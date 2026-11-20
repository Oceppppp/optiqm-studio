"""Modul Economic Order Quantity (EOQ) dasar."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from optiqm.core import BaseModule, InputError, ModuleResult, ParamSpec, SheetData, register


@register
class EOQ(BaseModule):
    key = "eoq"
    name = "EOQ (Persediaan Dasar)"
    category = "Persediaan"
    description = "Menghitung ukuran pemesanan ekonomis (EOQ), frekuensi pesan, total biaya, dan Reorder Point."
    sheet_prefixes = ("EOQ",)
    params = (
        ParamSpec("D", "Permintaan Tahunan (D)", "number", 1000.0),
        ParamSpec("S", "Biaya Pesan per Order (S)", "number", 10.0),
        ParamSpec("H", "Biaya Simpan per Unit/Thn (H, atau isi 0 jika pakai %)", "number", 0.5),
        ParamSpec("unit_price", "Harga per Unit (P, opsional)", "number", 0.0),
        ParamSpec("holding_pct", "Biaya Simpan % dari Harga (opsional, mis. 20%)", "number", 0.0),
        ParamSpec("working_days", "Hari Kerja per Tahun", "number", 250.0),
        ParamSpec("lead_time", "Lead Time (hari)", "number", 4.0),
    )
    table_hint = "Parameter dapat diisi di panel parameter atau di blok [params] Excel (tabel [main] opsional)."

    def template(self) -> SheetData:
        # Sharp Inc. (Heizer & Render): D=1000, S=10, H=0.5 -> Q*=200, cost=100, orders=5
        return SheetData(
            params={"D": 1000, "S": 10, "H": 0.5, "unit_price": 0, "holding_pct": 0, "working_days": 250, "lead_time": 4},
        )

    def solve(self, data: SheetData) -> ModuleResult:
        p = self.resolved_params_with_table(data)
        D, S, H, price, pct, days, lt = (float(p["D"]), float(p["S"]), float(p["H"]),
                                          float(p["unit_price"]), float(p["holding_pct"]),
                                          float(p["working_days"]), float(p["lead_time"]))
        if price < 0 or pct < 0 or lt < 0:
            raise InputError("Harga unit, persentase simpan, dan lead time tidak boleh negatif.")
        if days <= 0:
            raise InputError("Hari kerja per tahun harus > 0.")
        if H <= 0 and price > 0 and pct > 0:
            H = price * (pct / 100.0 if pct > 1 else pct)
        if D <= 0 or S <= 0 or H <= 0:
            raise InputError("D, S, dan H harus bernilai positif (> 0).")

        q_star = math.sqrt(2.0 * D * S / H)
        orders = D / q_star
        cycle = days / orders
        daily_d = D / days
        rop = daily_d * lt
        order_cost = (D / q_star) * S
        hold_cost = (q_star / 2.0) * H
        total_inv_cost = order_cost + hold_cost
        purchase_cost = D * price

        r = ModuleResult()
        r.metric("EOQ (Q*)", q_star, unit="unit", highlight=True)
        r.metric("Total Biaya Persediaan", total_inv_cost, highlight=True)
        r.metric("Frekuensi Order / Tahun", orders, unit="kali")
        r.metric("Siklus Antar Order", cycle, unit="hari")
        r.metric("Reorder Point (ROP)", rop, unit="unit")
        if purchase_cost > 0:
            r.metric("Total Biaya + Pembelian", total_inv_cost + purchase_cost)
        if lt > cycle:
            r.warnings.append(
                f"Lead time ({lt:g} hari) melebihi siklus antar order ({cycle:,.1f} hari): "
                "ROP harus dipantau berdasarkan Inventory Position (stok fisik + pesanan dalam perjalanan)."
            )

        r.table("Ringkasan EOQ", ["Komponen", "Nilai"], [
            ["Ukuran Order Optimal (Q*)", q_star],
            ["Rata-rata Persediaan (Q*/2)", q_star / 2.0],
            ["Order per Tahun (D/Q*)", orders],
            ["Waktu Antar Order (hari)", cycle],
            ["Biaya Pesan Tahunan", order_cost],
            ["Biaya Simpan Tahunan", hold_cost],
            ["Total Biaya Persediaan (Pesan + Simpan)", total_inv_cost],
            ["Reorder Point (ROP)", rop],
        ])

        qs = np.linspace(max(1.0, q_star * 0.25), q_star * 2.2, 25).tolist()
        r.chart("Kurva Biaya Tahunan vs Q", "line", {
            "x": [round(q, 1) for q in qs],
            "series": [
                {"name": "Biaya Pesan", "data": [D / q * S for q in qs]},
                {"name": "Biaya Simpan", "data": [q / 2 * H for q in qs]},
                {"name": "Total Biaya", "data": [D / q * S + q / 2 * H for q in qs]},
            ],
            "x_label": "Ukuran Order (Q)", "y_label": "Biaya",
        })
        # Pola gigi gergaji 3 siklus
        sx, sy = [], []
        for k in range(3):
            sx.extend([round(k * cycle, 1), round((k + 1) * cycle, 1)])
            sy.extend([q_star, 0.0])
        r.chart("Pola Persediaan (Sawtooth)", "line", {
            "x": sx, "series": [{"name": "Tingkat Persediaan", "data": sy}],
            "x_label": "Hari", "y_label": "Unit",
        })
        r.interpretation = f"Pesan {q_star:,.2f} unit setiap {cycle:,.1f} hari (saat stok ≤ {rop:,.1f} unit); biaya tahunan {total_inv_cost:,.2f}."

        # Analisis mendalam
        tc_minus20 = (D / (0.8 * q_star)) * S + (0.8 * q_star / 2.0) * H
        tc_plus20 = (D / (1.2 * q_star)) * S + (1.2 * q_star / 2.0) * H
        r.analyze(
            "Metodologi & Verifikasi Keseimbangan Biaya EOQ",
            "Model Economic Order Quantity (Wilson) meminimalkan jumlah biaya pemesanan tahunan dan biaya penyimpanan tahunan pada permintaan konstan.",
            [
                f"Substitusi Rumus: Q* = √(2 × {D:g} × {S:g} / {H:g}) = {q_star:,.2f} unit.",
                f"Verifikasi Titik Optimal: Biaya Pesan ({order_cost:,.2f}) = Biaya Simpan ({hold_cost:,.2f}) → Total = {total_inv_cost:,.2f}.",
                f"Permintaan Harian (d) = {D:g} / {days:g} = {daily_d:,.2f} unit/hari; Reorder Point (ROP) = d × LT = {daily_d:,.2f} × {lt:g} = {rop:,.2f} unit.",
            ],
        )
        r.analyze(
            "Analisis Sensitivitas & Ketangguhan (Robustness) EOQ",
            "Kurva total biaya EOQ berbentuk datar di sekitar titik minimum sehingga cukup toleran terhadap pembulatan ukuran lot kemasan.",
            [
                f"Jika order dikurangi 20% menjadi {0.8 * q_star:,.1f} unit: total biaya hanya naik {(tc_minus20 - total_inv_cost) / total_inv_cost * 100:.2f}% (menjadi {tc_minus20:,.2f}).",
                f"Jika order dinaikkan 20% menjadi {1.2 * q_star:,.1f} unit: total biaya hanya naik {(tc_plus20 - total_inv_cost) / total_inv_cost * 100:.2f}% (menjadi {tc_plus20:,.2f}).",
                f"Rata-rata persediaan tersimpan sepanjang tahun adalah {q_star / 2.0:,.2f} unit dengan perputaran (inventory turnover) {D / (q_star / 2.0):.2f} kali/tahun.",
            ],
        )
        r.analyze(
            "Rekomendasi Kebijakan Persediaan",
            "Implementasi praktis untuk tim pengadaan dan gudang:",
            [
                f"Tetapkan ukuran pemesanan standar sekitar {round(q_star):,} unit (boleh dibulatkan ke kelipatan dus/palet dalam rentang ±15% karena penalti biaya < 1%).",
                f"Pasang alarm pemesanan otomatis saat posisi persediaan menyentuh {rop:,.1f} unit agar barang tiba tepat sebelum stok habis.",
                "Jika permintaan harian atau waktu kirim pemasok berfluktuasi, lengkapi ROP dengan Safety Stock melalui modul Safety Stock & ROP.",
            ],
        )
        return r
