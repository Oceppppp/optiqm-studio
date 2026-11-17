"""Modul Descriptive Statistics & Histogram."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from optiqm.core import BaseModule, InputError, ModuleResult, ParamSpec, SheetData, register
from optiqm.core.parsing import clean_frame, require_rows, to_float


@register
class DescriptiveStatistics(BaseModule):
    key = "descriptive_statistics"
    name = "Descriptive Statistics"
    category = "Statistik & Simulasi"
    description = "Statistik deskriptif (mean, median, varians, simpangan baku, kuartil, skewness) dan histogram."
    sheet_prefixes = ("STAT", "STATS", "DESKRIPTIF")
    params = (ParamSpec("bins", "Jumlah Kelas Histogram", "integer", 6),)
    table_hint = "Setiap kolom berisi deretan angka variabel yang ingin dianalisis (minimal 1 kolom angka)."

    def template(self) -> SheetData:
        df = pd.DataFrame(
            {"Waktu_Layanan": [12, 15, 14, 18, 13, 16, 15, 19, 14, 15, 17, 13],
             "Biaya_Kirim": [45, 52, 48, 60, 44, 55, 50, 62, 49, 51, 58, 46]}
        )
        return SheetData(params={"bins": 6}, tables={"main": df})

    def solve(self, data: SheetData) -> ModuleResult:
        p = self.resolved_params(data)
        bins = max(2, int(p["bins"]))
        df = clean_frame(data.table("main"))
        require_rows(df, 2, "Tabel data statistik")

        cols_data: list[tuple[str, np.ndarray]] = []
        for col in df.columns:
            vals = []
            ok = True
            for v in df[col]:
                if pd.isna(v):
                    continue
                try:
                    vals.append(to_float(v, str(col)))
                except InputError:
                    ok = False
                    break
            if ok and len(vals) >= 2:
                cols_data.append((str(col), np.array(vals, dtype=float)))
        if not cols_data:
            raise InputError("Tidak ditemukan kolom numerik yang valid.")

        rows_out = []
        for name, arr in cols_data:
            q1, med, q3 = np.percentile(arr, [25, 50, 75])
            rows_out.append([
                name, len(arr), float(arr.mean()), float(med), float(arr.std(ddof=1)),
                float(arr.var(ddof=1)), float(arr.min()), float(q1), float(q3),
                float(arr.max()), float(stats.skew(arr)),
            ])

        first_name, first_arr = cols_data[0]
        hist, edges = np.histogram(first_arr, bins=bins)
        r = ModuleResult()
        r.metric(f"Rata-rata ({first_name})", float(first_arr.mean()), highlight=True)
        r.metric(f"Simpangan Baku ({first_name})", float(first_arr.std(ddof=1)), highlight=True)
        r.metric("Jumlah Variabel", len(cols_data))
        r.table("Ringkasan Statistik Deskriptif",
                ["Variabel", "n", "Mean", "Median", "Std. Dev", "Varians", "Min", "Q1", "Q3", "Max", "Skewness"],
                rows_out)
        r.chart(f"Histogram — {first_name}", "bar", {
            "x": [f"{edges[i]:.1f}–{edges[i+1]:.1f}" for i in range(len(hist))],
            "series": [{"name": "Frekuensi", "data": hist.tolist()}],
            "x_label": "Rentang Nilai", "y_label": "Frekuensi",
        })
        r.interpretation = f"Dihitung statistik deskriptif untuk {len(cols_data)} variabel (n={len(first_arr)})."
        return r
