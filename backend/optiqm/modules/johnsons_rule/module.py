"""Modul Johnson's Rule (Flow Shop 2 Mesin — minimasi Makespan)."""

from __future__ import annotations

import pandas as pd

from optiqm.core import BaseModule, InputError, ModuleResult, SheetData, register
from optiqm.core.parsing import clean_frame, find_column, require_rows, to_float


@register
class JohnsonsRule(BaseModule):
    key = "johnsons_rule"
    name = "Johnson's Rule (2 Mesin)"
    category = "Penjadwalan"
    description = "Mengurutkan pekerjaan pada dua stasiun/mesin berurutan untuk meminimalkan total waktu selesai (Makespan)."
    sheet_prefixes = ("JOHNSON", "FLOWSHOP")
    table_hint = "Kolom: Job, Machine_1 (waktu di mesin 1), Machine_2 (waktu di mesin 2)."

    def template(self) -> SheetData:
        # Contoh klasik 5 job Heizer & Render: A(5,2), B(3,6), C(8,4), D(10,7), E(7,12) -> makespan=35
        df = pd.DataFrame(
            [["A", 5, 2], ["B", 3, 6], ["C", 8, 4], ["D", 10, 7], ["E", 7, 12]],
            columns=["Job", "Machine_1", "Machine_2"],
        )
        return SheetData(tables={"main": df})

    def solve(self, data: SheetData) -> ModuleResult:
        df = clean_frame(data.table("main"))
        require_rows(df, 1, "Tabel pekerjaan 2 mesin")
        c_job = find_column(df, ["Job", "Pekerjaan", "Name"], required=False) or df.columns[0]
        c_m1 = find_column(df, ["Machine_1", "M1", "Mesin1", "Center1"])
        c_m2 = find_column(df, ["Machine_2", "M2", "Mesin2", "Center2"])

        jobs = [(str(df.at[i, c_job]).strip(), to_float(df.at[i, c_m1], "M1"), to_float(df.at[i, c_m2], "M2"))
                for i in range(len(df))]
        for nm, t1, t2 in jobs:
            if t1 < 0 or t2 < 0:
                raise InputError(f"Waktu proses '{nm}' tidak boleh negatif.")

        front, back = [], []
        rem = list(jobs)
        while rem:
            best = min(rem, key=lambda j: min(j[1], j[2]))
            rem.remove(best)
            if best[1] <= best[2]:
                front.append(best)
            else:
                back.insert(0, best)
        seq = front + back

        t1 = t2 = 0.0
        rows_out = []
        tasks = []
        for nm, p1, p2 in seq:
            s1, e1 = t1, t1 + p1
            s2 = max(e1, t2)
            e2 = s2 + p2
            rows_out.append([nm, p1, p2, s1, e1, s2, e2, max(0.0, e1 - t2)])
            tasks.append({"name": f"{nm} (M1)", "start": s1, "end": e1, "highlight": False})
            tasks.append({"name": f"{nm} (M2)", "start": s2, "end": e2, "highlight": True})
            t1, t2 = e1, e2

        idle_m2 = sum(row[7] for row in rows_out)
        r = ModuleResult()
        r.metric("Makespan (Total Waktu Selesai)", t2, highlight=True)
        r.metric("Urutan Optimal", " → ".join(j[0] for j in seq), highlight=True)
        r.metric("Total Idle Mesin 2", idle_m2)
        r.table("Jadwal Flow Shop Optimal",
                ["Job", "Proses M1", "Proses M2", "Mulai M1", "Selesai M1", "Mulai M2", "Selesai M2", "Idle M2"],
                rows_out)
        r.chart("Gantt Chart — Mesin 1 & Mesin 2", "gantt", {"tasks": tasks})
        r.interpretation = f"Urutan optimal Johnson's Rule: {' → '.join(j[0] for j in seq)} dengan makespan = {t2:g}."
        return r
