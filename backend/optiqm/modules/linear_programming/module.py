"""Modul Linear Programming (adapter SheetData <-> solver)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from optiqm.core import BaseModule, InputError, ModuleResult, ParamSpec, SheetData, register
from optiqm.core.parsing import clean_frame, find_column, require_rows, to_float

from .solver import LPProblem, corner_points, feasible_region, normalize_sign, solve_lp


@register
class LinearProgramming(BaseModule):
    key = "linear_programming"
    name = "Linear Programming"
    category = "Pemrograman Matematis"
    description = "Maksimasi/minimasi fungsi linear dengan kendala linear (metode grafik untuk 2 variabel)."
    sheet_prefixes = ("LP",)
    params = (
        ParamSpec("objective", "Tujuan", "choice", "max", ("max", "min")),
    )
    table_hint = ("Baris pertama = fungsi tujuan (kolom Sign & RHS kosong), baris berikutnya = kendala. "
                  "Kolom: Name, X1..Xn, Sign (<=, >=, =), RHS.")

    def template(self) -> SheetData:
        df = pd.DataFrame(
            [["Objective", 50, 40, None, None],
             ["Waktu Perakitan", 3, 5, "<=", 150],
             ["Waktu Pengecatan", 1, 0, "<=", 20],
             ["Ruang Gudang", 8, 5, "<=", 300]],
            columns=["Name", "X1", "X2", "Sign", "RHS"],
        )
        return SheetData(params={"objective": "max"}, tables={"main": df})

    # ------------------------------------------------------------------ parse
    def build_problem(self, data: SheetData) -> LPProblem:
        p = self.resolved_params(data)
        df = clean_frame(data.table("main"))
        require_rows(df, 2, "Tabel LP (1 fungsi tujuan + minimal 1 kendala)")
        name_col = df.columns[0]
        sign_col = find_column(df, ["Sign", "Tanda", "Relation"])
        rhs_col = find_column(df, ["RHS", "Kapasitas", "Nilai Kanan"])
        var_cols = [c for c in df.columns if c not in (name_col, sign_col, rhs_col)]
        if not var_cols:
            raise InputError("Tidak ada kolom variabel keputusan (mis. X1, X2).")

        def row_values(i: int) -> list[float]:
            return [0.0 if pd.isna(df.at[i, c]) else to_float(df.at[i, c], f"{df.at[i, name_col]}/{c}")
                    for c in var_cols]

        c = np.array(row_values(0))
        A, signs, b, names = [], [], [], []
        for i in range(1, len(df)):
            nm = str(df.at[i, name_col]) if not pd.isna(df.at[i, name_col]) else f"C{i}"
            A.append(row_values(i))
            signs.append(normalize_sign(df.at[i, sign_col], nm))
            b.append(to_float(df.at[i, rhs_col], f"RHS {nm}"))
            names.append(nm)
        return LPProblem(var_cols, c, np.array(A), signs, np.array(b), names, p["objective"] == "max")

    # ------------------------------------------------------------------ solve
    def solve(self, data: SheetData) -> ModuleResult:
        prob = self.build_problem(data)
        sol = solve_lp(prob)
        r = ModuleResult()
        r.metric("Nilai Optimal Z", sol.objective, highlight=True)
        for v, x in zip(prob.variables, sol.x):
            r.metric(v, x)

        r.table("Solusi Variabel", ["Variabel", "Nilai", "Koef. Tujuan", "Reduced Cost"],
                [[v, x, c, rc] for v, x, c, rc in zip(prob.variables, sol.x, prob.c, sol.reduced_costs)])
        r.table("Kendala & Analisis Sensitivitas",
                ["Kendala", "LHS", "Tanda", "RHS", "Slack/Surplus", "Shadow Price", "Status"],
                [[n, float(prob.A[i] @ sol.x), prob.signs[i], prob.b[i], sol.slack[i], sol.shadow_prices[i],
                  "Binding" if sol.slack[i] < 1e-7 else "Non-binding"]
                 for i, n in enumerate(prob.constraint_names)])

        if len(prob.variables) == 2:
            region = feasible_region(prob, sol.x)
            r.chart("Metode Grafik — Daerah Feasible", "lp_region", region)
            r.table("Titik Sudut (Corner Points)", [prob.variables[0], prob.variables[1], "Z"],
                    corner_points(prob, region["polygon"]))

        goal = "maksimum" if prob.maximize else "minimum"
        parts = ", ".join(f"{v} = {x:,.4g}" for v, x in zip(prob.variables, sol.x))
        binding = [n for n, s in zip(prob.constraint_names, sol.slack) if s < 1e-7]
        r.interpretation = (f"Nilai {goal} Z = {sol.objective:,.4f} dicapai pada {parts}. "
                            f"Kendala pembatas (binding): {', '.join(binding) or '-'}.")

        # Analisis mendalam
        obj_expr = " + ".join(f"({c:g}×{v})" for c, v in zip(prob.c, prob.variables))
        obj_sub = " + ".join(f"({c:g}×{x:,.4g})" for c, x in zip(prob.c, sol.x))
        r.analyze(
            "Metodologi & Verifikasi Fungsi Tujuan",
            f"Model Linear Programming ({'Maksimasi' if prob.maximize else 'Minimasi'}) dengan {len(prob.variables)} variabel keputusan "
            f"dan {len(prob.constraint_names)} kendala linear diselesaikan menggunakan algoritma Simpleks (HiGHS) dalam {sol.iterations} iterasi.",
            [
                f"Fungsi Tujuan: Z = {obj_expr}",
                f"Substitusi Solusi Optimal: Z = {obj_sub} = {sol.objective:,.4f}",
                "Seluruh variabel keputusan memenuhi syarat non-negativitas (X ≥ 0) dan seluruh kendala terpenuhi secara simultan.",
            ],
        )

        sens_bullets: list[str] = []
        for i, n in enumerate(prob.constraint_names):
            lhs_i = float(prob.A[i] @ sol.x)
            sp = float(sol.shadow_prices[i])
            sl = float(sol.slack[i])
            if sl < 1e-7:
                sens_bullets.append(
                    f"Kendala '{n}' bersifat BINDING (terpakai penuh: {lhs_i:,.4g} {prob.signs[i]} {prob.b[i]:,.4g}) "
                    f"dengan Shadow Price = {sp:,.4f} (setiap kenaikan 1 unit RHS mengubah Z sebesar {sp:+,.4f} selama basis tetap)."
                )
            else:
                kind = "sisa kapasitas (slack)" if prob.signs[i] == "<=" else "kelebihan capaian (surplus)"
                sens_bullets.append(
                    f"Kendala '{n}' bersifat NON-BINDING ({lhs_i:,.4g} {prob.signs[i]} {prob.b[i]:,.4g}) "
                    f"dengan {kind} sebesar {sl:,.4g} (Shadow Price = 0)."
                )
        non_basic = [(v, float(rc), float(c)) for v, x, rc, c in zip(prob.variables, sol.x, sol.reduced_costs, prob.c) if x < 1e-7]
        for v, rc, c in non_basic:
            if abs(rc) > 1e-7:
                direction = "ditingkatkan" if prob.maximize else "diturunkan"
                sens_bullets.append(
                    f"Variabel non-basis '{v}' bernilai 0 dengan Reduced Cost = {rc:,.4f}; koefisien tujuannya ({c:g}) "
                    f"perlu {direction} minimal {abs(rc):,.4f} agar layak masuk ke solusi optimal."
                )
        r.analyze(
            "Bedah Kendala, Slack/Surplus & Analisis Sensitivitas",
            "Shadow Price mengidentifikasi sumber daya yang benar-benar menjadi bottleneck, sedangkan Slack/Surplus menunjukkan kelonggaran kapasitas.",
            sens_bullets,
        )

        rec_bullets: list[str] = []
        ranked_sp = sorted(
            [(abs(float(sol.shadow_prices[i])), float(sol.shadow_prices[i]), prob.constraint_names[i], prob.signs[i])
             for i in range(len(prob.constraint_names)) if sol.slack[i] < 1e-7 and abs(sol.shadow_prices[i]) > 1e-7],
            reverse=True,
        )
        if ranked_sp:
            _, top_sp, top_name, top_sign = ranked_sp[0]
            aksi = "penambahan kapasitas/RHS" if (prob.maximize and top_sp > 0) or (not prob.maximize and top_sp < 0) else "pelonggaran syarat batas"
            rec_bullets.append(
                f"Prioritas ekspansi tertinggi: fokus pada '{top_name}' ({top_sign}) karena memiliki dampak marjinal terbesar "
                f"(|Shadow Price| = {abs(top_sp):,.4f} per unit {aksi})."
            )
        slack_high = [n for n, sl in zip(prob.constraint_names, sol.slack) if sl >= 1e-7]
        if slack_high:
            rec_bullets.append(
                f"Sumber daya pada {', '.join(slack_high)} masih memiliki kelonggaran (non-binding); "
                "hindari investasi tambahan di area ini sebelum bottleneck utama teratasi."
            )
        if not rec_bullets:
            rec_bullets.append("Seluruh kendala berada pada titik keseimbangan; lakukan uji sensitivitas bila koefisien biaya/harga berubah.")
        r.analyze(
            "Rekomendasi Manajerial",
            "Implikasi operasional untuk pengalokasian sumber daya dan peningkatan nilai tujuan:",
            rec_bullets,
        )
        return r
