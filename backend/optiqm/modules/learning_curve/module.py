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
            tables={"main": pd.DataFrame([["first_unit_time", 100], ["learning_rate", 80], ["target_unit", 8]],
                                         columns=["Parameter", "Value"])},
        )

    def solve(self, data: SheetData) -> ModuleResult:
        p = self.resolved_params(data)
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

        r = ModuleResult()
        r.metric(f"Waktu Unit ke-{N}", rows[-1][1], highlight=True)
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
        r.interpretation = f"Pada learning rate {lr*100:.0f}%, unit ke-{N} membutuhkan {rows[-1][1]:,.2f} dan total {N} unit = {cum:,.2f}."
        return r
