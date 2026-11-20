"""Modul Acceptance Sampling (Kurva OC, Risiko Produsen/Konsumen, AOQ/AOQL)."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import binom, poisson

from optiqm.core import BaseModule, InputError, ModuleResult, ParamSpec, SheetData, register


@register
class AcceptanceSampling(BaseModule):
    key = "acceptance_sampling"
    name = "Acceptance Sampling"
    category = "Kualitas & Keandalan"
    description = "Evaluasi rencana sampling penerimaan lot (n, c): kurva OC, risiko produsen α, risiko konsumen β, dan AOQL."
    sheet_prefixes = ("AS", "SAMPLING")
    params = (
        ParamSpec("n", "Ukuran Sampel (n)", "integer", 50),
        ParamSpec("c", "Batas Penerimaan Cacat (c)", "integer", 2),
        ParamSpec("aql", "AQL (proporsi cacat, mis. 0.02)", "number", 0.02),
        ParamSpec("ltpd", "LTPD (proporsi cacat, mis. 0.10)", "number", 0.10),
        ParamSpec("lot_size", "Ukuran Lot (N)", "integer", 1000),
        ParamSpec("distribution", "Distribusi", "choice", "binomial", ("binomial", "poisson")),
    )
    table_hint = "Atur parameter n, c, AQL, LTPD, ukuran lot N."

    def template(self) -> SheetData:
        return SheetData(
            params={"n": 50, "c": 2, "aql": 0.02, "ltpd": 0.10, "lot_size": 1000, "distribution": "binomial"},
        )

    def solve(self, data: SheetData) -> ModuleResult:
        par = self.resolved_params_with_table(data)
        n, c = int(par["n"]), int(par["c"])
        N = int(par["lot_size"])
        aql, ltpd = float(par["aql"]), float(par["ltpd"])
        aql = aql / 100.0 if aql > 1.0 else aql
        ltpd = ltpd / 100.0 if ltpd > 1.0 else ltpd
        if n < 1 or c < 0 or c > n:
            raise InputError("Ukuran sampel n >= 1 dan 0 <= c <= n.")
        if N < 0 or (0 < N < n):
            raise InputError("Ukuran lot N harus ≥ ukuran sampel n (atau 0 untuk lot tak hingga).")
        if not (0.0 <= aql <= 1.0) or not (0.0 <= ltpd <= 1.0):
            raise InputError("AQL dan LTPD harus berada di rentang 0..1 (atau 0%..100%).")

        def pa(p_def: float) -> float:
            if par["distribution"] == "poisson":
                return float(poisson.cdf(c, n * p_def))
            return float(binom.cdf(c, n, p_def))

        def aoq_fn(p_def: float) -> float:
            if N == 0:
                return p_def * pa(p_def)
            if N == n:
                return 0.0
            return p_def * pa(p_def) * (N - n) / N

        alpha = 1.0 - pa(aql)
        beta = pa(ltpd)
        # Cari AOQL eksak pada grid rapat [0, 1]
        fine_ps = np.linspace(0.0, 1.0, 1001)
        fine_aoqs = [aoq_fn(float(pv)) for pv in fine_ps]
        aoql_idx = int(np.argmax(fine_aoqs))
        aoql = fine_aoqs[aoql_idx]
        p_aoql = float(fine_ps[aoql_idx])

        ps = np.linspace(0.0, min(0.5, max(ltpd * 2.5, 0.2)), 21)
        pas = [pa(float(pv)) for pv in ps]
        aoqs = [aoq_fn(float(pv)) for pv in ps]
        ati_aql = n + (1.0 - pa(aql)) * max(0, N - n) if N > 0 else float(n)
        ati_ltpd = n + (1.0 - pa(ltpd)) * max(0, N - n) if N > 0 else float(n)

        r = ModuleResult()
        r.metric("Risiko Produsen (α pada AQL)", f"{alpha * 100:.2f}%", highlight=True)
        r.metric("Risiko Konsumen (β pada LTPD)", f"{beta * 100:.2f}%", highlight=True)
        r.metric("AOQL (Maksimum Rata-rata Cacat Lolos)", f"{aoql * 100:.3f}%")
        r.metric("P(Terima pada AQL)", f"{(1 - alpha) * 100:.2f}%")

        r.table("Kurva OC & AOQ", ["Proporsi Cacat (p)", "Probabilitas Terima Pa", "AOQ"],
                [[float(pv), pa_v, aoq_v] for pv, pa_v, aoq_v in zip(ps, pas, aoqs)])
        r.chart("Operating Characteristic (OC) Curve", "line", {
            "x": [f"{pv * 100:.1f}%" for pv in ps],
            "series": [{"name": "Pa (Prob. Penerimaan)", "data": pas}],
            "x_label": "Proporsi Cacat Lot (%)", "y_label": "Probabilitas Terima",
        })
        r.interpretation = (f"Rencana sampling (n={n}, c={c}): risiko produsen α={alpha*100:.2f}% (pada AQL={aql*100:.1f}%), "
                            f"risiko konsumen β={beta*100:.2f}% (pada LTPD={ltpd*100:.1f}%), AOQL={aoql*100:.2f}%.")

        # Analisis mendalam
        r.analyze(
            "Metodologi Rencana Sampling Penerimaan (Single Sampling Plan)",
            f"Evaluasi dilakukan dengan distribusi {par['distribution'].capitalize()} untuk sampel n = {n}, batas terima c = {c}, "
            f"ukuran lot N = {'∞' if N == 0 else N}, AQL = {aql * 100:.2f}%, dan LTPD = {ltpd * 100:.2f}%.",
            [
                f"Risiko Produsen (α = 1 − Pa(AQL)): peluang lot berkualitas baik (cacat {aql*100:.2f}%) ditolak secara keliru = {alpha*100:.2f}%.",
                f"Risiko Konsumen (β = Pa(LTPD)): peluang lot berkualitas buruk (cacat {ltpd*100:.2f}%) lolos diterima = {beta*100:.2f}%.",
                f"AOQL Eksak = {aoql * 100:.3f}% (terjadi saat tingkat cacat lot masuk p ≈ {p_aoql * 100:.2f}%): rata-rata proporsi cacat keluar tidak akan melampaui angka ini dengan inspeksi rektifikasi 100% pada lot ditolak.",
            ],
        )
        r.analyze(
            "Evaluasi Risiko & Beban Inspeksi (ATI)",
            "Menilai keseimbangan antara perlindungan kualitas konsumen, keadilan terhadap produsen, dan biaya inspeksi:",
            [
                f"Kelayakan α ({alpha*100:.2f}% vs standar 5%): {'MEMENUHI (≤ 5%)' if alpha <= 0.05 else 'TINGGI (> 5% — banyak lot bagus berisiko ditolak)'}.",
                f"Kelayakan β ({beta*100:.2f}% vs standar 10%): {'MEMENUHI (≤ 10%)' if beta <= 0.10 else 'TINGGI (> 10% — perlindungan konsumen masih lemah)'}.",
                f"Average Total Inspection (ATI): rata-rata {ati_aql:,.1f} unit diperiksa per lot pada AQL ({(ati_aql/N*100) if N > 0 else 100:.1f}% lot), "
                f"meningkat menjadi {ati_ltpd:,.1f} unit pada LTPD ({(ati_ltpd/N*100) if N > 0 else 100:.1f}% lot).",
            ],
        )
        rec_bullets = []
        if alpha > 0.05 and beta > 0.10:
            rec_bullets.append("Baik α maupun β masih di atas standar (5% / 10%): kurva OC terlalu landai — perbesar ukuran sampel (n) dan sesuaikan (c) agar daya diskriminasi meningkat.")
        elif beta > 0.10:
            rec_bullets.append("Risiko konsumen β > 10%: perketat rencana dengan menurunkan c atau menaikkan n untuk mencegah lot buruk lolos ke pelanggan.")
        elif alpha > 0.05:
            rec_bullets.append("Risiko produsen α > 5%: naikkan batas c sedikit (atau perbesar n) agar lot yang sudah memenuhi AQL tidak sering ditolak.")
        else:
            rec_bullets.append(f"Rencana (n={n}, c={c}) sudah seimbang (α ≤ 5% dan β ≤ 10%) dengan batas kualitas keluar AOQL = {aoql*100:.3f}%.")
        r.analyze("Rekomendasi Perancangan Sampling", "Saran penyempurnaan rencana inspeksi:", rec_bullets)
        return r
