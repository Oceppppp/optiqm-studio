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

        # Analisis mendalam
        maximin = float(M.min(axis=1).max())
        minimax = float(M.max(axis=0).min())
        v = float(out["value"])
        fairness = (
            "permainan ADIL (fair game, v = 0)" if abs(v) < 1e-7 else
            f"menguntungkan Pemain Baris sebesar +{v:,.4f} per putaran" if v > 0 else
            f"menguntungkan Pemain Kolom sebesar {abs(v):,.4f} per putaran"
        )
        r.analyze(
            "Metodologi Teori Permainan Zero-Sum (Maximin–Minimax)",
            f"Matriks payoff {M.shape[0]}×{M.shape[1]} dianalisis dengan prinsip Minimax (Teorema von Neumann). "
            f"Batas bawah murni Maximin = {maximin:,.4f} dan batas atas murni Minimax = {minimax:,.4f}.",
            [
                f"Tipe Ekuilibrium: {'Pure Strategy (Saddle Point ditemukan karena Maximin = Minimax = ' + f'{v:,.4f})' if out['pure'] else f'Mixed Strategy (karena Maximin {maximin:g} < Minimax {minimax:g}, diselesaikan via Linear Programming)'}.",
                f"Nilai Permainan (v = {v:,.4f}): {fairness}.",
            ],
        )

        exp_a_vs_b = out["p"] @ M
        exp_b_vs_a = M @ out["q"]
        ver_bullets = [
            "Payoff ekspektasi Pemain Baris (A) terhadap tiap strategi Pemain Kolom (B): "
            + ", ".join(f"vs {col_names[j]} = {exp_a_vs_b[j]:,.4f}" for j in range(len(col_names)))
            + f" (semuanya ≥ v = {v:,.4f}).",
            "Ekspektasi pembayaran Pemain Kolom (B) terhadap tiap strategi Pemain Baris (A): "
            + ", ".join(f"vs {row_names[i]} = {exp_b_vs_a[i]:,.4f}" for i in range(len(row_names)))
            + f" (semuanya ≤ v = {v:,.4f}).",
        ]
        unused_a = [row_names[i] for i in range(len(row_names)) if out["p"][i] < 1e-6]
        unused_b = [col_names[j] for j in range(len(col_names)) if out["q"][j] < 1e-6]
        if unused_a or unused_b:
            ver_bullets.append(
                f"Strategi tidak digunakan (probabilitas 0%): Pemain Baris [{', '.join(unused_a) or '-'}], Pemain Kolom [{', '.join(unused_b) or '-'}]."
            )
        r.analyze(
            "Verifikasi Ekuilibrium Nash & Payoff Ekspektasi",
            "Pada titik ekuilibrium, tidak ada pemain yang dapat memperbaiki hasil ekspektasinya dengan menyimpang sepihak:",
            ver_bullets,
        )

        if out["pure"]:
            i0, j0 = out["saddle"]
            rec_bullets = [
                f"Saddle Point stabil pada ({row_names[i0]}, {col_names[j0]}): kedua pemain sebaiknya konsisten memainkan strategi murni tersebut.",
                "Menyimpang dari Saddle Point hanya akan memberi keuntungan tambahan kepada lawan.",
            ]
        else:
            rec_bullets = [
                "Pemain Baris (A) harus mengacak pilihan secara independen sesuai proporsi: "
                + ", ".join(f"{n} ({p*100:.1f}%)" for n, p in zip(row_names, out["p"]) if p > 1e-6) + ".",
                "Pemain Kolom (B) harus mengacak pilihan sesuai proporsi: "
                + ", ".join(f"{n} ({q*100:.1f}%)" for n, q in zip(col_names, out["q"]) if q > 1e-6) + ".",
                "Kunci keberhasilan strategi campuran adalah kerahasiaan/pengacakan di setiap putaran agar lawan tidak bisa memprediksi langkah berikutnya.",
            ]
        r.analyze("Rekomendasi Strategi Kompetitif", "Panduan eksekusi di lapangan:", rec_bullets)
        return r
