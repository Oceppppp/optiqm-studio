"""Modul Assignment Problem (Metode Hungarian)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from optiqm.core import BaseModule, InputError, ModuleResult, ParamSpec, SheetData, SolverError, Table, register
from optiqm.core.parsing import clean_frame, require_rows, to_float

from .solver import hungarian_solve


@register
class Assignment(BaseModule):
    key = "assignment"
    name = "Assignment"
    category = "Distribusi & Jaringan"
    description = "Penugasan optimal 1-ke-1 antara pekerja/mesin dan tugas menggunakan Metode Hungarian."
    sheet_prefixes = ("ASSIGN", "PENUGASAN")
    params = (ParamSpec("objective", "Tujuan", "choice", "min", ("min", "max")),)
    table_hint = "Kolom pertama: nama agen/pekerja. Kolom berikutnya: biaya/skor untuk setiap tugas."

    def template(self) -> SheetData:
        # Contoh Fix-It Shop (Heizer & Render) -> biaya optimal $25
        df = pd.DataFrame(
            [["Adams", 11, 14, 6],
             ["Brown", 8, 10, 11],
             ["Cooper", 9, 12, 7]],
            columns=["Worker", "Project 1", "Project 2", "Project 3"],
        )
        return SheetData(params={"objective": "min"}, tables={"main": df})

    def solve(self, data: SheetData) -> ModuleResult:
        p = self.resolved_params(data)
        maximize = p["objective"] == "max"
        df = clean_frame(data.table("main"))
        require_rows(df, 1, "Tabel penugasan")
        name_col = df.columns[0]
        tasks = list(df.columns[1:])
        if not tasks:
            raise InputError("Minimal harus ada 1 kolom tugas.")
        workers = [str(x).strip() for x in df[name_col]]
        m, n = len(workers), len(tasks)

        cost = np.zeros((m, n))
        prohibited = np.zeros((m, n), dtype=bool)
        for i in range(m):
            for j, t in enumerate(tasks):
                v = df.at[i, t]
                if isinstance(v, str) and v.strip().upper() in {"X", "M", "-", "NA"}:
                    prohibited[i, j] = True
                else:
                    cost[i, j] = to_float(v, f"{workers[i]}->{t}")

        if prohibited.any():
            big = (np.abs(cost[~prohibited]).max(initial=1.0) + 1.0) * 1e5
            solve_cost = np.where(prohibited, -big if maximize else big, cost)
        else:
            solve_cost = cost

        pairs, steps = hungarian_solve(solve_cost, maximize=maximize)
        for i, j in pairs:
            if i < m and j < n and prohibited[i, j]:
                raise SolverError("Tidak ada penugasan 1-ke-1 yang layak tanpa melewati pasangan terlarang.")

        r = ModuleResult()
        if m != n:
            r.warnings.append(f"Matriks tidak persegi ({m}×{n}): ditambahkan baris/kolom Dummy bernilai 0.")

        total_val = 0.0
        rows_out = []
        w_labels = workers + [f"Dummy {k + 1}" for k in range(max(0, n - m))]
        t_labels = tasks + [f"Dummy {k + 1}" for k in range(max(0, m - n))]
        for i, j in pairs:
            val = float(cost[i, j]) if i < m and j < n else 0.0
            total_val += val
            rows_out.append([w_labels[i], t_labels[j], val, "Dummy" if (i >= m or j >= n) else "Aktif"])

        r.metric("Total Optimal" if maximize else "Total Biaya Minimum", total_val, highlight=True)
        r.metric("Jumlah Penugasan Aktif", sum(1 for row in rows_out if row[3] == "Aktif"))
        r.table("Penugasan Optimal", ["Pekerja/Mesin", "Tugas", "Biaya/Nilai", "Status"], rows_out)

        for title, mat in steps:
            r.steps.append(Table(title, ["Baris \\ Kolom", *t_labels],
                                 [[w_labels[i], *mat[i].tolist()] for i in range(len(w_labels))]))
        r.interpretation = "; ".join(f"{row[0]} → {row[1]} ({row[2]:g})" for row in rows_out if row[3] == "Aktif")

        # Analisis mendalam
        active = [row for row in rows_out if row[3] == "Aktif"]
        valid_cells = cost[~prohibited]
        avg_cell = float(valid_cells.mean()) if len(valid_cells) else 0.0
        expected_random = avg_cell * len(active)
        gain_vs_avg = (total_val - expected_random) if maximize else (expected_random - total_val)
        pct_vs_avg = (gain_vs_avg / abs(expected_random) * 100.0) if abs(expected_random) > 1e-12 else 0.0
        sum_expr = " + ".join(f"{row[2]:g}" for row in active)
        r.analyze(
            "Metodologi Algoritma Hungarian (Penugasan 1-ke-1)",
            f"Matriks {m} agen × {n} tugas diselesaikan dengan Metode Hungarian ({'Maksimasi via Opportunity Loss' if maximize else 'Minimasi langsung'}) "
            "melalui reduksi baris, reduksi kolom, dan pencarian alokasi nol independen optimal.",
            [
                f"Verifikasi Total: {sum_expr} = {total_val:,.4f} untuk {len(active)} penugasan aktif.",
                f"Perbandingan terhadap penugasan rata-rata acak ({expected_random:,.2f}): solusi optimal memberikan "
                f"{'peningkatan nilai' if maximize else 'penghematan biaya'} sebesar {gain_vs_avg:,.2f} ({pct_vs_avg:.1f}%).",
            ],
        )

        # Analisis kesesuaian tiap agen terhadap pilihan terbaik individunya
        fit_bullets: list[str] = []
        compromises = []
        for i, j in pairs:
            if i < m and j < n:
                avail = cost[i, ~prohibited[i]]
                best_ind = float(avail.max() if maximize else avail.min())
                val = float(cost[i, j])
                gap = (best_ind - val) if maximize else (val - best_ind)
                if gap <= 1e-9:
                    fit_bullets.append(f"{workers[i]} → {tasks[j]} ({val:g}): mendapat pilihan terbaik pribadinya (gap = 0).")
                else:
                    compromises.append((gap, workers[i], tasks[j]))
                    fit_bullets.append(
                        f"{workers[i]} → {tasks[j]} ({val:g}): selisih {gap:g} dari pilihan terbaik pribadinya ({best_ind:g}) "
                        "demi optimalitas global seluruh tim."
                    )
        r.analyze(
            "Bedah Kesesuaian Agen & Trade-off Global",
            "Penugasan optimal global terkadang tidak menempatkan setiap agen pada tugas terbaik pribadinya agar menghindari konflik di tugas yang sama.",
            fit_bullets,
        )

        rec_bullets = []
        if compromises:
            top_c = max(compromises, key=lambda x: x[0])
            rec_bullets.append(
                f"Fokus peningkatan kapabilitas: {top_c[1]} pada tugas '{top_c[2]}' menanggung kompromi terbesar ({top_c[0]:g}); "
                "pelatihan silang (cross-training) pada pasangan ini berpotensi menurunkan total biaya tim."
            )
        else:
            rec_bullets.append("Seluruh agen menempati tugas terbaik individunya tanpa konflik—struktur kompetensi tim sangat saling melengkapi.")
        if m != n:
            idle_label = "pekerja/mesin yang menganggur" if m > n else "tugas yang belum terisi"
            rec_bullets.append(f"Karena dimensi matriks tidak persegi ({m}×{n}), terdapat {abs(m - n)} {idle_label} (dipasangkan ke Dummy).")
        r.analyze("Rekomendasi Penugasan", "Implikasi manajerial hasil penugasan:", rec_bullets)
        return r
