"""Modul Project Crashing (percepatan proyek dengan LP)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import linprog

from optiqm.core import BaseModule, InputError, ModuleResult, ParamSpec, SheetData, SolverError, register
from optiqm.core.parsing import clean_frame, find_column, require_rows, to_float
from optiqm.modules.project_management.solver import Activity, parse_preds, solve_cpm_pert


@dataclass
class CrashItem:
    name: str
    preds: list[str]
    normal_t: float
    crash_t: float
    normal_c: float
    crash_c: float

    @property
    def max_crash(self) -> float:
        return max(0.0, self.normal_t - self.crash_t)

    @property
    def slope(self) -> float:
        return (self.crash_c - self.normal_c) / self.max_crash if self.max_crash > 0 else 0.0


def solve_crashing_lp(items: list[CrashItem], target: float) -> tuple[np.ndarray, float]:
    """Minimasi biaya crash untuk mencapai target durasi proyek via LP.

    Variabel: [y_0..y_{n-1} (pengurangan waktu per aktivitas), S_0..S_{n-1} (waktu mulai), T_proj]
    """
    n = len(items)
    idx = {it.name: i for i, it in enumerate(items)}
    total_v = 2 * n + 1
    T_idx = 2 * n
    c = np.zeros(total_v)
    for i, it in enumerate(items):
        c[i] = it.slope

    A_ub, b_ub = [], []
    for i, it in enumerate(items):
        # S_i + (normal_t - y_i) <= T_proj  =>  S_i - y_i - T_proj <= -normal_t
        row = np.zeros(total_v)
        row[n + i] = 1.0
        row[i] = -1.0
        row[T_idx] = -1.0
        A_ub.append(row); b_ub.append(-it.normal_t)
        for pr in it.preds:
            j = idx[pr]
            # S_j + (normal_t_j - y_j) <= S_i  =>  S_j - y_j - S_i <= -normal_t_j
            r2 = np.zeros(total_v)
            r2[n + j] = 1.0
            r2[j] = -1.0
            r2[n + i] = -1.0
            A_ub.append(r2); b_ub.append(-items[j].normal_t)

    bounds = [(0.0, it.max_crash) for it in items] + [(0.0, None)] * n + [(0.0, target)]
    res = linprog(c, A_ub=np.array(A_ub), b_ub=np.array(b_ub), bounds=bounds, method="highs")
    if not res.success:
        raise SolverError(f"Target durasi {target:g} tidak dapat dicapai meskipun seluruh aktivitas di-crash penuh.")
    y = res.x[:n]
    return y, float(sum(it.normal_c + it.slope * y[i] for i, it in enumerate(items)))


@register
class ProjectCrashing(BaseModule):
    key = "project_crashing"
    name = "Project Crashing"
    category = "Manajemen Proyek"
    description = "Mempercepat jadwal proyek hingga target durasi dengan tambahan biaya seminimal mungkin."
    sheet_prefixes = ("CRASH",)
    params = (ParamSpec("target_duration", "Target Durasi (kosongkan = maksimal crash)", "text", ""),)
    table_hint = "Kolom: Activity, Predecessors, Normal_Time, Crash_Time, Normal_Cost, Crash_Cost."

    def template(self) -> SheetData:
        # Contoh klasik Milwaukee Paper Crashing (Heizer & Render): normal=15 ($30.5k), crash ke 13 (+$1,750)
        df = pd.DataFrame(
            [["A", "-", 2, 1, 22000, 22750],
             ["B", "-", 3, 1, 30000, 34000],
             ["C", "A", 2, 1, 26000, 27000],
             ["D", "A, B", 4, 3, 48000, 49000],
             ["E", "C", 4, 2, 56000, 58000],
             ["F", "C", 3, 2, 30000, 30500],
             ["G", "D, E", 5, 2, 80000, 84500],
             ["H", "F, G", 2, 1, 16000, 19000]],
            columns=["Activity", "Predecessors", "Normal_Time", "Crash_Time", "Normal_Cost", "Crash_Cost"],
        )
        return SheetData(params={"target_duration": "13"}, tables={"main": df})

    def solve(self, data: SheetData) -> ModuleResult:
        p = self.resolved_params(data)
        df = clean_frame(data.table("main"))
        require_rows(df, 1, "Tabel project crashing")
        c_act = find_column(df, ["Activity", "Aktivitas", "Task"])
        c_pred = find_column(df, ["Predecessors", "Predecessor", "Pendahulu"], required=False)
        c_nt = find_column(df, ["Normal_Time", "NormalTime", "NT"])
        c_ct = find_column(df, ["Crash_Time", "CrashTime", "CT"])
        c_nc = find_column(df, ["Normal_Cost", "NormalCost", "NC"])
        c_cc = find_column(df, ["Crash_Cost", "CrashCost", "CC"])

        items: list[CrashItem] = []
        for i in range(len(df)):
            nm = str(df.at[i, c_act]).strip()
            nt, ct = to_float(df.at[i, c_nt], f"NT {nm}"), to_float(df.at[i, c_ct], f"CT {nm}")
            nc, cc = to_float(df.at[i, c_nc], f"NC {nm}"), to_float(df.at[i, c_cc], f"CC {nm}")
            if nt < 0 or ct < 0 or nc < 0 or cc < 0:
                raise InputError(f"Waktu dan biaya pada aktivitas '{nm}' tidak boleh negatif.")
            if ct > nt:
                raise InputError(f"Crash_Time '{nm}' tidak boleh lebih besar dari Normal_Time.")
            if cc < nc - 1e-9:
                raise InputError(f"Crash_Cost '{nm}' ({cc:g}) tidak boleh lebih kecil dari Normal_Cost ({nc:g}).")
            items.append(CrashItem(nm, parse_preds(df.at[i, c_pred]) if c_pred else [], nt, ct, nc, cc))

        norm_res = solve_cpm_pert([Activity(it.name, it.preds, it.normal_t) for it in items])
        min_res = solve_cpm_pert([Activity(it.name, it.preds, it.crash_t) for it in items])
        normal_dur, min_dur = norm_res["duration"], min_res["duration"]
        target = to_float(p["target_duration"], "Target Durasi") if p["target_duration"] else min_dur
        if target < min_dur - 1e-6:
            raise InputError(f"Target durasi ({target:g}) lebih kecil dari batas minimum crash ({min_dur:g}).")

        y, total_cost = solve_crashing_lp(items, target)
        normal_total = sum(it.normal_c for it in items)
        crash_added = total_cost - normal_total
        eff_dur = min(target, normal_dur)

        r = ModuleResult()
        r.metric("Durasi Target", eff_dur, highlight=True)
        r.metric("Total Biaya Setelah Crash", total_cost, highlight=True)
        r.metric("Tambahan Biaya Crash", crash_added)
        r.metric("Durasi Normal / Min", f"{normal_dur:g} / {min_dur:g}")

        r.table("Rencana Percepatan (Crashing)",
                ["Aktivitas", "Waktu Normal", "Waktu Crash Min", "Biaya/Periode", "Di-crash (periode)", "Waktu Baru", "Tambahan Biaya"],
                [[it.name, it.normal_t, it.crash_t, it.slope, y[i], it.normal_t - y[i], y[i] * it.slope]
                 for i, it in enumerate(items)])

        # Kurva Trade-off Waktu vs Biaya (dibatasi maks 25 titik agar tetap responsif untuk rentang besar)
        span = normal_dur - min_dur
        if span <= 1e-9:
            durs = [round(normal_dur, 4)]
        elif span <= 24:
            durs = sorted({round(d, 4) for d in [normal_dur, *[normal_dur - k for k in range(1, int(span) + 1)], min_dur]})
        else:
            durs = sorted({round(float(d), 4) for d in np.linspace(min_dur, normal_dur, 25)})
        trade_costs = [solve_crashing_lp(items, d)[1] for d in durs]
        r.chart("Kurva Trade-off Durasi vs Total Biaya", "line", {
            "x": [f"{d:g}" for d in durs],
            "series": [{"name": "Total Biaya Proyek", "data": trade_costs}],
            "x_label": "Durasi Proyek", "y_label": "Total Biaya",
        })
        r.interpretation = f"Mempercepat proyek dari {normal_dur:g} menjadi {eff_dur:g} membutuhkan tambahan biaya {crash_added:,.2f} (total {total_cost:,.2f})."

        # Analisis mendalam
        saved_t = max(0.0, normal_dur - eff_dur)
        avg_marginal = (crash_added / saved_t) if saved_t > 1e-9 else 0.0
        crashed = [(items[i], float(y[i]), float(y[i] * items[i].slope)) for i in range(len(items)) if y[i] > 1e-6]
        post_res = solve_cpm_pert([Activity(it.name, it.preds, it.normal_t - float(y[i])) for i, it in enumerate(items)])
        r.analyze(
            "Metodologi Optimasi Crashing via Linear Programming",
            "Model LP meminimalkan Σ(Slope_i × y_i) terhadap seluruh hubungan presedensi jaringan sehingga secara otomatis "
            "menangani kemunculan jalur kritis paralel baru saat durasi dipangkas.",
            [
                f"Durasi Normal = {normal_dur:g} (biaya {normal_total:,.2f}) → Target = {eff_dur:g} (penghematan {saved_t:g} periode, batas crash fisik = {min_dur:g}).",
                f"Tambahan Biaya Crash = {crash_added:,.2f} (+{(crash_added / normal_total * 100.0) if normal_total > 0 else 0.0:.2f}% dari biaya normal); "
                f"biaya marjinal rata-rata = {avg_marginal:,.2f} per periode percepatan.",
            ],
        )

        crash_bullets = [
            f"Aktivitas '{it.name}': dipercepat {yi:g} periode (dari {it.normal_t:g} → {it.normal_t - yi:g}, slope {it.slope:,.2f}/periode, subtotal {ci:,.2f}"
            + (", mencapai batas crash maksimal)." if abs(yi - it.max_crash) < 1e-6 else ").")
            for it, yi, ci in crashed
        ] or ["Tidak ada aktivitas yang perlu di-crash karena durasi target sudah ≥ durasi normal."]
        crash_bullets.append(
            f"Setelah crashing, terdapat {len(post_res['crit_paths'])} jalur kritis aktif pada durasi {post_res['duration']:g}: "
            + " | ".join(" → ".join(cp) for cp in post_res["crit_paths"][:3]) + "."
        )
        r.analyze(
            "Bedah Aktivitas Dipercepat & Jalur Kritis Pasca-Crashing",
            "Percepatan yang baik memilih aktivitas kritis dengan biaya/periode terendah dan menghindari pemborosan crash pada aktivitas non-kritis:",
            crash_bullets,
        )

        rec_bullets = [
            f"Crashing menuju durasi {eff_dur:g} layak secara ekonomis apabila biaya tidak langsung (overhead/denda keterlambatan) melebihi {avg_marginal:,.2f} per periode."
        ]
        if eff_dur > min_dur + 1e-6:
            max_cost = trade_costs[0]
            rec_bullets.append(
                f"Masih tersedia ruang percepatan tambahan sebesar {eff_dur - min_dur:g} periode lagi menuju durasi crash penuh ({min_dur:g}) "
                f"dengan tambahan biaya ekstra {max_cost - total_cost:,.2f}."
            )
        else:
            rec_bullets.append("Proyek sudah berada pada batas crash fisik minimum; percepatan lebih lanjut memerlukan perubahan metode kerja atau desain jaringan.")
        r.analyze("Rekomendasi Trade-off Waktu vs Biaya", "Dasar pengambilan keputusan anggaran percepatan:", rec_bullets)
        return r
