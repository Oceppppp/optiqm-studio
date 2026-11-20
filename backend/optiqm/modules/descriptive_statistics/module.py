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
        var_details = []
        for name, arr in cols_data:
            q1, med, q3 = [float(x) for x in np.percentile(arr, [25, 50, 75])]
            mean_v = float(arr.mean())
            std_v = float(arr.std(ddof=1))
            var_v = float(arr.var(ddof=1))
            sk = 0.0 if std_v < 1e-12 else float(stats.skew(arr))
            iqr = q3 - q1
            cv = (std_v / abs(mean_v) * 100.0) if abs(mean_v) > 1e-12 else 0.0
            lo_fence, hi_fence = q1 - 1.5 * iqr, q3 + 1.5 * iqr
            outliers = [float(x) for x in arr if x < lo_fence or x > hi_fence]
            var_details.append({
                "name": name, "n": len(arr), "mean": mean_v, "med": med, "std": std_v,
                "iqr": iqr, "cv": cv, "skew": sk, "min": float(arr.min()), "max": float(arr.max()),
                "outliers": outliers,
            })
            rows_out.append([
                name, len(arr), mean_v, med, std_v, var_v, float(arr.min()), q1, q3, float(arr.max()), sk,
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

        # Analisis mendalam
        r.analyze(
            "Metodologi Statistik Deskriptif & Penyebaran Sampel",
            f"Meringkas karakteristik distribusi {len(cols_data)} variabel numerik menggunakan simpangan baku sampel tak bias (ddof = 1), "
            "rentang antarkuartil (IQR = Q3 − Q1), koefisien variasi (CV = s / |x̄|), kemencengan (Skewness), serta aturan deteksi pencilan Tukey (1.5 × IQR).",
            [
                f"Variabel '{d['name']}' (n={d['n']}): Mean = {d['mean']:,.3f}, Median = {d['med']:,.3f}, Std. Dev = {d['std']:,.3f}, Rentang = [{d['min']:g}, {d['max']:g}], IQR = {d['iqr']:,.3f}."
                for d in var_details
            ],
        )

        shape_bullets = []
        any_outlier = False
        any_skewed = False
        for d in var_details:
            sk = d["skew"]
            if abs(sk) < 0.5:
                sk_lbl = "relatif simetris"
            elif sk >= 0.5:
                sk_lbl = "menceng ke kanan (positively skewed — ekor panjang di nilai tinggi)"
                any_skewed = True
            else:
                sk_lbl = "menceng ke kiri (negatively skewed — ekor panjang di nilai rendah)"
                any_skewed = True
            cv_lbl = "homogen (<15%)" if d["cv"] < 15 else ("moderat (15%–30%)" if d["cv"] <= 30 else "tinggi / heterogen (>30%)")
            out_txt = f"{len(d['outliers'])} outlier ({', '.join(f'{x:g}' for x in d['outliers'][:5])})" if d["outliers"] else "tidak ada outlier"
            if d["outliers"]:
                any_outlier = True
            shape_bullets.append(
                f"'{d['name']}': distribusi {sk_lbl} (skew = {sk:+.3f}), variasi {cv_lbl} (CV = {d['cv']:.1f}%), deteksi 1.5×IQR: {out_txt}."
            )
        r.analyze(
            "Bedah Bentuk Distribusi, Variabilitas (CV) & Deteksi Outlier",
            "Analisis komprehensif terhadap kesimetrisan, tingkat konsistensi data, dan anomali:",
            shape_bullets,
        )

        rec_bullets = []
        if any_outlier or any_skewed:
            rec_bullets.append("Karena terdeteksi kemencengan kuat atau nilai pencilan (outlier), gunakan Median dan IQR sebagai ukuran pusat/sebaran yang lebih tahan terhadap distorsi dibanding Mean.")
            if any_outlier:
                rec_bullets.append("Verifikasi nilai outlier di atas — pastikan bukan kesalahan pencatatan sebelum dipakai untuk pemodelan parametrik.")
        else:
            rec_bullets.append("Data relatif simetris dan bebas outlier: Mean dan Simpangan Baku representatif untuk analisis parametrik (uji t, peta kendali SPC, atau safety stock normal).")
        if len(var_details) >= 2:
            arr0, arr1 = cols_data[0][1], cols_data[1][1]
            if len(arr0) == len(arr1) and arr0.std() > 1e-12 and arr1.std() > 1e-12:
                corr = float(np.corrcoef(arr0, arr1)[0, 1])
                rec_bullets.append(
                    f"Korelasi Pearson antara '{cols_data[0][0]}' dan '{cols_data[1][0]}': r = {corr:+.3f} "
                    f"({'hubungan kuat' if abs(corr) >= 0.7 else ('hubungan sedang' if abs(corr) >= 0.4 else 'hubungan lemah')})."
                )
        r.analyze("Rekomendasi Interpretasi & Analisis Lanjutan", "Panduan pemanfaatan hasil statistik:", rec_bullets)
        return r
