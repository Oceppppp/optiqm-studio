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
        using_custom_rng = False
        if rng_tbl is not None and len(clean_frame(rng_tbl)) > 0:
            rdf = clean_frame(rng_tbl)
            rn_col = find_column(rdf, ["Random", "RN", "U", "Rand"], required=False) or rdf.columns[0]
            rands = np.array([to_float(x, "Random") for x in rdf[rn_col]], dtype=float)
            if (rands < 0.0).any():
                raise InputError("Angka acak pada tabel [random] tidak boleh negatif.")
            if (rands > 1.0).any():
                if (rands > 100.0).any():
                    raise InputError("Angka acak pada tabel [random] harus dalam rentang 0..1 atau 0..100.")
                rands = rands / 100.0
            trials = len(rands)
            using_custom_rng = True
        else:
            rands = np.random.default_rng(seed).random(trials)

        outcomes = [vals[min(int(np.searchsorted(cum, u, side="right")), len(vals) - 1)] for u in rands]
        sim_mean = float(np.mean(outcomes))
        sim_std = float(np.std(outcomes, ddof=1)) if trials > 1 else 0.0
        theo_var = float(sum(pr * ((v - expected) ** 2) for v, pr in zip(vals, probs)))
        theo_std = float(np.sqrt(max(0.0, theo_var)))
        se = sim_std / float(np.sqrt(trials)) if trials > 0 else 0.0
        ci_lo, ci_hi = sim_mean - 1.96 * se, sim_mean + 1.96 * se

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

        # Analisis mendalam
        err_abs = abs(sim_mean - expected)
        err_pct = (err_abs / abs(expected) * 100.0) if abs(expected) > 1e-12 else 0.0
        in_ci = ci_lo <= expected <= ci_hi
        mode_idx = int(np.argmax(counts))
        r.analyze(
            "Metodologi Simulasi Monte Carlo (Inverse Transform)",
            f"Menjalankan {trials:,} percobaan acak ({'menggunakan angka acak kustom [random]' if using_custom_rng else f'generator PCG64 seed={seed}'}) "
            f"dengan memetakan U(0,1) ke {len(vals)} interval probabilitas kumulatif.",
            [
                f"Nilai Harapan Teoritis E[X] = Σ(x_i·p_i) = {expected:,.4f}; Std. Deviasi Teoritis σ = {theo_std:,.4f}.",
                f"Hasil Simulasi: Rata-rata x̄ = {sim_mean:,.4f}; Std. Deviasi s = {sim_std:,.4f}; Galat Baku (SE = s/√N) = {se:,.4f}.",
            ],
        )
        r.analyze(
            "Uji Konvergensi & Interval Kepercayaan 95%",
            "Berdasarkan Hukum Bilangan Besar (Law of Large Numbers), rata-rata simulasi akan semakin mendekati nilai harapan teoritis seiring bertambahnya jumlah percobaan:",
            [
                f"Selisih Simulasi vs Teoritis: |x̄ − E[X]| = {err_abs:,.4f} ({err_pct:.2f}%).",
                f"Interval Kepercayaan 95% rata-rata simulasi: [{ci_lo:,.4f}, {ci_hi:,.4f}] → nilai teoritis E[X] berada "
                f"{'DI DALAM interval (simulasi konsisten dan bebas bias).' if in_ci else 'DI LUAR interval (variasi acak cukup besar — pertimbangkan menambah jumlah percobaan).'}",
                f"Outcome paling dominan muncul: nilai {vals[mode_idx]:g} sebanyak {counts[mode_idx]} kali ({counts[mode_idx] / trials * 100:.1f}% vs ekspektasi {probs[mode_idx] * 100:.1f}%).",
            ],
        )
        r.analyze(
            "Rekomendasi Presisi Simulasi",
            "Panduan meningkatkan akurasi estimasi Monte Carlo:",
            [
                f"Margin of error 95% saat ini adalah ±{1.96 * se:,.4f}. Untuk memangkas margin kesalahan menjadi separuhnya, naikkan jumlah percobaan menjadi ≈ {trials * 4:,} trials (hukum 1/√N).",
                "Gunakan hasil simulasi ini bersama skenario ekstrem (persentil min/maks) untuk merancang kapasitas penyangga terhadap fluktuasi permintaan.",
            ],
        )
        return r
