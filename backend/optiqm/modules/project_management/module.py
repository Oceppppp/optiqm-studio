"""Modul Project Management (PERT / CPM)."""

from __future__ import annotations

import pandas as pd

from optiqm.core import BaseModule, InputError, ModuleResult, ParamSpec, SheetData, register
from optiqm.core.parsing import clean_frame, find_column, require_rows, to_float

from .solver import Activity, parse_preds, solve_cpm_pert


@register
class ProjectManagement(BaseModule):
    key = "project_management"
    name = "Project Management (PERT/CPM)"
    category = "Manajemen Proyek"
    description = "Menghitung jalur kritis, ES/EF/LS/LF, slack, diagram Gantt & jaringan, serta probabilitas PERT."
    sheet_prefixes = ("PERT", "CPM", "PROJ", "PROYEK")
    params = (
        ParamSpec("target_time", "Target Waktu Penyelesaian (opsional, untuk PERT)", "text", ""),
    )
    table_hint = ("Kolom: Activity, Predecessors (dipisah koma, '-' jika tidak ada), lalu Time (CPM) "
                  "ATAU tiga kolom Optimistic, Most_Likely, Pessimistic (PERT).")

    def template(self) -> SheetData:
        # Milwaukee Paper Manufacturing (Heizer & Render): durasi = 15, jalur kritis A-C-E-G-H
        df = pd.DataFrame(
            [["A", "-", 1, 2, 3],
             ["B", "-", 2, 3, 4],
             ["C", "A", 1, 2, 3],
             ["D", "A, B", 2, 4, 6],
             ["E", "C", 1, 4, 7],
             ["F", "C", 1, 2, 9],
             ["G", "D, E", 3, 4, 11],
             ["H", "F, G", 1, 2, 3]],
            columns=["Activity", "Predecessors", "Optimistic", "Most_Likely", "Pessimistic"],
        )
        return SheetData(params={"target_time": "16"}, tables={"main": df})

    def solve(self, data: SheetData) -> ModuleResult:
        p = self.resolved_params(data)
        df = clean_frame(data.table("main"))
        require_rows(df, 1, "Tabel aktivitas proyek")
        c_act = find_column(df, ["Activity", "Aktivitas", "Task", "ID"])
        c_pred = find_column(df, ["Predecessors", "Predecessor", "Pendahulu", "Pred"], required=False)

        c_opt = find_column(df, ["Optimistic", "Opt", "a", "O"], required=False)
        c_ml = find_column(df, ["Most_Likely", "MostLikely", "ML", "m", "Likely"], required=False)
        c_pes = find_column(df, ["Pessimistic", "Pes", "b", "P"], required=False)
        c_time = find_column(df, ["Time", "Duration", "Durasi", "Waktu", "t"], required=False)

        is_pert = bool(c_opt and c_ml and c_pes)
        if not is_pert and not c_time:
            raise InputError("Sertakan kolom 'Time' (CPM) atau tiga kolom 'Optimistic', 'Most_Likely', 'Pessimistic' (PERT).")

        acts: list[Activity] = []
        for i in range(len(df)):
            nm = str(df.at[i, c_act]).strip()
            preds = parse_preds(df.at[i, c_pred]) if c_pred else []
            if is_pert:
                a = to_float(df.at[i, c_opt], f"Optimistic {nm}")
                m = to_float(df.at[i, c_ml], f"Most_Likely {nm}")
                b = to_float(df.at[i, c_pes], f"Pessimistic {nm}")
                if a < 0 or not (a <= m <= b):
                    raise InputError(f"Estimasi PERT pada '{nm}' harus memenuhi 0 ≤ Optimistic ({a:g}) ≤ Most_Likely ({m:g}) ≤ Pessimistic ({b:g}).")
                t = (a + 4.0 * m + b) / 6.0
                var = ((b - a) / 6.0) ** 2
            else:
                t = to_float(df.at[i, c_time], f"Time {nm}")
                var = 0.0
            if t < 0:
                raise InputError(f"Durasi '{nm}' tidak boleh negatif.")
            acts.append(Activity(nm, preds, t, var))

        target = to_float(p["target_time"], "Target Waktu") if p["target_time"] else None
        out = solve_cpm_pert(acts, target)
        crit = out["critical"]

        r = ModuleResult()
        r.metric("Durasi Proyek", out["duration"], highlight=True)
        path_str = " → ".join(out["crit_paths"][0]) if out["crit_paths"] else "-"
        r.metric("Jalur Kritis", path_str, highlight=True)
        if is_pert:
            r.metric("Std. Deviasi Jalur Kritis", out["std"])
        if out["prob"] is not None:
            r.metric(f"P(Selesai ≤ {target:g})", f"{out['prob'] * 100:.2f}%")
        if len(out["crit_paths"]) > 1:
            r.warnings.append(
                f"Terdapat {len(out['crit_paths'])} jalur kritis paralel; keterlambatan pada salah satu jalur akan langsung menunda proyek."
            )

        rows_out = []
        for nm in out["order"]:
            a = out["by_name"][nm]
            rows_out.append([nm, ", ".join(a.preds) or "-", a.time, out["es"][nm], out["ef"][nm],
                             out["ls"][nm], out["lf"][nm], out["slack"][nm], "Ya" if nm in crit else "Tidak",
                             *([a.variance] if is_pert else [])])
        cols = ["Aktivitas", "Pendahulu", "Durasi", "ES", "EF", "LS", "LF", "Slack", "Kritis?"]
        if is_pert:
            cols.append("Varians")
        r.table("Jadwal Aktivitas (PERT/CPM)", cols, rows_out)

        G = out["G"]
        nodes = [{"id": "__START__", "label": "Start", "highlight": True},
                 *[{"id": nm, "label": f"{nm} ({out['by_name'][nm].time:g})", "highlight": nm in crit}
                   for nm in out["order"]],
                 {"id": "__END__", "label": f"Finish ({out['duration']:g})", "highlight": True}]
        edges = []
        for nm in out["order"]:
            if G.in_degree(nm) == 0:
                edges.append({"source": "__START__", "target": nm, "label": "", "highlight": nm in crit})
            for succ in G.successors(nm):
                edges.append({"source": nm, "target": succ, "label": "", "highlight": nm in crit and succ in crit})
            if G.out_degree(nm) == 0:
                edges.append({"source": nm, "target": "__END__", "label": "",
                              "highlight": nm in crit and abs(out["ef"][nm] - out["duration"]) < 1e-7})

        r.chart("Diagram Jaringan Aktivitas (AON)", "network", {"directed": True, "nodes": nodes, "edges": edges})
        r.chart("Gantt Chart Jadwal Proyek", "gantt", {
            "tasks": [{"name": nm, "start": out["es"][nm], "end": out["ef"][nm], "highlight": nm in crit}
                      for nm in out["order"]],
        })
        r.interpretation = f"Durasi proyek = {out['duration']:,.2f} dengan jalur kritis {path_str}."

        # Analisis mendalam
        mode_lbl = "PERT (3-Point Beta: t = (a + 4m + b)/6, σ² = ((b−a)/6)²)" if is_pert else "CPM (Deterministik)"
        all_paths_txt = " | ".join(" → ".join(cp) for cp in out["crit_paths"][:4])
        r.analyze(
            "Metodologi Forward/Backward Pass & Jalur Kritis",
            f"Jaringan Activity-on-Node (AON) berjumlah {len(acts)} aktivitas dianalisis dengan metode {mode_lbl}. "
            "Forward pass menentukan ES/EF, backward pass menentukan LS/LF, dan aktivitas dengan Slack = LS − ES = 0 membentuk jalur kritis.",
            [
                f"Durasi ekspektasi proyek = {out['duration']:,.2f} satuan waktu; {len(crit)} dari {len(acts)} aktivitas ({len(crit)/len(acts)*100:.1f}%) bersifat kritis (Slack = 0).",
                f"Jalur kritis teridentifikasi ({len(out['crit_paths'])} jalur): {all_paths_txt}.",
            ],
        )

        non_crit = sorted([(out["slack"][nm], nm) for nm in out["order"] if nm not in crit])
        risk_bullets: list[str] = []
        if non_crit:
            tight_sl, tight_nm = non_crit[0]
            max_sl, max_nm = non_crit[-1]
            risk_bullets.append(
                f"Aktivitas non-kritis paling ketat (near-critical): '{tight_nm}' dengan Slack hanya {tight_sl:,.2f} — "
                "keterlambatan melebihi batas ini akan memunculkan jalur kritis baru."
            )
            risk_bullets.append(f"Aktivitas paling fleksibel: '{max_nm}' dengan Slack = {max_sl:,.2f} (sumber daya dapat dipinjam sementara jika dibutuhkan jalur kritis).")
        else:
            risk_bullets.append("Seluruh aktivitas bersifat kritis (tidak ada kelonggaran/slack di seluruh jaringan).")

        if is_pert:
            top_var_act = max(acts, key=lambda a: a.variance)
            ci_lo = max(0.0, out["duration"] - 1.96 * out["std"])
            ci_hi = out["duration"] + 1.96 * out["std"]
            risk_bullets.append(
                f"Ketidakpastian PERT: varians jalur kritis = {out['variance']:,.3f}, std. deviasi σ = {out['std']:,.3f}; "
                f"rentang keyakinan 95% penyelesaian proyek berada di [{ci_lo:,.2f}, {ci_hi:,.2f}]."
            )
            risk_bullets.append(f"Sumber ketidakpastian terbesar: aktivitas '{top_var_act.name}' (varians = {top_var_act.variance:,.3f}).")
            if out["prob"] is not None and target is not None:
                z_txt = f"Z = {out['z']:+.3f}" if out["z"] is not None else "deterministik"
                risk_bullets.append(
                    f"Peluang selesai ≤ target {target:g} ({z_txt}) = {out['prob'] * 100:.2f}% "
                    f"({'sangat aman' if out['prob'] >= 0.9 else ('cukup moderat' if out['prob'] >= 0.7 else 'risiko terlambat tinggi')})."
                )
        r.analyze(
            "Bedah Kelonggaran (Slack) & Risiko Ketidakpastian Jadwal",
            "Identifikasi aktivitas hampir kritis dan variabilitas durasi membantu manajer proyek memfokuskan mitigasi sebelum keterlambatan terjadi:",
            risk_bullets,
        )

        rec_bullets = [
            f"Terapkan pemantauan harian ketat pada aktivitas jalur kritis ({', '.join(nm for nm in out['order'] if nm in crit)}) karena setiap 1 satuan keterlambatan langsung memundurkan tanggal selesai proyek."
        ]
        if is_pert and out["prob"] is not None and out["prob"] < 0.85:
            rec_bullets.append("Peluang memenuhi target waktu masih di bawah 85%: pertimbangkan percepatan (Project Crashing) pada aktivitas kritis termurah atau tambahkan buffer waktu.")
        if non_crit:
            rec_bullets.append(f"Manfaatkan kelonggaran pada '{non_crit[-1][1]}' (Slack {non_crit[-1][0]:,.2f}) untuk resource leveling agar beban kerja tim lebih merata.")
        r.analyze("Rekomendasi Pengendalian Proyek", "Strategi pengawasan dan mitigasi risiko jadwal:", rec_bullets)
        return r
