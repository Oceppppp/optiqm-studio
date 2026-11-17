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
            tables={"main": pd.DataFrame([["n", 50], ["c", 2], ["aql", 0.02], ["ltpd", 0.10], ["lot_size", 1000]],
                                         columns=["Parameter", "Value"])},
        )

    def solve(self, data: SheetData) -> ModuleResult:
        par = self.resolved_params(data)
        n, c = int(par["n"]), int(par["c"])
        N = int(par["lot_size"])
        aql, ltpd = float(par["aql"]), float(par["ltpd"])
        aql = aql / 100.0 if aql > 1.0 else aql
        ltpd = ltpd / 100.0 if ltpd > 1.0 else ltpd
        if n < 1 or c < 0 or c > n:
            raise InputError("Ukuran sampel n >= 1 dan 0 <= c <= n.")

        def pa(p_def: float) -> float:
            if par["distribution"] == "poisson":
                return float(poisson.cdf(c, n * p_def))
            return float(binom.cdf(c, n, p_def))

        alpha = 1.0 - pa(aql)
        beta = pa(ltpd)
        ps = np.linspace(0.0, min(0.5, max(ltpd * 2.5, 0.2)), 21)
        pas = [pa(float(pv)) for pv in ps]
        aoqs = [float(pv) * pa_v * (N - n) / N if N > n else float(pv) * pa_v for pv, pa_v in zip(ps, pas)]
        aoql = max(aoqs)

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
        return r
