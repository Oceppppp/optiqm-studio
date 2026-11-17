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
        return r
