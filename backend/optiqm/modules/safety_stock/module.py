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
        )

    def solve(self, data: SheetData) -> ModuleResult:
        p = self.resolved_params_with_table(data)
        sl = float(p["service_level"])
        sl = sl / 100.0 if sl > 1.0 else sl
        if not (0.5 <= sl < 1.0):
            raise InputError("Service level harus antara 50% dan <100%.")
        z = float(norm.ppf(sl))
        d, sd, L, sL = float(p["mean_demand"]), float(p["sigma_demand"]), float(p["mean_lt"]), float(p["sigma_lt"])
        hc = float(p["holding_cost"])
        if d < 0 or sd < 0 or L < 0 or sL < 0 or hc < 0:
            raise InputError("Permintaan, simpangan baku, lead time, dan biaya simpan tidak boleh negatif.")
        mdl = p["model"]

        if mdl == "lead_time_demand_known":
            exp_lt_d = d
            sigma_lt_d = sd
            formula_desc = f"Distribusi permintaan selama lead time diketahui langsung: μ_dLT = {d:g}, σ_dLT = {sd:g}."
        elif mdl == "demand_variable_lt_constant":
            exp_lt_d = d * L
            sigma_lt_d = math.sqrt(L) * sd
            formula_desc = f"Permintaan harian acak, lead time konstan: μ_dLT = d·L = {d:g}×{L:g} = {exp_lt_d:,.2f}; σ_dLT = √L·σ_d = √{L:g}×{sd:g} = {sigma_lt_d:,.3f}."
        elif mdl == "demand_constant_lt_variable":
            exp_lt_d = d * L
            sigma_lt_d = d * sL
            formula_desc = f"Permintaan harian konstan, lead time acak: μ_dLT = d·L = {exp_lt_d:,.2f}; σ_dLT = d·σ_LT = {d:g}×{sL:g} = {sigma_lt_d:,.3f}."
        else:
            exp_lt_d = d * L
            sigma_lt_d = math.sqrt(L * (sd ** 2) + (d ** 2) * (sL ** 2))
            formula_desc = f"Permintaan & lead time keduanya acak: σ_dLT = √(L·σ_d² + d²·σ_LT²) = {sigma_lt_d:,.3f}."

        ss = z * sigma_lt_d
        rop = exp_lt_d + ss
        hold = ss * hc

        r = ModuleResult()
        r.metric("Reorder Point (ROP)", rop, unit="unit", highlight=True)
        r.metric("Safety Stock", ss, unit="unit", highlight=True)
        r.metric("Nilai Z", z)
        r.metric("Rata-rata Permintaan saat LT", exp_lt_d, unit="unit")
        if hold > 0:
            r.metric("Biaya Simpan Safety Stock/Thn", hold)
        r.table("Rincian Perhitungan", ["Komponen", "Nilai"], [
            ["Service Level", f"{sl * 100:.2f}%"],
            ["Risiko Stockout (1 − SL)", f"{(1 - sl) * 100:.2f}%"],
            ["Z-score", z],
            ["Rata-rata Permintaan selama Lead Time", exp_lt_d],
            ["Simpangan Baku selama Lead Time (σ_dLT)", sigma_lt_d],
            ["Safety Stock (Z · σ_dLT)", ss],
            ["Reorder Point (ROP)", rop],
        ])
        r.interpretation = f"Untuk service level {sl * 100:.1f}% (Z={z:.3f}), siapkan Safety Stock {ss:,.2f} unit dan pesan ulang saat stok ≤ {rop:,.2f} unit."

        # Analisis mendalam
        r.analyze(
            "Metodologi & Rumus Safety Stock Probabilistik",
            f"{formula_desc} Dengan asumsi normalitas permintaan selama lead time, faktor pengaman ditentukan oleh kuantil distribusi normal baku Z = Φ⁻¹(SL).",
            [
                f"Z-score pada Service Level {sl * 100:.2f}% (risiko stockout {(1 - sl) * 100:.2f}%) = {z:.4f}.",
                f"Safety Stock (SS) = Z × σ_dLT = {z:.4f} × {sigma_lt_d:,.3f} = {ss:,.2f} unit.",
                f"Reorder Point (ROP) = μ_dLT + SS = {exp_lt_d:,.2f} + {ss:,.2f} = {rop:,.2f} unit"
                + (f" (biaya simpan SS = {hold:,.2f}/tahun)." if hold > 0 else "."),
            ],
        )

        sens_bullets = []
        for target_sl in (0.90, 0.95, 0.98, 0.99, 0.995):
            zt = float(norm.ppf(target_sl))
            sst = zt * sigma_lt_d
            ropt = exp_lt_d + sst
            cost_txt = f", biaya simpan = {sst * hc:,.2f}/thn" if hc > 0 else ""
            sens_bullets.append(f"SL {target_sl * 100:.1f}% (Z={zt:.3f}): SS = {sst:,.2f} unit, ROP = {ropt:,.2f} unit{cost_txt}.")
        r.analyze(
            "Sensitivitas Service Level vs Kebutuhan Safety Stock",
            "Meningkatkan service level mendekati 100% menaikkan kebutuhan safety stock secara non-linear (kurva Z semakin curam di ekor distribusi):",
            sens_bullets,
        )

        rec_bullets = [
            f"Picu pesanan ulang begitu posisi stok turun ke ≤ {rop:,.1f} unit (termasuk cadangan penyangga {ss:,.1f} unit).",
            f"Evaluasi keseimbangan biaya: menaikkan SL dari 95% ke 99% meningkatkan Safety Stock sebesar {(norm.ppf(0.99)/norm.ppf(0.95) - 1)*100:.1f}% — pastikan biaya stockout (kehilangan penjualan/denda) memang membenarkannya.",
        ]
        if mdl == "both_variable" and sigma_lt_d > 0:
            v_dem = L * (sd ** 2)
            v_lt = (d ** 2) * (sL ** 2)
            tot_v = v_dem + v_lt
            if tot_v > 0:
                dom = "variabilitas lead time pemasok" if v_lt > v_dem else "fluktuasi permintaan pelanggan"
                rec_bullets.append(
                    f"Sumber ketidakpastian dominan berasal dari {dom} "
                    f"(porsi variansi: permintaan {v_dem / tot_v * 100:.1f}% vs lead time {v_lt / tot_v * 100:.1f}%)."
                )
        r.analyze("Rekomendasi Pengendalian Risiko Stockout", "Langkah efisiensi cadangan pengaman:", rec_bullets)
        return r
