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
        if pct < 0 or fixed_h < 0:
            raise InputError("Persentase biaya simpan dan biaya simpan tetap tidak boleh negatif.")

        df = clean_frame(data.table("main"))
        require_rows(df, 1, "Tabel tingkat diskon")
        c_min = find_column(df, ["Min_Qty", "Min", "From", "BatasBawah", "Qty"])
        c_max = find_column(df, ["Max_Qty", "Max", "To", "BatasAtas"], required=False)
        c_price = find_column(df, ["Price", "Harga", "UnitCost", "Cost"])

        tiers = []
        for i in range(len(df)):
            mn = to_float(df.at[i, c_min], f"Min_Qty baris {i + 1}")
            raw_mx = df.at[i, c_max] if c_max else None
            if raw_mx is None or pd.isna(raw_mx) or str(raw_mx).strip().lower() in {"", "inf", "∞", "unlimited", "-"}:
                mx = math.inf
            else:
                mx = to_float(raw_mx, f"Max_Qty baris {i + 1}")
            pr = to_float(df.at[i, c_price], f"Price baris {i + 1}")
            if mn < 0 or mx <= 0 or mx < mn or pr <= 0:
                raise InputError(f"Baris tier {i + 1} tidak valid (pastikan 0 ≤ Min_Qty ≤ Max_Qty, Max_Qty > 0, dan Harga > 0).")
            tiers.append((mn, mx, pr))
        tiers.sort(key=lambda t: t[0])

        rows_out = []
        best = None
        for idx, (mn, mx, pr) in enumerate(tiers, start=1):
            H = fixed_h if fixed_h > 0 else pct * pr
            if H <= 0:
                raise InputError("Biaya simpan H tidak boleh <= 0.")
            q_raw = math.sqrt(2.0 * D * S / H)
            lo = max(1.0, mn)
            if lo <= q_raw <= mx:
                q_adj, status = q_raw, "Feasible (EOQ)"
            elif q_raw < lo:
                q_adj, status = lo, "Disesuaikan ke batas minimum"
            else:
                q_adj, status = mx, "Disesuaikan ke batas maksimum"
            ord_c = (D / q_adj) * S
            hold_c = (q_adj / 2.0) * H
            pur_c = D * pr
            tot = ord_c + hold_c + pur_c
            rows_out.append([idx, f"{mn:g} – {'∞' if math.isinf(mx) else f'{mx:g}'}", pr, H, q_raw, q_adj, status, pur_c, ord_c, hold_c, tot])
            if best is None or tot < best[0]:
                best = (tot, q_adj, pr, idx, pur_c, ord_c, hold_c)

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

        # Analisis mendalam
        base_row = rows_out[0]
        last_row = rows_out[-1]
        savings_vs_base = base_row[-1] - best[0]
        r.analyze(
            "Metodologi EOQ Diskon Kuantitas (All-Units Discount)",
            f"Setiap dari {len(rows_out)} tingkat harga dihitung EOQ mentahnya Q = √(2DS/H), disesuaikan ke rentang kuantitas layak [Min, Max], "
            "lalu dibandingkan Total Biaya Tahunan = (D×P) + (D/Q×S) + (Q/2×H).",
            [
                f"Solusi Optimal: Tier {best[3]} pada Q* = {best[1]:,.2f} unit (harga {best[2]:,.4g}/unit, {D / best[1]:,.2f} order/tahun).",
                f"Komposisi Total Biaya ({best[0]:,.2f}): Pembelian = {best[4]:,.2f} ({best[4]/best[0]*100:.1f}%), "
                f"Pesan = {best[5]:,.2f} ({best[5]/best[0]*100:.1f}%), Simpan = {best[6]:,.2f} ({best[6]/best[0]*100:.1f}%).",
            ],
        )

        trade_bullets = [
            f"Dibandingkan Tier 1 tanpa diskon ekstra (total {base_row[-1]:,.2f}): memilih Tier {best[3]} menghemat {savings_vs_base:,.2f}/tahun "
            f"({(savings_vs_base / base_row[-1] * 100.0) if base_row[-1] > 0 else 0.0:.2f}%)."
        ]
        if best[3] != last_row[0]:
            diff_last = last_row[-1] - best[0]
            trade_bullets.append(
                f"Mengapa Tier {last_row[0]} (harga termurah {last_row[2]:g}) TIDAK optimal? Meski biaya beli turun {best[4] - last_row[7]:,.2f}, "
                f"lonjakan biaya simpan ({last_row[9] - best[6]:+,.2f}) lebih besar sehingga total biaya justru lebih mahal {diff_last:,.2f}/tahun."
            )
        else:
            trade_bullets.append("Tier diskon tertinggi memberikan total biaya terendah karena penghematan harga beli melampaui tambahan biaya penyimpanan.")
        r.analyze(
            "Bedah Trade-off Harga Diskon vs Biaya Penyimpanan",
            "Diskon kuantitas hanya menguntungkan bila penghematan harga pembelian dan frekuensi order lebih besar dari tambahan biaya simpan stok.",
            trade_bullets,
        )
        r.analyze(
            "Rekomendasi Pengadaan",
            "Pertimbangan praktis sebelum mengeksekusi pembelian pada tingkat diskon terpilih:",
            [
                f"Pesan sebanyak {best[1]:,.0f} unit setiap kali order (rata-rata stok tersimpan {best[1] / 2.0:,.1f} unit).",
                "Pastikan ruang gudang, modal kerja tunai, dan umur simpan (shelf-life) produk mampu menampung ukuran lot tersebut tanpa risiko rusak atau usang.",
            ],
        )
        return r
