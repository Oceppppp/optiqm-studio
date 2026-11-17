"""Modul Safety Stock & Reorder Point (permintaan/lead time probabilistik)."""

from __future__ import annotations

import math

import pandas as pd
from scipy.stats import norm

from optiqm.core import BaseModule, InputError, ModuleResult, ParamSpec, SheetData, register


@register
class SafetyStock(BaseModule):
    key = "safety_stock"
    name = "Safety Stock & ROP"
    category = "Persediaan"
    description = "Menghitung Safety Stock dan Reorder Point (ROP) untuk tingkat layanan (service level) tertentu."
    sheet_prefixes = ("SS", "SAFETY", "ROP")
    params = (
        ParamSpec("model", "Model Ketidakpastian", "choice", "lead_time_demand_known",
                  ("lead_time_demand_known", "demand_variable_lt_constant", "demand_constant_lt_variable", "both_variable")),
        ParamSpec("service_level", "Service Level (%)", "number", 95.0),
        ParamSpec("mean_demand", "Rata-rata Permintaan (harian, atau saat LT utk model 1)", "number", 350.0),
        ParamSpec("sigma_demand", "Simpangan Baku Permintaan (σ_d)", "number", 10.0),
        ParamSpec("mean_lt", "Rata-rata Lead Time (hari)", "number", 1.0),
        ParamSpec("sigma_lt", "Simpangan Baku Lead Time (σ_LT, hari)", "number", 0.0),
        ParamSpec("holding_cost", "Biaya Simpan per Unit/Thn (opsional)", "number", 0.0),
    )
    table_hint = "Masukkan parameter permintaan, standar deviasi, lead time, dan service level (%)."

    def template(self) -> SheetData:
        # Memphis Regional Hospital (Heizer & Render): mean LT demand=350, sigma=10, SL=95% -> z=1.645, SS=16.45, ROP=366.45
        return SheetData(
            params={"model": "lead_time_demand_known", "service_level": 95, "mean_demand": 350,
                    "sigma_demand": 10, "mean_lt": 1, "sigma_lt": 0, "holding_cost": 5},
            tables={"main": pd.DataFrame([["service_level", 95], ["mean_demand", 350], ["sigma_demand", 10]],
                                         columns=["Parameter", "Value"])},
        )

    def solve(self, data: SheetData) -> ModuleResult:
        p = self.resolved_params(data)
        sl = float(p["service_level"])
        sl = sl / 100.0 if sl > 1.0 else sl
        if not (0.5 <= sl < 1.0):
            raise InputError("Service level harus antara 50% dan <100%.")
        z = float(norm.ppf(sl))
        d, sd, L, sL = float(p["mean_demand"]), float(p["sigma_demand"]), float(p["mean_lt"]), float(p["sigma_lt"])
        mdl = p["model"]

        if mdl == "lead_time_demand_known":
            exp_lt_d = d
            sigma_lt_d = sd
        elif mdl == "demand_variable_lt_constant":
            exp_lt_d = d * L
            sigma_lt_d = math.sqrt(L) * sd
        elif mdl == "demand_constant_lt_variable":
            exp_lt_d = d * L
            sigma_lt_d = d * sL
        else:
            exp_lt_d = d * L
            sigma_lt_d = math.sqrt(L * (sd ** 2) + (d ** 2) * (sL ** 2))

        ss = z * sigma_lt_d
        rop = exp_lt_d + ss
        hold = ss * float(p["holding_cost"])

        r = ModuleResult()
        r.metric("Reorder Point (ROP)", rop, unit="unit", highlight=True)
        r.metric("Safety Stock", ss, unit="unit", highlight=True)
        r.metric("Nilai Z", z)
        r.metric("Rata-rata Permintaan saat LT", exp_lt_d, unit="unit")
        if hold > 0:
            r.metric("Biaya Simpan Safety Stock/Thn", hold)
        r.table("Rincian Perhitungan", ["Komponen", "Nilai"], [
            ["Service Level", f"{sl * 100:.2f}%"],
            ["Z-score", z],
            ["Rata-rata Permintaan selama Lead Time", exp_lt_d],
            ["Simpangan Baku selama Lead Time (σ_dLT)", sigma_lt_d],
            ["Safety Stock (Z · σ_dLT)", ss],
            ["Reorder Point (ROP)", rop],
        ])
        r.interpretation = f"Untuk service level {sl * 100:.1f}% (Z={z:.3f}), siapkan Safety Stock {ss:,.2f} unit dan pesan ulang saat stok ≤ {rop:,.2f} unit."
        return r
