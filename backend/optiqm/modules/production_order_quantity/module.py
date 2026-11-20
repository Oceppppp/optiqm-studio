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
        )

    def solve(self, data: SheetData) -> ModuleResult:
        par = self.resolved_params_with_table(data)
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
        cycle_len = q_star / d_rate
        depletion_len = max_inv / d_rate
        eoq_ref = math.sqrt(2.0 * D * S / H)
        eoq_cost = math.sqrt(2.0 * D * S * H)

        r = ModuleResult()
        r.metric("Lot Produksi Optimal (Qp*)", q_star, unit="unit", highlight=True)
        r.metric("Total Biaya Persediaan", total_cost, highlight=True)
        r.metric("Persediaan Maksimum", max_inv, unit="unit")
        r.metric("Lama 1 Siklus Produksi", run_len, unit="hari")
        r.table("Ringkasan POQ", ["Metrik", "Nilai"], [
            ["Ukuran Lot Optimal (Qp*)", q_star],
            ["Persediaan Maksimum (I_max)", max_inv],
            ["Rata-rata Persediaan (I_max/2)", avg_inv],
            ["Jumlah Setup / Tahun", D / q_star],
            ["Lama Run Produksi (t_p = Qp*/p)", run_len],
            ["Lama Fase Konsumsi Murni (I_max/d)", depletion_len],
            ["Total Panjang Siklus (Qp*/d)", cycle_len],
            ["Biaya Setup Tahunan", setup_cost],
            ["Biaya Simpan Tahunan", hold_cost],
            ["Total Biaya (Setup + Simpan)", total_cost],
        ])
        r.interpretation = f"Lot produksi optimal Qp* = {q_star:,.2f} unit (stok maks {max_inv:,.2f}, total biaya {total_cost:,.2f})."

        # Analisis mendalam
        util_pct = (d_rate / p_rate) * 100.0
        r.analyze(
            "Metodologi Production Order Quantity (POQ / EPQ)",
            "Berbeda dari EOQ yang menerima barang sekaligus, model POQ memperhitungkan akumulasi stok bertahap sebesar (p − d) per hari selama mesin berproduksi.",
            [
                f"Faktor Penyesuaian Produksi: (1 − d/p) = (1 − {d_rate:g}/{p_rate:g}) = {factor:.4f}.",
                f"Substitusi Rumus: Qp* = √(2 × {D:g} × {S:g} / ({H:g} × {factor:.4f})) = {q_star:,.2f} unit.",
                f"Verifikasi Keseimbangan Optimal: Biaya Setup ({setup_cost:,.2f}) = Biaya Simpan ({hold_cost:,.2f}) → Total = {total_cost:,.2f}.",
            ],
        )
        r.analyze(
            "Dinamika Siklus Produksi & Perbandingan terhadap EOQ",
            "Karena sebagian output langsung terserap permintaan saat diproduksi, puncak stok jauh lebih rendah dibanding ukuran lotnya.",
            [
                f"Fase Produksi aktif selama {run_len:,.2f} hari (stok naik dengan laju p − d = {p_rate - d_rate:g} unit/hari hingga puncak {max_inv:,.2f} unit), "
                f"dilanjutkan fase konsumsi murni tanpa produksi selama {depletion_len:,.2f} hari (total siklus {cycle_len:,.2f} hari).",
                f"Utilisasi lini produksi untuk item ini = d/p = {util_pct:.1f}% (tersisa {100.0 - util_pct:.1f}% waktu mesin bebas untuk produk lain atau perawatan).",
                f"Dibandingkan EOQ standar (Q={eoq_ref:,.2f}, biaya={eoq_cost:,.2f}): ukuran lot POQ lebih besar {(q_star / eoq_ref - 1) * 100:.1f}%, "
                f"namun total biaya persediaan lebih hemat {(1 - total_cost / eoq_cost) * 100:.1f}%.",
            ],
        )
        rec_bullets = [
            f"Jalankan {D / q_star:,.2f} kali production run per tahun sebesar {q_star:,.0f} unit setiap {cycle_len:,.1f} hari.",
            f"Siapkan kapasitas gudang barang jadi minimal {max_inv:,.0f} unit (bukan {q_star:,.0f} unit, karena sebagian langsung dikonsumsi).",
        ]
        if util_pct > 85.0:
            rec_bullets.append(f"Peringatan: rasio d/p sudah sangat tinggi ({util_pct:.1f}%); sedikit penurunan laju produksi dapat menyebabkan kekurangan stok.")
        else:
            rec_bullets.append(f"Manfaatkan jendela {depletion_len:,.1f} hari non-produksi per siklus untuk pergantian produk (changeover) atau pemeliharaan preventif.")
        r.analyze("Rekomendasi Penjadwalan Produksi", "Implikasi operasional untuk lantai pabrik:", rec_bullets)
        return r
