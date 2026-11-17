"""Modul Preemptive Goal Programming."""

from __future__ import annotations

import numpy as np
import pandas as pd

from optiqm.core import BaseModule, InputError, ModuleResult, SheetData, register
from optiqm.core.parsing import clean_frame, find_column, require_rows, to_float
from optiqm.modules.linear_programming.solver import normalize_sign

from .solver import GoalRow, solve_goal_programming


@register
class GoalProgramming(BaseModule):
    key = "goal_programming"
    name = "Goal Programming"
    category = "Pemrograman Matematis"
    description = "Optimasi multi-tujuan berprioritas (Preemptive Goal Programming) dengan deviasi d- dan d+."
    sheet_prefixes = ("GP", "GOAL")
    table_hint = ("Kolom: Goal/Kendala, X1..Xn, Sign (=, <=, >=), Target/RHS, Priority (0 = kendala keras), "
                  "W_minus (penalti kurang), W_plus (penalti lebih).")

    def template(self) -> SheetData:
        # Contoh Harrison Electric: X1 = lampu, X2 = kipas; profit $7,$6 target 30;
        # P1: profit >= 30 (w-=1,w+=0); P2: wiring <= 240 (w+=1); P3: X1 >= 3; dll.
        # Contoh standar: X1, X2
        df = pd.DataFrame(
            [["Target Laba", 7, 6, ">=", 30, 1, 1, 0],
             ["Lembur Perakitan", 2, 3, "<=", 12, 2, 0, 1],
             ["Target Lampu", 1, 0, ">=", 4, 3, 1, 0],
             ["Kapasitas Kabel", 6, 5, "<=", 30, 0, 0, 0]],
            columns=["Goal", "X1", "X2", "Sign", "Target", "Priority", "W_minus", "W_plus"],
        )
        return SheetData(tables={"main": df})

    def solve(self, data: SheetData) -> ModuleResult:
        df = clean_frame(data.table("main"))
        require_rows(df, 1, "Tabel Goal Programming")
        name_col = df.columns[0]
        sign_col = find_column(df, ["Sign", "Tanda"], required=False)
        target_col = find_column(df, ["Target", "RHS"])
        prio_col = find_column(df, ["Priority", "Prioritas"])
        wm_col = find_column(df, ["W_minus", "W-", "Under", "Wt-"], required=False)
        wp_col = find_column(df, ["W_plus", "W+", "Over", "Wt+"], required=False)
        meta = {c for c in (name_col, sign_col, target_col, prio_col, wm_col, wp_col) if c}
        var_cols = [c for c in df.columns if c not in meta]
        if not var_cols:
            raise InputError("Tidak ada kolom variabel keputusan.")

        rows: list[GoalRow] = []
        for i in range(len(df)):
            nm = str(df.at[i, name_col]).strip()
            coeffs = np.array([0.0 if pd.isna(df.at[i, c]) else to_float(df.at[i, c], f"{nm}/{c}") for c in var_cols])
            target = to_float(df.at[i, target_col], f"Target {nm}")
            pr = int(round(to_float(df.at[i, prio_col], f"Priority {nm}")))
            sg = normalize_sign(df.at[i, sign_col], nm) if sign_col and not pd.isna(df.at[i, sign_col]) else "="
            wm = to_float(df.at[i, wm_col], f"W_minus {nm}") if wm_col and not pd.isna(df.at[i, wm_col]) else (1.0 if sg == ">=" else 0.0)
            wp = to_float(df.at[i, wp_col], f"W_plus {nm}") if wp_col and not pd.isna(df.at[i, wp_col]) else (1.0 if sg == "<=" else 0.0)
            if sg == "=" and wm == 0 and wp == 0 and pr > 0:
                wm = wp = 1.0
            rows.append(GoalRow(nm, coeffs, target, pr, wm, wp, sg))

        if not any(g.priority > 0 for g in rows):
            raise InputError("Minimal harus ada 1 tujuan dengan Priority >= 1.")

        out = solve_goal_programming(var_cols, rows)
        r = ModuleResult()
        for v, val in zip(var_cols, out["x"]):
            r.metric(v, float(val), highlight=True)
        achieved = sum(1 for pr, val in out["steps"] if val < 1e-6)
        r.metric("Prioritas Tercapai Penuh", f"{achieved} / {len(out['steps'])}")

        r.table("Solusi Variabel", ["Variabel", "Nilai"], [[v, val] for v, val in zip(var_cols, out["x"])])
        g_rows = []
        for k, g in enumerate(out["goals"]):
            lhs = float(g.coeffs @ out["x"])
            dm, dp = float(out["d_minus"][k]), float(out["d_plus"][k])
            pen = g.w_minus * dm + g.w_plus * dp
            status = "Tercapai" if pen < 1e-6 else f"Deviasi (penalti={pen:g})"
            g_rows.append([g.priority, g.name, lhs, g.target, dm, dp, status])
        r.table("Analisis Pencapaian Tujuan", ["Prioritas", "Tujuan", "Aktual", "Target", "d⁻ (Kurang)", "d⁺ (Lebih)", "Status"], g_rows)
        r.interpretation = ", ".join(f"{v}={val:g}" for v, val in zip(var_cols, out["x"])) + f" — {achieved}/{len(out['steps'])} prioritas tercapai penuh."
        return r
