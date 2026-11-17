"""Modul Error Analysis (Evaluasi Akurasi Ramalan / Prediksi)."""

from __future__ import annotations

import pandas as pd

from optiqm.core import BaseModule, ModuleResult, SheetData, register
from optiqm.core.parsing import clean_frame, find_column, require_rows, to_float
from optiqm.modules.forecasting.metrics import error_metrics


@register
class ErrorAnalysis(BaseModule):
    key = "error_analysis"
    name = "Forecast Error Analysis"
    category = "Statistik & Simulasi"
    description = "Mengevaluasi akurasi hasil peramalan yang sudah ada (MAD, MSE, RMSE, MAPE, Bias, Tracking Signal)."
    sheet_prefixes = ("ERR", "ERROR")
    table_hint = "Kolom: Period (opsional), Actual, Forecast."

    def template(self) -> SheetData:
        df = pd.DataFrame(
            [["P1", 100, 95], ["P2", 110, 105], ["P3", 105, 112], ["P4", 120, 115], ["P5", 130, 125]],
            columns=["Period", "Actual", "Forecast"],
        )
        return SheetData(tables={"main": df})

    def solve(self, data: SheetData) -> ModuleResult:
        df = clean_frame(data.table("main"))
        require_rows(df, 1, "Tabel perbandingan Aktual vs Forecast")
        c_act = find_column(df, ["Actual", "Aktual", "Y", "Demand"])
        c_fc = find_column(df, ["Forecast", "Ramalan", "Prediksi", "F"])
        c_per = find_column(df, ["Period", "Periode"], required=False)

        periods = [str(df.at[i, c_per]) if c_per else f"P{i+1}" for i in range(len(df))]
        actual = [to_float(df.at[i, c_act], f"Actual {periods[i]}") for i in range(len(df))]
        forecast = [to_float(df.at[i, c_fc], f"Forecast {periods[i]}") for i in range(len(df))]
        em = error_metrics(actual, forecast)

        r = ModuleResult()
        r.metric("MAD", em["mad"], highlight=True)
        r.metric("MSE", em["mse"])
        r.metric("RMSE", em["rmse"])
        r.metric("MAPE", em["mape"], unit="%", highlight=True)
        r.metric("Tracking Signal", em["tracking_signal"])
        r.table("Rincian Error per Periode",
                ["Periode", "Aktual", "Ramalan", "Error", "|Error|", "Error²", "|% Error|"],
                [[periods[i], *row] for i, row in enumerate(em["rows"])])
        r.chart("Aktual vs Ramalan", "line", {
            "x": periods,
            "series": [{"name": "Aktual", "data": actual}, {"name": "Ramalan", "data": forecast}],
            "x_label": "Periode", "y_label": "Nilai",
        })
        r.interpretation = f"MAD = {em['mad']:,.3f}, RMSE = {em['rmse']:,.3f}, MAPE = {em['mape']:.2f}%, Tracking Signal = {em['tracking_signal']:.2f}."
        return r
