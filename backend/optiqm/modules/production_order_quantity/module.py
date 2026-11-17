"""Modul Production Order Quantity (POQ / EPQ)."""

from __future__ import annotations

import math

import pandas as pd

from optiqm.core import BaseModule, InputError, ModuleResult, ParamSpec, SheetData, register


@register
class ProductionOrderQuantity(BaseModule):
    key = "production_order_quantity"
    name = "Production Order Quantity (POQ)"
    category = "Persediaan"
    description = "Ukuran lot produksi optimal ketika barang diproduksi dan digunakan secara bersamaan (p > d)."
    sheet_prefixes = ("POQ", "EPQ")
    params = (
        ParamSpec("D", "Permintaan Tahunan (D)", "number", 1000.0),
        ParamSpec("S", "Biaya Setup per Run (S)", "number", 10.0),
        ParamSpec("H", "Biaya Simpan per Unit/Thn (H)", "number", 0.5),
        ParamSpec("prod_rate", "Laju Produksi Harian (p)", "number", 8.0),
        ParamSpec("demand_rate", "Laju Permintaan Harian (d)", "number", 4.0),
    )
    table_hint = "Atur D, S, H, prod_rate (laju produksi harian), demand_rate (laju permintaan harian) pada parameter."

    def template(self) -> SheetData:
        # Nathan Manufacturing (Heizer & Render): D=1000, S=10, H=0.5, p=8, d=4 -> Q*=282.84
        return SheetData(
            params={"D": 1000, "S": 10, "H": 0.5, "prod_rate": 8, "demand_rate": 4},
            tables={"main": pd.DataFrame([["D", 1000], ["S", 10], ["H", 0.5], ["prod_rate", 8], ["demand_rate", 4]],
                                         columns=["Parameter", "Value"])},
        )

    def solve(self, data: SheetData) -> ModuleResult:
        par = self.resolved_params(data)
        D, S, H = float(par["D"]), float(par["S"]), float(par["H"])
        p_rate, d_rate = float(par["prod_rate"]), float(par["demand_rate"])
        if D <= 0 or S <= 0 or H <= 0 or p_rate <= 0 or d_rate <= 0:
            raise InputError("Semua parameter (D, S, H, p, d) harus > 0.")
        if d_rate >= p_rate:
            raise InputError("Laju produksi (p) harus lebih besar daripada laju permintaan (d).")

        factor = 1.0 - d_rate / p_rate
        q_star = math.sqrt((2.0 * D * S) / (H * factor))
        max_inv = q_star * factor
        avg_inv = max_inv / 2.0
        setup_cost = (D / q_star) * S
        hold_cost = avg_inv * H
        total_cost = setup_cost + hold_cost
        run_len = q_star / p_rate

        r = ModuleResult()
        r.metric("Lot Produksi Optimal (Qp*)", q_star, unit="unit", highlight=True)
        r.metric("Total Biaya Persediaan", total_cost, highlight=True)
        r.metric("Persediaan Maksimum", max_inv, unit="unit")
        r.metric("Lama 1 Siklus Produksi", run_len, unit="hari")
        r.table("Ringkasan POQ", ["Metrik", "Nilai"], [
            ["Ukuran Lot Optimal (Qp*)", q_star],
            ["Persediaan Maksimum", max_inv],
            ["Rata-rata Persediaan", avg_inv],
            ["Jumlah Setup / Tahun", D / q_star],
            ["Biaya Setup Tahunan", setup_cost],
            ["Biaya Simpan Tahunan", hold_cost],
            ["Total Biaya (Setup + Simpan)", total_cost],
        ])
        r.interpretation = f"Lot produksi optimal Qp* = {q_star:,.2f} unit (stok maks {max_inv:,.2f}, total biaya {total_cost:,.2f})."
        return r
