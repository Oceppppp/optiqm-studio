"""Modul Waiting Lines (Teori Antrian)."""

from __future__ import annotations

import pandas as pd

from optiqm.core import BaseModule, InputError, ModuleResult, ParamSpec, SheetData, register

from .solver import md1, mm1, mm1_finite, mms


@register
class WaitingLines(BaseModule):
    key = "waiting_lines"
    name = "Waiting Lines (Antrian)"
    category = "Antrian"
    description = "Analisis kinerja sistem antrian (M/M/1, M/M/s, M/D/1, M/M/1 Populasi Terbatas) + analisis biaya."
    sheet_prefixes = ("QUEUE", "ANTRIAN", "WAIT")
    params = (
        ParamSpec("model", "Model Antrian", "choice", "mm1", ("mm1", "mms", "md1", "mm1_finite_population")),
        ParamSpec("arrival_rate", "Laju Kedatangan (λ)", "number", 2.0),
        ParamSpec("service_rate", "Laju Layanan per Server (μ)", "number", 3.0),
        ParamSpec("servers", "Jumlah Server (s, untuk M/M/s)", "integer", 1),
        ParamSpec("population", "Ukuran Populasi (N, untuk Finite)", "integer", 10),
        ParamSpec("waiting_cost", "Biaya Menunggu / Unit / Waktu (Cw)", "number", 0.0),
        ParamSpec("server_cost", "Biaya Server / Waktu (Cs)", "number", 0.0),
    )
    table_hint = "Atur parameter λ, μ, jumlah server s, atau isi tabel [main] dengan kolom Parameter | Value."

    def template(self) -> SheetData:
        # Arnold's Muffler Shop (Heizer & Render): λ=2/jam, μ=3/jam -> L=2, Lq=4/3, W=1, Wq=2/3
        return SheetData(
            params={"model": "mm1", "arrival_rate": 2, "service_rate": 3, "servers": 1,
                    "population": 10, "waiting_cost": 15, "server_cost": 10},
            tables={"main": pd.DataFrame([["arrival_rate", 2], ["service_rate", 3], ["servers", 1]],
                                         columns=["Parameter", "Value"])},
        )

    def solve(self, data: SheetData) -> ModuleResult:
        p = self.resolved_params(data)
        lam, mu = float(p["arrival_rate"]), float(p["service_rate"])
        s, N = int(p["servers"]), int(p["population"])
        if lam <= 0 or mu <= 0:
            raise InputError("Laju kedatangan (λ) dan laju layanan (μ) harus > 0.")

        mdl = p["model"]
        if mdl == "mm1":
            res = mm1(lam, mu); eff_s = 1
        elif mdl == "mms":
            res = mms(lam, mu, s); eff_s = s
        elif mdl == "md1":
            res = md1(lam, mu); eff_s = 1
        else:
            res = mm1_finite(lam, mu, N); eff_s = 1

        cw, cs = float(p["waiting_cost"]), float(p["server_cost"])
        total_cost = res["l"] * cw + eff_s * cs

        r = ModuleResult()
        r.metric("Utilisasi Server (ρ)", f"{res['rho'] * 100:.2f}%", highlight=True)
        r.metric("Rata-rata dalam Sistem (L)", res["l"])
        r.metric("Rata-rata Antri (Lq)", res["lq"])
        r.metric("Waktu dalam Sistem (W)", res["w"])
        r.metric("Waktu Tunggu Antri (Wq)", res["wq"], highlight=True)
        if cw > 0 or cs > 0:
            r.metric("Total Biaya / Satuan Waktu", total_cost)

        r.table("Metrik Kinerja Antrian", ["Parameter", "Nilai"], [
            ["Utilisasi Sistem (ρ)", res["rho"]],
            ["P(0) — Sistem Kosong", res["p0"]],
            ["P(w) — Pelanggan Harus Menunggu", res["pw"]],
            ["Rata-rata Pelanggan dalam Antrian (Lq)", res["lq"]],
            ["Rata-rata Pelanggan dalam Sistem (L)", res["l"]],
            ["Rata-rata Waktu Tunggu di Antrian (Wq)", res["wq"]],
            ["Rata-rata Waktu di Sistem (W)", res["w"]],
            ["Total Biaya (L·Cw + s·Cs)", total_cost],
        ])

        if res["pn"]:
            cum = 0.0
            p_rows = []
            for n, pn in enumerate(res["pn"]):
                cum += pn
                p_rows.append([n, pn, cum])
            r.table("Distribusi Probabilitas P(n)", ["n Pelanggan", "P(n)", "Kumulatif P(≤ n)"], p_rows)
            r.chart("Distribusi Probabilitas Jumlah Pelanggan P(n)", "bar", {
                "x": [str(n) for n in range(len(res["pn"]))],
                "series": [{"name": "P(n)", "data": res["pn"]}],
                "x_label": "Jumlah Pelanggan (n)", "y_label": "Probabilitas",
            })
        r.interpretation = (f"Model {mdl.upper()}: utilisasi server {res['rho']*100:.1f}%, "
                            f"rata-rata antrean Lq = {res['lq']:.3f} unit dengan waktu tunggu Wq = {res['wq']:.4f}.")
        return r
