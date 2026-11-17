"""Modul Monte Carlo Simulation."""

from __future__ import annotations

import numpy as np
import pandas as pd

from optiqm.core import BaseModule, InputError, ModuleResult, ParamSpec, SheetData, register
from optiqm.core.parsing import clean_frame, find_column, require_rows, to_float


@register
class MonteCarloSimulation(BaseModule):
    key = "simulation"
    name = "Simulation (Monte Carlo)"
    category = "Statistik & Simulasi"
    description = "Simulasi Monte Carlo dari distribusi frekuensi/probabilitas untuk mengestimasi rata-rata hasil."
    sheet_prefixes = ("SIM", "MONTE", "SIMULASI")
    params = (
        ParamSpec("trials", "Jumlah Percobaan (Trials)", "integer", 200),
        ParamSpec("seed", "Random Seed", "integer", 42),
    )
    table_hint = "Kolom: Value (nilai outcome), dan Frequency atau Probability (bobot). Opsional blok [random] dengan kolom Random (0..1)."

    def template(self) -> SheetData:
        # Harry's Auto Tire (Heizer & Render): expected demand = 1.95
        df = pd.DataFrame(
            [[0, 10], [1, 20], [2, 40], [3, 60], [4, 40], [5, 30]],
            columns=["Value", "Frequency"],
        )
        return SheetData(params={"trials": 200, "seed": 42}, tables={"main": df})

    def solve(self, data: SheetData) -> ModuleResult:
        p = self.resolved_params(data)
        trials = max(1, int(p["trials"]))
        seed = int(p["seed"])

        df = clean_frame(data.table("main"))
        require_rows(df, 1, "Tabel distribusi probabilitas")
        c_val = find_column(df, ["Value", "Nilai", "Outcome", "Demand"])
        c_prob = find_column(df, ["Probability", "Prob", "Frequency", "Freq", "Frekuensi"])

        vals = [to_float(df.at[i, c_val], f"Value baris {i+1}") for i in range(len(df))]
        raw_w = np.array([to_float(df.at[i, c_prob], f"Freq/Prob baris {i+1}") for i in range(len(df))], dtype=float)
        if (raw_w < 0).any() or raw_w.sum() <= 0:
            raise InputError("Frekuensi/probabilitas harus >= 0 dan total > 0.")
        probs = raw_w / raw_w.sum()
        cum = np.cumsum(probs)
        expected = float(np.dot(vals, probs))

        rng_tbl = data.table("random", required=False)
        if rng_tbl is not None and len(clean_frame(rng_tbl)) > 0:
            rdf = clean_frame(rng_tbl)
            rn_col = find_column(rdf, ["Random", "RN", "U", "Rand"], required=False) or rdf.columns[0]
            rands = np.array([to_float(x, "Random") for x in rdf[rn_col]])
            if (rands > 1.0).any():
                rands = rands / 100.0
            trials = len(rands)
        else:
            rands = np.random.default_rng(seed).random(trials)

        outcomes = [vals[min(int(np.searchsorted(cum, u, side="right")), len(vals) - 1)] for u in rands]
        sim_mean = float(np.mean(outcomes))
        sim_std = float(np.std(outcomes, ddof=1)) if trials > 1 else 0.0

        r = ModuleResult()
        r.metric("Rata-rata Simulasi", sim_mean, highlight=True)
        r.metric("Nilai Harapan Teoritis", expected, highlight=True)
        r.metric("Simpangan Baku Simulasi", sim_std)
        r.metric("Jumlah Percobaan", trials)

        prev = 0.0
        dist_rows = []
        for v, pr, cm in zip(vals, probs, cum):
            dist_rows.append([v, pr, cm, f"{prev:.4f} – {cm:.4f}"])
            prev = float(cm)
        r.table("Distribusi & Interval Angka Acak", ["Nilai", "Probabilitas", "Kumulatif", "Interval"], dist_rows)
        r.table("Sampel Hasil Simulasi (maks 50 baris)", ["Percobaan", "Angka Acak", "Hasil"],
                [[k + 1, float(rands[k]), outcomes[k]] for k in range(min(50, trials))])

        counts = [sum(1 for x in outcomes if x == v) for v in vals]
        r.chart("Distribusi Frekuensi Hasil Simulasi", "bar", {
            "x": [str(v) for v in vals],
            "series": [
                {"name": "Frekuensi Simulasi", "data": counts},
                {"name": "Frekuensi Harapan", "data": [float(pr * trials) for pr in probs]},
            ],
            "x_label": "Outcome", "y_label": "Frekuensi",
        })
        r.interpretation = f"Dari {trials} simulasi diperoleh rata-rata {sim_mean:,.4f} (nilai harapan teoritis = {expected:,.4f})."
        return r
