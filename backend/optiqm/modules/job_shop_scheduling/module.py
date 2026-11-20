"""Modul Job Shop Scheduling (FCFS, SPT, LPT, EDD, Critical Ratio)."""

from __future__ import annotations

import pandas as pd

from optiqm.core import BaseModule, InputError, ModuleResult, ParamSpec, SheetData, register
from optiqm.core.parsing import clean_frame, find_column, require_rows, to_float


def _evaluate_order(jobs: list[tuple[str, float, float]], order: list[int]) -> dict:
    t = 0.0
    rows = []
    tot_flow = 0.0
    tot_proc = sum(p for _, p, _ in jobs)
    tot_late = 0.0
    max_late = 0.0
    tardy = 0
    gantt = []
    for idx in order:
        nm, proc, due = jobs[idx]
        start = t
        finish = t + proc
        late = max(0.0, finish - due)
        if late > 1e-9:
            tardy += 1
        max_late = max(max_late, late)
        tot_flow += finish
        tot_late += late
        rows.append([nm, proc, due, start, finish, late])
        gantt.append({"name": nm, "start": start, "end": finish, "highlight": late > 1e-9})
        t = finish
    n = len(jobs)
    util = (tot_proc / tot_flow * 100.0) if tot_flow > 0 else 0.0
    avg_jobs = (tot_flow / tot_proc) if tot_proc > 0 else 0.0
    return {
        "rows": rows, "gantt": gantt, "avg_completion": tot_flow / n,
        "utilization": util, "avg_jobs": avg_jobs, "avg_lateness": tot_late / n,
        "max_lateness": max_late, "tardy": tardy, "makespan": t,
    }


def _dynamic_cr_order(jobs: list[tuple[str, float, float]]) -> list[int]:
    """Dynamic Critical Ratio: pada setiap langkah t, pilih pekerjaan dengan CR = (Due - t) / Proc terkecil."""
    rem = list(range(len(jobs)))
    order: list[int] = []
    t = 0.0
    while rem:
        pick = min(
            rem,
            key=lambda i: (((jobs[i][2] - t) / jobs[i][1]) if jobs[i][1] > 0 else float("inf"), i),
        )
        order.append(pick)
        rem.remove(pick)
        t += jobs[pick][1]
    return order


@register
class JobShopScheduling(BaseModule):
    key = "job_shop_scheduling"
    name = "Job Shop Scheduling"
    category = "Penjadwalan"
    description = "Penjadwalan 1 mesin (FCFS, SPT, LPT, EDD, Critical Ratio) dan perbandingan kinerjanya."
    sheet_prefixes = ("SCHED", "JOBSHOP", "JADWAL")
    params = (
        ParamSpec("rule", "Aturan Prioritas", "choice", "spt", ("spt", "edd", "fcfs", "lpt", "cr")),
    )
    table_hint = "Kolom: Job, Processing_Time, Due_Date (opsional)."

    def template(self) -> SheetData:
        # Contoh klasik 5 job Heizer & Render
        df = pd.DataFrame(
            [["A", 6, 8], ["B", 2, 6], ["C", 8, 18], ["D", 3, 15], ["E", 9, 23]],
            columns=["Job", "Processing_Time", "Due_Date"],
        )
        return SheetData(params={"rule": "spt"}, tables={"main": df})

    def solve(self, data: SheetData) -> ModuleResult:
        p = self.resolved_params(data)
        df = clean_frame(data.table("main"))
        require_rows(df, 1, "Tabel pekerjaan")
        c_job = find_column(df, ["Job", "Pekerjaan", "Name"], required=False) or df.columns[0]
        c_pt = find_column(df, ["Processing_Time", "ProcessTime", "Time", "Waktu"])
        c_dd = find_column(df, ["Due_Date", "DueDate", "Due", "Batas"], required=False)

        jobs = []
        for i in range(len(df)):
            nm = str(df.at[i, c_job]).strip()
            pt = to_float(df.at[i, c_pt], f"Processing_Time {nm}")
            if pt < 0:
                raise InputError(f"Waktu proses '{nm}' tidak boleh negatif.")
            dd = to_float(df.at[i, c_dd], f"Due_Date {nm}") if c_dd and not pd.isna(df.at[i, c_dd]) else pt * len(df)
            jobs.append((nm, pt, dd))

        n = len(jobs)
        orders = {
            "fcfs": list(range(n)),
            "spt": sorted(range(n), key=lambda i: (jobs[i][1], i)),
            "lpt": sorted(range(n), key=lambda i: (-jobs[i][1], i)),
            "edd": sorted(range(n), key=lambda i: (jobs[i][2], i)),
            "cr": _dynamic_cr_order(jobs),
        }
        all_eval = {k: _evaluate_order(jobs, ord_) for k, ord_ in orders.items()}
        chosen = all_eval[p["rule"]]

        r = ModuleResult()
        r.metric("Rata-rata Waktu Penyelesaian", chosen["avg_completion"], highlight=True)
        r.metric("Utilisasi", f"{chosen['utilization']:.2f}%", highlight=True)
        r.metric("Rata-rata Job di Sistem", chosen["avg_jobs"])
        r.metric("Rata-rata Keterlambatan", chosen["avg_lateness"])
        r.metric("Jumlah Job Terlambat", chosen["tardy"])

        r.table(f"Urutan Jadwal ({p['rule'].upper()})",
                ["Job", "Waktu Proses", "Due Date", "Mulai", "Selesai (Flow Time)", "Keterlambatan"],
                chosen["rows"])
        r.table("Perbandingan Semua Aturan",
                ["Aturan", "Rata-rata Completion", "Utilisasi (%)", "Rata-rata Job", "Rata-rata Lateness", "Maks. Lateness", "Job Terlambat"],
                [[k.upper(), ev["avg_completion"], ev["utilization"], ev["avg_jobs"], ev["avg_lateness"], ev["max_lateness"], ev["tardy"]]
                 for k, ev in all_eval.items()])
        r.chart(f"Gantt Chart — Aturan {p['rule'].upper()}", "gantt", {"tasks": chosen["gantt"]})
        r.interpretation = (f"Urutan {p['rule'].upper()}: {' → '.join(row[0] for row in chosen['rows'])} "
                            f"(rata-rata waktu selesai {chosen['avg_completion']:.2f}, utilisasi {chosen['utilization']:.1f}%).")

        # Analisis mendalam
        best_flow = min(all_eval.items(), key=lambda kv: kv[1]["avg_completion"])
        best_late = min(all_eval.items(), key=lambda kv: (kv[1]["avg_lateness"], kv[1]["max_lateness"]))
        best_max_late = min(all_eval.items(), key=lambda kv: kv[1]["max_lateness"])
        r.analyze(
            "Metodologi Penjadwalan 1 Mesin (Priority Dispatching Rules)",
            f"Total waktu proses (Makespan) konstan = {chosen['makespan']:g} untuk seluruh urutan ({n} pekerjaan). "
            "Aturan Critical Ratio (CR) dihitung secara dinamis pada setiap waktu selesai pekerjaan: CR_i(t) = (Due_i − t) / Proc_i.",
            [
                f"Aturan aktif {p['rule'].upper()}: urutan {' → '.join(row[0] for row in chosen['rows'])}, rata-rata waktu penyelesaian = {chosen['avg_completion']:.2f}, "
                f"utilisasi = {chosen['utilization']:.2f}%, rata-rata WIP = {chosen['avg_jobs']:.2f} job.",
                f"Kinerja Ketepatan Waktu: {chosen['tardy']} dari {n} job terlambat, rata-rata keterlambatan = {chosen['avg_lateness']:.2f}, maksimum = {chosen['max_lateness']:.2f}.",
            ],
        )
        r.analyze(
            "Bedah Trade-off Antar Aturan Prioritas",
            "Tidak ada satu aturan yang unggul di semua indikator secara bersamaan — pilihan bergantung pada tujuan operasi:",
            [
                f"Terbaik untuk Flow Time, Utilisasi & WIP: {best_flow[0].upper()} (rata-rata selesai {best_flow[1]['avg_completion']:.2f}, WIP {best_flow[1]['avg_jobs']:.2f}). Secara matematis SPT selalu meminimalkan rata-rata waktu selesai.",
                f"Terbaik untuk Keterlambatan Maksimum: {best_max_late[0].upper()} (maks. lateness {best_max_late[1]['max_lateness']:.2f}). Secara matematis EDD selalu meminimalkan keterlambatan maksimum.",
                f"Terbaik untuk Rata-rata Keterlambatan: {best_late[0].upper()} (avg lateness {best_late[1]['avg_lateness']:.2f}, {best_late[1]['tardy']} job terlambat).",
            ],
        )
        r.analyze(
            "Rekomendasi Pemilihan Aturan",
            "Panduan memilih aturan dispatching di lantai produksi:",
            [
                "Gunakan SPT bila prioritas utama adalah memaksimalkan throughput, meminimalkan antrean kerja (WIP), dan menjaga utilisasi tetap tinggi.",
                "Gunakan EDD atau Critical Ratio (CR) dinamis bila penalti keterlambatan due date / kontrak SLA pelanggan sangat mahal.",
                "Hindari LPT untuk pekerjaan ber-due date ketat karena cenderung menunda pekerjaan pendek dan meningkatkan WIP.",
            ],
        )
        return r
