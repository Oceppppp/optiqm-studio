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
            tables={"main": pd.DataFrame([["D", 1000], ["S", 10], ["H", 0.5], ["working_days", 250], ["lead_time", 4]],
                                         columns=["Parameter", "Value"])},
        )

    def _read(self, data: SheetData) -> dict:
        p = self.resolved_params(data)
        df = data.table("main", required=False)
        if df is not None and len(df.columns) >= 2:
            for _, row in df.iterrows():
                k = str(row.iloc[0]).strip().lower()
                if k in p and not pd.isna(row.iloc[1]):
                    p[k] = float(row.iloc[1]) if k not in {"working_days"} else float(row.iloc[1])
        return p

    def solve(self, data: SheetData) -> ModuleResult:
        p = self._read(data)
        D, S, H, price, pct, days, lt = (float(p["D"]), float(p["S"]), float(p["H"]),
                                          float(p["unit_price"]), float(p["holding_pct"]),
                                          float(p["working_days"]), float(p["lead_time"]))
        if H <= 0 and price > 0 and pct > 0:
            H = price * (pct / 100.0 if pct > 1 else pct)
        if D <= 0 or S <= 0 or H <= 0:
            raise InputError("D, S, dan H harus bernilai positif (> 0).")

        q_star = math.sqrt(2.0 * D * S / H)
        orders = D / q_star
        cycle = days / orders if days > 0 else 0.0
        daily_d = D / days if days > 0 else 0.0
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
        return r
