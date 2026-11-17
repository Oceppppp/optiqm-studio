"""Modul Assignment Problem (Metode Hungarian)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from optiqm.core import BaseModule, InputError, ModuleResult, ParamSpec, SheetData, Table, register
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
        for i in range(m):
            for j, t in enumerate(tasks):
                v = df.at[i, t]
                if isinstance(v, str) and v.strip().upper() in {"X", "M", "-"}:
                    cost[i, j] = -1e9 if maximize else 1e9
                else:
                    cost[i, j] = to_float(v, f"{workers[i]}->{t}")

        pairs, steps = hungarian_solve(cost, maximize=maximize)
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
        return r
