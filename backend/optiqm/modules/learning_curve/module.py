"""Modul Learning Curve (Kurva Belajar Wright)."""

from __future__ import annotations

import math

import pandas as pd

from optiqm.core import BaseModule, InputError, ModuleResult, ParamSpec, SheetData, register


@register
class LearningCurve(BaseModule):
    key = "learning_curve"
    name = "Learning Curve"
    category = "Produktivitas & Kerja"
    description = "Memperkirakan waktu produksi per unit dan kumulatif berdasarkan tingkat pembelajaran (%)."
    sheet_prefixes = ("LC", "LEARNING")
    params = (
        ParamSpec("first_unit_time", "Waktu Unit Pertama (T₁)", "number", 100.0),
        ParamSpec("learning_rate", "Learning Rate (%, mis. 80)", "number", 80.0),
        ParamSpec("target_unit", "Nomor Unit Target (N)", "integer", 10),
    )
    table_hint = "Atur T₁, Learning Rate (%), dan jumlah unit target N."

    def template(self) -> SheetData:
        return SheetData(
            params={"first_unit_time": 100, "learning_rate": 80, "target_unit": 8},
        )

    def solve(self, data: SheetData) -> ModuleResult:
        p = self.resolved_params_with_table(data)
        t1 = float(p["first_unit_time"])
        lr = float(p["learning_rate"])
        lr = lr / 100.0 if lr > 1.0 else lr
        N = int(p["target_unit"])
        if t1 <= 0 or not (0.0 < lr <= 1.0) or N < 1 or N > 5000:
            raise InputError("T₁ > 0, learning rate (0..100%), dan N antara 1..5000.")

        b = math.log(lr) / math.log(2.0)
        rows = []
        cum = 0.0
        for n in range(1, N + 1):
            tn = t1 * (n ** b)
            cum += tn
            rows.append([n, tn, cum, cum / n])

        t_n = rows[-1][1]
        no_learn_cum = t1 * N
        saved_cum = no_learn_cum - cum
        saved_pct = (saved_cum / no_learn_cum * 100.0) if no_learn_cum > 0 else 0.0

        r = ModuleResult()
        r.metric(f"Waktu Unit ke-{N}", t_n, highlight=True)
        r.metric(f"Waktu Kumulatif (1..{N})", cum, highlight=True)
        r.metric("Rata-rata Waktu / Unit", cum / N)
        r.metric("Eksponen b", b)
        r.table("Kurva Belajar per Unit", ["Unit ke-", "Waktu Unit", "Waktu Kumulatif", "Rata-rata Kumulatif"], rows[:100])
        r.chart("Kurva Penurunan Waktu per Unit", "line", {
            "x": [str(row[0]) for row in rows[:50]],
            "series": [
                {"name": "Waktu per Unit", "data": [row[1] for row in rows[:50]]},
                {"name": "Rata-rata Kumulatif", "data": [row[3] for row in rows[:50]]},
            ], "x_label": "Unit ke-", "y_label": "Waktu",
        })
        r.interpretation = f"Pada learning rate {lr*100:.0f}%, unit ke-{N} membutuhkan {t_n:,.2f} dan total {N} unit = {cum:,.2f}."

        # Analisis mendalam
        doubles = [f"Unit #{k}: {t1 * (k ** b):,.2f}" for k in (1, 2, 4, 8, 16) if k <= N]
        r.analyze(
            "Metodologi Kurva Belajar Wright (Log-Linear)",
            f"Model Wright menyatakan bahwa setiap kali volume produksi kumulatif berlipat dua (2×), waktu pengerjaan turun menjadi {lr * 100:.1f}% dari sebelumnya (turun {(1 - lr) * 100:.1f}%).",
            [
                f"Eksponen belajar b = ln({lr:.4f}) / ln(2) = {b:.4f}.",
                f"Substitusi Unit ke-{N}: T_{N} = {t1:g} × {N}^({b:.4f}) = {t_n:,.2f} (turun {(1 - t_n / t1) * 100:.1f}% dari unit pertama).",
                f"Verifikasi Hukum Penggandaan: {' → '.join(doubles)}.",
            ],
        )
        r.analyze(
            "Analisis Penghematan Kumulatif & Biaya Marjinal",
            "Perbandingan terhadap skenario tanpa efek belajar (waktu konstan = T₁) memperlihatkan skala efisiensi yang tercipta:",
            [
                f"Tanpa kurva belajar ({N} × {t1:g}): total waktu = {no_learn_cum:,.2f}; dengan kurva belajar {lr * 100:.0f}%: total = {cum:,.2f}.",
                f"Penghematan waktu kumulatif = {saved_cum:,.2f} ({saved_pct:.1f}%), dengan rata-rata turun dari {t1:g} menjadi {cum / N:,.2f}/unit.",
                f"Proyeksi unit ke-{N * 2} (jika volume dilipatgandakan lagi): T_{N * 2} = {t_n * lr:,.2f} (hemat tambahan {t_n * (1 - lr):,.2f}/unit).",
            ],
        )
        r.analyze(
            "Rekomendasi Penetapan Harga & Perencanaan Tenaga Kerja",
            "Implikasi praktis untuk perhitungan tender, kapasitas, dan kontrak produksi:",
            [
                f"Gunakan rata-rata kumulatif ({cum / N:,.2f}/unit) untuk menghitung total harga pokok paket pesanan {N} unit, dan gunakan waktu marjinal ({t_n:,.2f}/unit) sebagai acuan penetapan harga pesanan tambahan (repeat order).",
                "Waspadai asumsi kurva belajar: laju perbaikan akan melambat secara alami pada volume besar dan dapat hilang/ter-reset bila terjadi perubahan desain produk atau tingkat turnover operator yang tinggi.",
            ],
        )
        return r
