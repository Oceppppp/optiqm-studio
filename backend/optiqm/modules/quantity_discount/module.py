"""Modul Quantity Discount (EOQ dengan diskon kuantitas)."""

from __future__ import annotations

import math

import pandas as pd

from optiqm.core import BaseModule, InputError, ModuleResult, ParamSpec, SheetData, register
from optiqm.core.parsing import clean_frame, find_column, require_rows, to_float


@register
class QuantityDiscount(BaseModule):
    key = "quantity_discount"
    name = "Quantity Discount"
    category = "Persediaan"
    description = "Memilih ukuran order optimal ketika harga per unit turun pada jumlah pembelian tertentu."
    sheet_prefixes = ("QD", "DISCOUNT", "DISKON")
    params = (
        ParamSpec("D", "Permintaan Tahunan (D)", "number", 5000.0),
        ParamSpec("S", "Biaya Pesan per Order (S)", "number", 49.0),
        ParamSpec("holding_pct", "Biaya Simpan (% dari harga)", "number", 20.0),
        ParamSpec("fixed_H", "Atau Biaya Simpan Tetap H (0 = pakai %)", "number", 0.0),
    )
    table_hint = "Kolom: Min_Qty (batas bawah kuantitas), Max_Qty (opsional), Price (harga per unit)."

    def template(self) -> SheetData:
        # Wohl's Discount / Heizer & Render: D=5000, S=49, I=20%, breaks: 0->5.00, 1000->4.80, 2000->4.75
        df = pd.DataFrame(
            [[0, 999, 5.00], [1000, 1999, 4.80], [2000, None, 4.75]],
            columns=["Min_Qty", "Max_Qty", "Price"],
        )
        return SheetData(params={"D": 5000, "S": 49, "holding_pct": 20, "fixed_H": 0}, tables={"main": df})

    def solve(self, data: SheetData) -> ModuleResult:
        p = self.resolved_params(data)
        D, S = float(p["D"]), float(p["S"])
        pct = float(p["holding_pct"])
        pct = pct / 100.0 if pct > 1.0 else pct
        fixed_h = float(p["fixed_H"])
        if D <= 0 or S <= 0:
            raise InputError("D dan S harus > 0.")

        df = clean_frame(data.table("main"))
        require_rows(df, 1, "Tabel tingkat diskon")
        c_min = find_column(df, ["Min_Qty", "Min", "From", "BatasBawah", "Qty"])
        c_max = find_column(df, ["Max_Qty", "Max", "To", "BatasAtas"], required=False)
        c_price = find_column(df, ["Price", "Harga", "UnitCost", "Cost"])

        tiers = []
        for i in range(len(df)):
            mn = to_float(df.at[i, c_min], f"Min_Qty baris {i + 1}")
            mx = to_float(df.at[i, c_max], f"Max_Qty baris {i + 1}") if c_max and not pd.isna(df.at[i, c_max]) else math.inf
            pr = to_float(df.at[i, c_price], f"Price baris {i + 1}")
            tiers.append((mn, mx, pr))
        tiers.sort(key=lambda t: t[0])

        rows_out = []
        best = None
        for idx, (mn, mx, pr) in enumerate(tiers, start=1):
            H = fixed_h if fixed_h > 0 else pct * pr
            if H <= 0:
                raise InputError("Biaya simpan H tidak boleh <= 0.")
            q_raw = math.sqrt(2.0 * D * S / H)
            if mn <= q_raw <= mx:
                q_adj, status = q_raw, "Feasible (EOQ)"
            elif q_raw < mn:
                q_adj, status = max(1.0, mn), "Disesuaikan ke batas minimum"
            else:
                q_adj, status = mx, "Melebihi batas maksimum"
            ord_c = (D / q_adj) * S
            hold_c = (q_adj / 2.0) * H
            pur_c = D * pr
            tot = ord_c + hold_c + pur_c
            rows_out.append([idx, f"{mn:g} – {'∞' if math.isinf(mx) else f'{mx:g}'}", pr, H, q_raw, q_adj, status, pur_c, ord_c, hold_c, tot])
            if q_raw <= mx and (best is None or tot < best[0]):
                best = (tot, q_adj, pr, idx)

        if best is None:
            # fallback pilih biaya terendah dari semua baris
            best_row = min(rows_out, key=lambda r: r[-1])
            best = (best_row[-1], best_row[5], best_row[2], best_row[0])

        r = ModuleResult()
        r.metric("Total Biaya Minimum", best[0], highlight=True)
        r.metric("Kuantitas Order Optimal (Q*)", best[1], unit="unit", highlight=True)
        r.metric("Harga Terbaik", best[2])
        r.table("Evaluasi Tingkat Diskon",
                ["Tier", "Rentang Qty", "Harga", "H", "Q* Mentah", "Q Disesuaikan", "Status",
                 "Biaya Beli", "Biaya Pesan", "Biaya Simpan", "Total Biaya"], rows_out)
        r.chart("Perbandingan Total Biaya per Tier", "bar", {
            "x": [f"Tier {row[0]} ({row[2]:g})" for row in rows_out],
            "series": [{"name": "Total Biaya", "data": [row[-1] for row in rows_out]}],
            "x_label": "Tier Harga", "y_label": "Total Biaya Tahunan",
        })
        r.interpretation = f"Pilih Tier {best[3]} (harga {best[2]:g}) dengan order Q* = {best[1]:g} unit; total biaya tahunan = {best[0]:,.2f}."
        return r
