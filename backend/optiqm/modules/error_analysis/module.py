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

        # Analisis mendalam
        mape = em["mape"]
        mape_tier = (
            "sangat akurat (<10%)" if mape < 10 else
            "baik (10%–20%)" if mape < 20 else
            "cukup (20%–50%)" if mape < 50 else
            "kurang akurat (>50%)"
        )
        ts = em["tracking_signal"]
        ratio = em["rmse"] / em["mad"] if em["mad"] > 1e-12 else 1.0
        worst_i = max(range(len(periods)), key=lambda i: abs(actual[i] - forecast[i]))
        worst_e = actual[worst_i] - forecast[worst_i]
        r.analyze(
            "Metodologi Evaluasi Akurasi Peramalan",
            f"Mengevaluasi {em['n']} pasangan observasi (Aktual vs Ramalan) dengan definisi error e_t = Aktual_t − Ramalan_t.",
            [
                f"MAD = Σ|e|/n = {em['mad']:,.3f}; MSE = Σe²/n = {em['mse']:,.3f}; RMSE = √MSE = {em['rmse']:,.3f}.",
                f"MAPE = {mape:.2f}% (kategori Lewis: {mape_tier}); Mean Error (Bias) = {em['bias']:+,.3f}; Cumulative Error = {em['cum_err']:+,.3f}.",
                f"Tracking Signal (TS = Σe / MAD) = {ts:+.2f}.",
            ],
        )
        bias_desc = (
            "hampir bebas bias" if abs(em["bias"]) <= 0.05 * em["mad"] else
            f"under-forecast sistematis sebesar {em['bias']:+,.3f}/periode (ramalan konsisten terlalu rendah)" if em["bias"] > 0 else
            f"over-forecast sistematis sebesar {em['bias']:+,.3f}/periode (ramalan konsisten terlalu tinggi)"
        )
        r.analyze(
            "Diagnostik Bias, Tracking Signal & Periode Anomali",
            "Memeriksa apakah kesalahan bersifat acak atau mengandung bias terarah:",
            [
                f"Arah Bias: {bias_desc}.",
                f"Kontrol Tracking Signal: TS = {ts:+.2f} → {'TERKENDALI (dalam batas ±4)' if abs(ts) <= 4.0 else 'MELEBIHI BATAS KENDALI ±4 (model bias!)'}.",
                f"Rasio RMSE / MAD = {ratio:.2f} (nilai normal ≈ 1.25); kesalahan terbesar terjadi pada periode '{periods[worst_i]}' (Aktual={actual[worst_i]:g}, Ramalan={forecast[worst_i]:g}, Error={worst_e:+g}).",
            ],
        )
        rec_bullets = []
        if abs(ts) > 4.0:
            rec_bullets.append("Tracking Signal melampaui ±4: segera revisi metode peramalan (pertimbangkan Holt Trend-Adjusted atau Dekomposisi Musiman) agar tidak terus-menerus meleset ke satu arah.")
        else:
            rec_bullets.append("Tracking Signal berada dalam batas kendali (±4); kesalahan relatif seimbang antara positif dan negatif.")
        if ratio > 1.4:
            rec_bullets.append(f"Rasio RMSE/MAD tinggi ({ratio:.2f}): periksa periode '{periods[worst_i]}' untuk mengetahui apakah lonjakan error disebabkan event khusus/promosi/gangguan pasokan.")
        rec_bullets.append(f"Gunakan estimasi simpangan baku error σ_e ≈ 1.25 × MAD = {1.25 * em['mad']:,.2f} sebagai masukan perhitungan Safety Stock bila data permintaan mengikuti model ramalan ini.")
        r.analyze("Rekomendasi Kalibrasi Peramalan", "Tindak lanjut peningkatan akurasi:", rec_bullets)
        return r
