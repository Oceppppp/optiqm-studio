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
        return r
