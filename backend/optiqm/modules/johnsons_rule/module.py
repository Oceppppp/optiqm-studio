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

        # Analisis mendalam
        sum_m1 = sum(j[1] for j in seq)
        sum_m2 = sum(j[2] for j in seq)
        util_m1 = (sum_m1 / t2 * 100.0) if t2 > 0 else 0.0
        util_m2 = (sum_m2 / t2 * 100.0) if t2 > 0 else 0.0
        idle_m1_end = max(0.0, t2 - sum_m1)
        # Hitung makespan urutan awal (FCFS) untuk pembanding
        fcfs_t1 = fcfs_t2 = 0.0
        for _, p1, p2 in jobs:
            fcfs_t1 += p1
            fcfs_t2 = max(fcfs_t1, fcfs_t2) + p2
        saved = max(0.0, fcfs_t2 - t2)
        lower_bound = max(sum_m1 + min(j[2] for j in jobs), sum_m2 + min(j[1] for j in jobs))
        r.analyze(
            "Metodologi Johnson's Rule (Flow Shop 2 Mesin)",
            f"Sebanyak {len(jobs)} pekerjaan dijadwalkan melewati Mesin 1 lalu Mesin 2 secara berurutan. "
            "Algoritma Johnson menempatkan pekerjaan dengan waktu terkecil di M1 ke awal urutan dan waktu terkecil di M2 ke akhir urutan, "
            "yang secara matematis menjamin Makespan minimum global.",
            [
                f"Urutan Optimal: {' → '.join(j[0] for j in seq)} menghasilkan Makespan = {t2:g} (batas bawah teoretis = {lower_bound:g}).",
                f"Penghematan dibanding urutan awal tabel (FCFS = {fcfs_t2:g}): menghemat {saved:g} satuan waktu ({(saved / fcfs_t2 * 100.0) if fcfs_t2 > 0 else 0:.1f}%).",
            ],
        )
        bottleneck = "Mesin 1" if sum_m1 >= sum_m2 else "Mesin 2"
        r.analyze(
            "Bedah Utilisasi Mesin & Waktu Menganggur (Idle Time)",
            "Keseimbangan beban kerja antara Mesin 1 dan Mesin 2 menentukan seberapa lama mesin harus menunggu pekerjaan:",
            [
                f"Mesin 1: total waktu kerja = {sum_m1:g}, selesai di t = {t1:g}, utilisasi = {util_m1:.1f}%, idle di akhir = {idle_m1_end:g}.",
                f"Mesin 2: total waktu kerja = {sum_m2:g}, selesai di t = {t2:g}, utilisasi = {util_m2:.1f}%, total idle = {idle_m2:g} (termasuk tunggu awal {rows_out[0][7]:g} dari job '{seq[0][0]}').",
                f"Mesin pembatas kapasitas (bottleneck): {bottleneck} (beban {max(sum_m1, sum_m2):g} vs {min(sum_m1, sum_m2):g}).",
            ],
        )
        r.analyze(
            "Rekomendasi Penjadwalan Lantai Produksi",
            "Langkah eksekusi jadwal flow shop:",
            [
                f"Jalankan urutan tepat {' → '.join(j[0] for j in seq)} pada kedua mesin agar total waktu selesai tidak melampaui {t2:g}.",
                f"Untuk memangkas makespan lebih lanjut di bawah {t2:g}, fokuskan percepatan proses pada {bottleneck} dan job awal '{seq[0][0]}' (yang menunda start Mesin 2) atau job akhir '{seq[-1][0]}' (ekor M2 = {seq[-1][2]:g}).",
            ],
        )
        return r
