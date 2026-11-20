"""Modul Integer & Mixed-Integer Programming."""

from __future__ import annotations

import numpy as np
import pandas as pd

from optiqm.core import BaseModule, InputError, ModuleResult, ParamSpec, SheetData, register
from optiqm.core.parsing import clean_frame, find_column, require_rows, to_float
from optiqm.modules.linear_programming.solver import LPProblem, normalize_sign, solve_lp

from .solver import solve_milp


@register
class IntegerProgramming(BaseModule):
    key = "integer_programming"
    name = "Integer / Mixed Integer Programming"
    category = "Pemrograman Matematis"
    description = "Optimasi linear dengan variabel bilangan bulat (int), biner (bin), atau campuran (real)."
    sheet_prefixes = ("IP", "MILP", "INTEGER")
    params = (
        ParamSpec("objective", "Tujuan", "choice", "max", ("max", "min")),
        ParamSpec("default_type", "Tipe Default Variabel", "choice", "int", ("int", "bin", "real")),
    )
    table_hint = ("Sama seperti LP, ditambah baris opsional bernama 'Type' berisi int/bin/real per variabel.")

    def template(self) -> SheetData:
        # Contoh Harrison Electric (Render-Stair-Hanna): max 7X1 + 6X2 -> int X1=5, X2=0?
        # Contoh klasik: max 100X1 + 150X2; 8000X1+4000X2<=40000; 15X1+30X2<=200 -> X1=2, X2=5 Z=950?
        # Harrison Electric: max 7X1 + 6X2; 2X1+3X2<=12; 6X1+5X2<=30 -> LP: X1=5, X2=0 (35)?
        # Better: max 50X1 + 120X2; 2X1+4X2<=13; X1+X2<=4 -> X1=1, X2=2 -> 290; atau X1=0, X2=3 -> 360.
        df = pd.DataFrame(
            [["Objective", 100, 150, None, None],
             ["Type", "int", "int", None, None],
             ["Modal", 8000, 4000, "<=", 40000],
             ["Jam Kerja", 15, 30, "<=", 200]],
            columns=["Name", "X1", "X2", "Sign", "RHS"],
        )
        return SheetData(params={"objective": "max", "default_type": "int"}, tables={"main": df})

    def solve(self, data: SheetData) -> ModuleResult:
        p = self.resolved_params(data)
        df = clean_frame(data.table("main"))
        require_rows(df, 2, "Tabel Integer Programming")
        name_col = df.columns[0]
        sign_col = find_column(df, ["Sign", "Tanda", "Relation"])
        rhs_col = find_column(df, ["RHS", "Kapasitas", "Nilai Kanan"])
        var_cols = [c for c in df.columns if c not in (name_col, sign_col, rhs_col)]
        if not var_cols:
            raise InputError("Tidak ada kolom variabel.")

        var_types = [p["default_type"]] * len(var_cols)
        c = np.array([0.0 if pd.isna(df.at[0, col]) else to_float(df.at[0, col], f"Obj {col}") for col in var_cols])
        A, signs, b, names = [], [], [], []
        for i in range(1, len(df)):
            nm = str(df.at[i, name_col]).strip()
            if nm.lower() in {"type", "tipe", "jenis"}:
                var_types = [
                    p["default_type"] if pd.isna(df.at[i, col]) or not str(df.at[i, col]).strip()
                    else str(df.at[i, col]).strip()
                    for col in var_cols
                ]
                continue
            A.append([0.0 if pd.isna(df.at[i, col]) else to_float(df.at[i, col], f"{nm}/{col}") for col in var_cols])
            signs.append(normalize_sign(df.at[i, sign_col], nm))
            b.append(to_float(df.at[i, rhs_col], f"RHS {nm}"))
            names.append(nm)
        if not A:
            raise InputError("Minimal harus ada 1 baris kendala.")

        prob = LPProblem(var_cols, c, np.array(A), signs, np.array(b), names, p["objective"] == "max")
        x, z, slack = solve_milp(prob, var_types)
        lp_bounds = [
            (0.0, 1.0) if vt.strip().lower() in {"bin", "binary", "0-1", "biner"} else (0.0, None)
            for vt in var_types
        ]
        lp_sol = solve_lp(prob, bounds=lp_bounds)

        r = ModuleResult()
        r.metric("Nilai Optimal Z (Integer)", z, highlight=True)
        r.metric("Nilai LP Relaxation", lp_sol.objective)
        for v, val in zip(var_cols, x):
            r.metric(v, round(float(val), 6))

        r.table("Solusi Variabel", ["Variabel", "Tipe", "Nilai Optimal", "LP Relaxation", "Koef. Tujuan"],
                [[v, vt, x[j], lp_sol.x[j], c[j]] for j, (v, vt) in enumerate(zip(var_cols, var_types))])
        r.table("Status Kendala", ["Kendala", "LHS", "Tanda", "RHS", "Slack/Surplus"],
                [[n, float(prob.A[i] @ x), prob.signs[i], prob.b[i], slack[i]] for i, n in enumerate(names)])

        parts = ", ".join(f"{v}={x[j]:g}" for j, v in enumerate(var_cols))
        r.interpretation = f"Solusi integer optimal Z = {z:,.4f} pada {parts} (LP relaxation = {lp_sol.objective:,.4f})."

        # Analisis mendalam
        gap_abs = abs(lp_sol.objective - z)
        gap_pct = (gap_abs / abs(lp_sol.objective) * 100.0) if abs(lp_sol.objective) > 1e-12 else 0.0
        sub_str = " + ".join(f"({c[j]:g}×{x[j]:g})" for j in range(len(var_cols)))
        type_summary = ", ".join(f"{v}:{vt}" for v, vt in zip(var_cols, var_types))
        r.analyze(
            "Metodologi Branch-and-Bound (MILP) & Relaksasi LP",
            f"Masalah diselesaikan dengan Mixed-Integer Linear Programming (HiGHS Branch-and-Cut) untuk tujuan "
            f"{'Maksimasi' if prob.maximize else 'Minimasi'} dengan domain variabel ({type_summary}).",
            [
                f"Solusi Relaksasi LP (tanpa syarat bulat, tetap menghormati batas biner 0–1): Z_LP = {lp_sol.objective:,.4f}.",
                f"Solusi Integer Optimal: Z_IP = {sub_str} = {z:,.4f}.",
                f"Integrality Gap (biaya diskretisasi): |Z_LP − Z_IP| = {gap_abs:,.4f} ({gap_pct:.2f}% terhadap batas teoretis LP).",
            ],
        )

        detail_bullets: list[str] = []
        frac_vars = [
            f"{v} (LP={lp_sol.x[j]:.3f} → IP={x[j]:g})"
            for j, v in enumerate(var_cols)
            if abs(lp_sol.x[j] - x[j]) > 1e-5
        ]
        if frac_vars:
            detail_bullets.append(
                f"Perbedaan nilai antara LP Relaxation dan solusi bulat terjadi pada: {', '.join(frac_vars)}. "
                "Ini membuktikan pembulatan naif dari LP berisiko melanggar kendala atau menghasilkan nilai sub-optimal."
            )
        else:
            detail_bullets.append("Solusi LP Relaxation kebetulan sudah memenuhi syarat bilangan bulat (Integrality Gap = 0).")
        for i, n in enumerate(names):
            lhs_i = float(prob.A[i] @ x)
            util_pct = (lhs_i / prob.b[i] * 100.0) if abs(prob.b[i]) > 1e-12 else 0.0
            detail_bullets.append(
                f"Kendala '{n}': terpakai {lhs_i:,.4g} dari {prob.b[i]:,.4g} ({prob.signs[i]}), "
                f"sisa/selisih = {slack[i]:,.4g}" + (f" (utilisasi {util_pct:.1f}%)." if prob.signs[i] == "<=" and prob.b[i] > 0 else ".")
            )
        r.analyze(
            "Analisis Integrality Gap & Utilisasi Kendala",
            "Perbandingan solusi kontinu vs diskrit memperlihatkan seberapa ketat syarat bilangan bulat/biner memengaruhi pemanfaatan kapasitas.",
            detail_bullets,
        )

        chosen = [f"{v}={x[j]:g}" for j, v in enumerate(var_cols) if x[j] > 1e-6]
        rejected = [v for j, v in enumerate(var_cols) if x[j] <= 1e-6]
        tightest = min(range(len(names)), key=lambda i: slack[i])
        r.analyze(
            "Rekomendasi Keputusan",
            "Panduan eksekusi keputusan diskrit berdasarkan hasil optimasi MILP:",
            [
                f"Keputusan aktif terpilih: {', '.join(chosen) or 'tidak ada variabel bernilai positif'}."
                + (f" Variabel tidak dipilih (0): {', '.join(rejected)}." if rejected else ""),
                f"Kendala paling ketat adalah '{names[tightest]}' (sisa {slack[tightest]:,.4g}); penambahan kapasitas kecil di sini dapat membuka kombinasi bulat yang lebih baik.",
                "Perhatikan bahwa dalam MILP tidak berlaku Shadow Price linear seperti LP biasa—uji skenario perubahan RHS secara langsung untuk menilai dampak ekspansi.",
            ],
        )
        return r
