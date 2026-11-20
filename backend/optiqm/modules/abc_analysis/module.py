"""Modul Analisis ABC Persediaan (Hukum Pareto)."""

from __future__ import annotations

import pandas as pd

from optiqm.core import BaseModule, InputError, ModuleResult, ParamSpec, SheetData, register
from optiqm.core.parsing import clean_frame, find_column, require_rows, to_float


@register
class ABCAnalysis(BaseModule):
    key = "abc_analysis"
    name = "ABC Analysis"
    category = "Persediaan"
    description = "Mengelompokkan item persediaan ke kelas A, B, C berdasarkan kontribusi nilai pemakaian tahunan."
    sheet_prefixes = ("ABC",)
    params = (
        ParamSpec("cutoff_a", "Batas Kumulatif Kelas A (%)", "number", 80.0),
        ParamSpec("cutoff_b", "Batas Kumulatif Kelas A+B (%)", "number", 95.0),
    )
    table_hint = "Kolom: Item, Demand (kebutuhan tahunan), Cost (harga per unit)."

    def template(self) -> SheetData:
        # Silicon Chips Inc. (Heizer & Render)
        df = pd.DataFrame(
            [["#10286", 1000, 90.00], ["#11526", 500, 154.00], ["#12760", 1550, 17.00],
             ["#10867", 350, 42.86], ["#10500", 1000, 12.50], ["#12572", 600, 14.17],
             ["#14075", 2000, 0.60], ["#01036", 100, 8.50], ["#01307", 1200, 0.42], ["#10572", 250, 0.60]],
            columns=["Item", "Demand", "Cost"],
        )
        return SheetData(params={"cutoff_a": 80, "cutoff_b": 95}, tables={"main": df})

    def solve(self, data: SheetData) -> ModuleResult:
        p = self.resolved_params(data)
        cut_a, cut_b = float(p["cutoff_a"]), float(p["cutoff_b"])
        if not (0 < cut_a < cut_b <= 100):
            raise InputError("Batas persentase harus memenuhi 0 < Cutoff A < Cutoff A+B ≤ 100.")
        df = clean_frame(data.table("main"))
        require_rows(df, 1, "Tabel item persediaan")
        c_item = find_column(df, ["Item", "Nama", "SKU", "Barang"], required=False) or df.columns[0]
        c_dem = find_column(df, ["Demand", "Volume", "Qty", "Jumlah", "Pemakaian"])
        c_cost = find_column(df, ["Cost", "Price", "Harga", "UnitCost", "Biaya"])

        items = []
        for i in range(len(df)):
            nm = str(df.at[i, c_item]).strip()
            d = to_float(df.at[i, c_dem], f"Demand {nm}")
            c = to_float(df.at[i, c_cost], f"Cost {nm}")
            if d < 0 or c < 0:
                raise InputError(f"Demand/Cost '{nm}' tidak boleh negatif.")
            items.append((nm, d, c, d * c))
        items.sort(key=lambda x: x[3], reverse=True)
        total_val = sum(x[3] for x in items)
        if total_val <= 0:
            raise InputError("Total nilai pemakaian tahunan nol.")

        rows_out = []
        cum = 0.0
        counts = {"A": 0, "B": 0, "C": 0}
        class_vals = {"A": 0.0, "B": 0.0, "C": 0.0}
        for nm, d, c, val in items:
            pct = val / total_val * 100.0
            prev_cum = cum
            cum += pct
            cls = "A" if prev_cum < cut_a - 1e-6 else ("B" if prev_cum < cut_b - 1e-6 else "C")
            counts[cls] += 1
            class_vals[cls] += val
            rows_out.append([nm, d, c, val, pct, cum, cls])

        r = ModuleResult()
        r.metric("Total Nilai Pemakaian", total_val, highlight=True)
        r.metric("Item Kelas A", counts["A"])
        r.metric("Item Kelas B", counts["B"])
        r.metric("Item Kelas C", counts["C"])
        r.table("Klasifikasi ABC",
                ["Item", "Demand", "Harga/Unit", "Nilai Tahunan", "% Nilai", "% Kumulatif", "Kelas"], rows_out)
        r.chart("Diagram Pareto Nilai ABC", "bar", {
            "x": [row[0] for row in rows_out],
            "series": [
                {"name": "% Nilai Item", "data": [row[4] for row in rows_out]},
                {"name": "% Kumulatif", "data": [row[5] for row in rows_out]},
            ],
            "x_label": "Item", "y_label": "Persentase (%)",
        })
        r.interpretation = f"Dari {len(items)} item (total nilai {total_val:,.2f}): Kelas A={counts['A']}, B={counts['B']}, C={counts['C']}."

        # Analisis mendalam
        n_items = len(items)
        r.analyze(
            "Metodologi Klasifikasi ABC (Hukum Pareto)",
            f"Seluruh {n_items} SKU dihitung nilai pemakaian tahunannya (Demand × Harga/Unit), diurutkan dari terbesar ke terkecil, "
            f"lalu diklasifikasikan berdasarkan batas kumulatif sebelum item masuk: Kelas A (<{cut_a:g}%), Kelas B ({cut_a:g}%–{cut_b:g}%), dan Kelas C (≥{cut_b:g}%).",
            [
                f"Kelas A: {counts['A']} item ({counts['A']/n_items*100:.1f}% SKU) menyumbang {class_vals['A']:,.2f} ({class_vals['A']/total_val*100:.1f}% total nilai).",
                f"Kelas B: {counts['B']} item ({counts['B']/n_items*100:.1f}% SKU) menyumbang {class_vals['B']:,.2f} ({class_vals['B']/total_val*100:.1f}% total nilai).",
                f"Kelas C: {counts['C']} item ({counts['C']/n_items*100:.1f}% SKU) menyumbang {class_vals['C']:,.2f} ({class_vals['C']/total_val*100:.1f}% total nilai).",
            ],
        )
        top3 = rows_out[:3]
        top3_pct = sum(row[4] for row in top3)
        r.analyze(
            "Bedah Konsentrasi Nilai (Item Kritis)",
            f"Tiga item teratas menyumbang {top3_pct:.1f}% dari seluruh nilai pemakaian persediaan tahunan:",
            [
                f"Peringkat #{idx}: '{row[0]}' — nilai {row[3]:,.2f} ({row[4]:.1f}%, Demand={row[1]:g} × Harga={row[2]:g}) → Kelas {row[6]}."
                for idx, row in enumerate(top3, start=1)
            ],
        )
        r.analyze(
            "Rekomendasi Kebijakan Pengendalian per Kelas",
            "Alokasikan energi pengawasan proporsional terhadap kontribusi finansial masing-masing kelas:",
            [
                f"Kelas A ({counts['A']} SKU): terapkan pemantauan ketat (perpetual inventory), cycle counting bulanan, negosiasi harga pemasok, dan akurasi peramalan tinggi.",
                f"Kelas B ({counts['B']} SKU): gunakan kebijakan EOQ/ROP standar dengan review berkala per kuartal.",
                f"Kelas C ({counts['C']} SKU): gunakan sistem pengendalian sederhana (two-bin / pemesanan massal periodik) agar biaya administrasi tetap minimal.",
            ],
        )
        return r
