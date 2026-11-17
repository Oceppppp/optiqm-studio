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
    tardy = 0
    gantt = []
    for idx in order:
        nm, proc, due = jobs[idx]
        start = t
        finish = t + proc
        late = max(0.0, finish - due)
        if late > 1e-9:
            tardy += 1
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
        "tardy": tardy, "makespan": t,
    }


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
            "cr": sorted(range(n), key=lambda i: (jobs[i][2] / jobs[i][1] if jobs[i][1] > 0 else float("inf"), i)),
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
                ["Aturan", "Rata-rata Completion", "Utilisasi (%)", "Rata-rata Job", "Rata-rata Lateness", "Job Terlambat"],
                [[k.upper(), ev["avg_completion"], ev["utilization"], ev["avg_jobs"], ev["avg_lateness"], ev["tardy"]]
                 for k, ev in all_eval.items()])
        r.chart(f"Gantt Chart — Aturan {p['rule'].upper()}", "gantt", {"tasks": chosen["gantt"]})
        r.interpretation = (f"Urutan {p['rule'].upper()}: {' → '.join(row[0] for row in chosen['rows'])} "
                            f"(rata-rata waktu selesai {chosen['avg_completion']:.2f}, utilisasi {chosen['utilization']:.1f}%).")
        return r
