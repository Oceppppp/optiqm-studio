"""Modul Game Theory (Two-Person Zero-Sum: Saddle Point & Mixed Strategy LP)."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import linprog

from optiqm.core import BaseModule, InputError, ModuleResult, SheetData, SolverError, register
from optiqm.core.parsing import clean_frame, require_rows, to_float


def solve_zero_sum(M: np.ndarray) -> dict:
    """Selesaikan game zero-sum (baris = Pemain A maksimasi, kolom = Pemain B minimasi)."""
    m, n = M.shape
    row_mins = M.min(axis=1)
    col_maxs = M.max(axis=0)
    maximin = float(row_mins.max())
    minimax = float(col_maxs.min())
    if abs(maximin - minimax) < 1e-9:
        i0 = int(np.argmax(row_mins))
        j0 = int(np.argmin(col_maxs))
        p = np.zeros(m); p[i0] = 1.0
        q = np.zeros(n); q[j0] = 1.0
        return {"value": maximin, "p": p, "q": q, "pure": True, "saddle": (i0, j0)}

    # Geser matriks agar semua entri > 0 sehingga v > 0
    shift = abs(float(M.min())) + 1.0 if M.min() <= 0 else 0.0
    Mp = M + shift
    # Pemain A: min sum(y_i) s.t. Mp^T y >= 1, y >= 0  (y_i = p_i / v)
    res_a = linprog(np.ones(m), A_ub=-Mp.T, b_ub=-np.ones(n), bounds=[(0, None)] * m, method="highs")
    res_b = linprog(-np.ones(n), A_ub=Mp, b_ub=np.ones(m), bounds=[(0, None)] * n, method="highs")
    if not res_a.success or not res_b.success:
        raise SolverError("Gagal menyelesaikan mixed strategy LP.")
    v_shifted = 1.0 / float(res_a.x.sum())
    p = res_a.x * v_shifted
    q = res_b.x * (1.0 / float(res_b.x.sum()))
    return {"value": v_shifted - shift, "p": p, "q": q, "pure": False, "saddle": None}


@register
class GameTheory(BaseModule):
    key = "game_theory"
    name = "Game Theory"
    category = "Analisis Keputusan"
    description = "Permainan dua pemain zero-sum: deteksi saddle point dan strategi campuran (mixed strategy) via LP."
    sheet_prefixes = ("GAME",)
    table_hint = "Kolom pertama: strategi Pemain Baris (Row/Pemain 1). Kolom lainnya: strategi Pemain Kolom (nilai = payoff Pemain Baris)."

    def template(self) -> SheetData:
        # Contoh klasik mixed strategy: A=[[4, -2], [-1, 3]] -> value = 1.0?
        # 4p - (1-p) = -2p + 3(1-p) => 5p - 1 = 3 - 5p => 10p = 4 => p = 0.4, 0.6; v = 0.6
        df = pd.DataFrame([["Strategi A1", 4, -2], ["Strategi A2", -1, 3]],
                          columns=["Pemain A \\ B", "Strategi B1", "Strategi B2"])
        return SheetData(tables={"main": df})

    def solve(self, data: SheetData) -> ModuleResult:
        df = clean_frame(data.table("main"))
        require_rows(df, 1, "Matriks payoff permainan")
        row_names = [str(x).strip() for x in df.iloc[:, 0]]
        col_names = list(df.columns[1:])
        if not col_names:
            raise InputError("Minimal harus ada 1 strategi pemain kolom.")
        M = np.array([[to_float(df.at[i, c], f"{row_names[i]} vs {c}") for c in col_names] for i in range(len(df))])
        out = solve_zero_sum(M)

        r = ModuleResult()
        r.metric("Nilai Permainan (Value of Game)", out["value"], highlight=True)
        r.metric("Tipe Solusi", "Pure Strategy (Saddle Point)" if out["pure"] else "Mixed Strategy")
        r.table("Strategi Optimal Pemain Baris", ["Strategi", "Probabilitas", "Persen"],
                [[nm, out["p"][i], f"{out['p'][i] * 100:.2f}%"] for i, nm in enumerate(row_names)])
        r.table("Strategi Optimal Pemain Kolom", ["Strategi", "Probabilitas", "Persen"],
                [[nm, out["q"][j], f"{out['q'][j] * 100:.2f}%"] for j, nm in enumerate(col_names)])
        r.interpretation = (f"Nilai permainan = {out['value']:,.4f} ({'Saddle Point' if out['pure'] else 'Mixed Strategy'}): "
                            f"Pemain A ({', '.join(f'{n}:{p*100:.1f}%' for n, p in zip(row_names, out['p']))}).")
        return r
