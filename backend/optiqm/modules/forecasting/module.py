"""Modul Forecasting (8 metode peramalan + evaluasi akurasi)."""

from __future__ import annotations

import pandas as pd

from optiqm.core import BaseModule, InputError, ModuleResult, ParamSpec, SheetData, register
from optiqm.core.parsing import clean_frame, find_column, require_rows, to_float

from .metrics import error_metrics
from .methods import (
    exponential_smoothing, linear_regression, moving_average, naive,
    seasonal_multiplicative, trend_adjusted_exp, weighted_moving_average,
)

METHODS = (
    "naive", "moving_average", "weighted_moving_average", "exponential_smoothing",
    "trend_adjusted_exponential_smoothing", "linear_regression", "causal_regression", "seasonal",
)


@register
class Forecasting(BaseModule):
    key = "forecasting"
    name = "Forecasting"
    category = "Peramalan"
    description = "Peramalan deret waktu & kausal (MA, WMA, Exponential Smoothing, Trend, Regresi, Musiman)."
    sheet_prefixes = ("FC", "FORECAST", "RAMAL")
    params = (
        ParamSpec("method", "Metode", "choice", "exponential_smoothing", METHODS),
        ParamSpec("periods", "Panjang Moving Average (k)", "integer", 3),
        ParamSpec("weights", "Bobot WMA (dipisah koma, terlama→terbaru)", "text", "0.2, 0.3, 0.5"),
        ParamSpec("alpha", "Alpha (α)", "number", 0.3),
        ParamSpec("beta", "Beta (β, untuk Trend-Adjusted)", "number", 0.2),
        ParamSpec("initial_forecast", "Ramalan Awal F₁ (opsional)", "text", ""),
        ParamSpec("season_length", "Panjang Musim (mis. 4 kuartal)", "integer", 4),
        ParamSpec("x_next", "Nilai X Berikutnya (utk Causal Regression)", "text", ""),
    )
    table_hint = "Kolom: Period, Demand (dan opsional kolom X jika memakai causal_regression)."

    def template(self) -> SheetData:
        # Contoh klasik data kuartalan/bulanan (8 periode)
        df = pd.DataFrame(
            [[f"P{i}", d] for i, d in enumerate([17, 21, 19, 23, 18, 16, 20, 18, 22, 20, 15, 22], start=1)],
            columns=["Period", "Demand"],
        )
        return SheetData(params={"method": "exponential_smoothing", "alpha": 0.3}, tables={"main": df})

    def solve(self, data: SheetData) -> ModuleResult:
        p = self.resolved_params(data)
        df = clean_frame(data.table("main"))
        require_rows(df, 2, "Tabel data historis")
        c_per = find_column(df, ["Period", "Periode", "Time", "Bulan", "Tahun"], required=False) or df.columns[0]
        c_dem = find_column(df, ["Demand", "Permintaan", "Actual", "Aktual", "Y", "Value", "Nilai"])
        periods = [str(v).strip() for v in df[c_per]]
        y = [to_float(df.at[i, c_dem], f"Demand baris {i + 1}") for i in range(len(df))]

        m = p["method"]
        f0 = to_float(p["initial_forecast"], "F1") if p["initial_forecast"] else None
        extra_note = ""
        if m == "naive":
            fc, next_f = naive(y)
        elif m == "moving_average":
            fc, next_f = moving_average(y, p["periods"])
        elif m == "weighted_moving_average":
            w = [to_float(x, "Bobot WMA") for x in str(p["weights"]).split(",") if x.strip()]
            fc, next_f = weighted_moving_average(y, w)
        elif m == "exponential_smoothing":
            fc, next_f = exponential_smoothing(y, p["alpha"], f0)
        elif m == "trend_adjusted_exponential_smoothing":
            fc, next_f = trend_adjusted_exp(y, p["alpha"], p["beta"], f0)
        elif m == "linear_regression":
            reg = linear_regression(y)
            fc, next_f = reg["fc"], reg["next"]
            extra_note = f"Persamaan: Y = {reg['a']:,.4f} + {reg['b']:,.4f}·t (R² = {reg['r2']:.4f})."
        elif m == "causal_regression":
            c_x = find_column(df, ["X", "Independent", "Predictor", "Iklan", "Harga"])
            xs = [to_float(df.at[i, c_x], f"X baris {i + 1}") for i in range(len(df))]
            xn = to_float(p["x_next"], "X berikutnya") if p["x_next"] else xs[-1]
            reg = linear_regression(y, xs, xn)
            fc, next_f = reg["fc"], reg["next"]
            extra_note = f"Persamaan: Y = {reg['a']:,.4f} + {reg['b']:,.4f}·X (R² = {reg['r2']:.4f}), pada X={xn:g}."
        elif m == "seasonal":
            sres = seasonal_multiplicative(y, p["season_length"])
            fc, next_f = sres["fc"], sres["next"]
            extra_note = f"Indeks musiman: {', '.join(f'{v:.3f}' for v in sres['indices'])}."
        else:
            raise InputError(f"Metode '{m}' tidak dikenal.")

        em = error_metrics(y, fc)
        r = ModuleResult()
        r.metric("Ramalan Periode Berikutnya", next_f, highlight=True)
        r.metric("MAD", em["mad"])
        r.metric("MSE", em["mse"])
        r.metric("MAPE", em["mape"], unit="%")
        r.metric("Tracking Signal", em["tracking_signal"])
        r.metric("Bias", em["bias"])

        tbl_rows = [[periods[i], *row] for i, row in enumerate(em["rows"])]
        tbl_rows.append(["Berikutnya", None, next_f, None, None, None, None])
        r.table("Tabel Peramalan & Akurasi",
                ["Periode", "Aktual", "Ramalan", "Error", "|Error|", "Error²", "|% Error|"], tbl_rows, note=extra_note)

        r.chart("Aktual vs Ramalan", "line", {
            "x": [*periods, "Berikutnya"],
            "series": [
                {"name": "Aktual", "data": [*y, None]},
                {"name": "Ramalan", "data": [*fc, next_f]},
            ],
            "x_label": "Periode", "y_label": "Permintaan",
        })
        r.interpretation = (f"Ramalan periode berikutnya = {next_f:,.2f} (MAD = {em['mad']:,.3f}, "
                            f"MAPE = {em['mape']:.2f}%). {extra_note}").strip()

        # Analisis mendalam
        method_desc = {
            "naive": "Naive Forecast: F_t = A_{t-1} (menggunakan nilai aktual terakhir sebagai ramalan periode berikutnya).",
            "moving_average": f"Simple Moving Average (k={p['periods']}): rata-rata bergerak dari {p['periods']} periode aktual terakhir.",
            "weighted_moving_average": f"Weighted Moving Average (bobot={p['weights']}): rata-rata tertimbang dengan bobot lebih tinggi pada periode terbaru.",
            "exponential_smoothing": f"Single Exponential Smoothing (α={p['alpha']:g}): F_t = α·A_{{t-1}} + (1 − α)·F_{{t-1}}.",
            "trend_adjusted_exponential_smoothing": f"Holt Trend-Adjusted Exponential Smoothing (α={p['alpha']:g}, β={p['beta']:g}): menangkap level (F_t) dan tren (T_t).",
            "linear_regression": f"Regresi Tren Linear (OLS): {extra_note}",
            "causal_regression": f"Regresi Kausal Linear (OLS): {extra_note}",
            "seasonal": f"Dekomposisi Musiman Multiplikatif (panjang musim={p['season_length']}): {extra_note}",
        }[m]
        avg_y = sum(y) / len(y)
        r.analyze(
            "Metodologi Peramalan & Ringkasan Data Historis",
            f"{method_desc} Data historis mencakup {len(y)} periode (rata-rata = {avg_y:,.2f}, rentang = {min(y):,.2f} s.d. {max(y):,.2f}).",
            [
                f"Proyeksi periode berikutnya: {next_f:,.4f} ({((next_f - avg_y) / avg_y * 100.0) if abs(avg_y) > 1e-12 else 0.0:+.1f}% terhadap rata-rata historis).",
                f"Evaluasi dilakukan pada {em['n']} periode yang memiliki pasangan (Aktual, Ramalan).",
            ],
        )

        mape = em["mape"]
        mape_tier = (
            "sangat akurat (<10%)" if mape < 10 else
            "baik (10%–20%)" if mape < 20 else
            "cukup / layak (20%–50%)" if mape < 50 else
            "kurang akurat (>50%)"
        )
        bias_dir = (
            "hampir bebas bias (seimbang)" if abs(em["bias"]) <= 0.05 * em["mad"] else
            f"under-forecast rata-rata {em['bias']:+,.3f} (ramalan cenderung terlalu rendah dari aktual)" if em["bias"] > 0 else
            f"over-forecast rata-rata {em['bias']:+,.3f} (ramalan cenderung terlalu tinggi dari aktual)"
        )
        ts = em["tracking_signal"]
        ts_status = "TERKENDALI (dalam batas ±4)" if abs(ts) <= 4.0 else "DI LUAR KENDALI (melebihi ±4 — indikasi bias sistematis!)"
        ratio = em["rmse"] / em["mad"] if em["mad"] > 1e-12 else 1.0
        r.analyze(
            "Diagnostik Akurasi, Bias & Tracking Signal",
            "Evaluasi komprehensif terhadap kesalahan peramalan historis untuk menilai kelayakan model:",
            [
                f"Akurasi Relatif (MAPE = {mape:.2f}%): tergolong {mape_tier} berdasarkan skala akurasi Lewis.",
                f"Kesalahan Absolut & Kuadrat: MAD = {em['mad']:,.3f}, RMSE = {em['rmse']:,.3f} (MSE = {em['mse']:,.3f}). "
                f"Rasio RMSE/MAD = {ratio:.2f} (nilai normal ≈ 1.25; nilai > 1.4 mengindikasikan adanya lonjakan/outlier error).",
                f"Analisis Bias: Mean Error = {em['bias']:+,.3f} → model {bias_dir}.",
                f"Tracking Signal = {ts:+.2f} → status {ts_status}.",
            ],
        )

        rec_bullets: list[str] = []
        if abs(ts) > 4.0:
            rec_bullets.append("Tracking Signal keluar dari batas ±4: segera kalibrasi ulang parameter (naikkan α atau beralih ke metode ber-tren/musiman) karena model gagal mengikuti pergeseran permintaan.")
        else:
            rec_bullets.append("Tracking Signal masih berada di zona aman (±4), sehingga model layak dipakai untuk perencanaan jangka pendek dengan pemantauan berkala.")
        if m == "exponential_smoothing":
            rec_bullets.append(
                f"Dengan α={p['alpha']:g}, bobot pada observasi terbaru sebesar {p['alpha']*100:.0f}%; "
                "coba bandingkan nilai α berbeda (mis. 0.1–0.5) dan pilih yang menghasilkan MAD/MSE terkecil."
            )
        elif m in {"linear_regression", "causal_regression"}:
            rec_bullets.append("Waspadai ekstrapolasi terlalu jauh di luar rentang data historis dan periksa nilai R² untuk memastikan kekuatan hubungan linear.")
        elif m == "seasonal":
            rec_bullets.append("Gunakan indeks musiman untuk menyusun rencana stok pengaman dan kapasitas puncak pada periode berindeks > 1.0.")
        else:
            rec_bullets.append("Bandingkan performa MAD & MAPE dengan metode alternatif (Exponential Smoothing / Trend / Musiman) pada data yang sama untuk memastikan model terbaik.")
        r.analyze("Rekomendasi Pemilihan Model & Perencanaan", "Saran optimasi model peramalan:", rec_bullets)
        return r
