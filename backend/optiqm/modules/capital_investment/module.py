"""Modul Capital Investment (NPV, IRR, Payback Period, Profitability Index)."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import brentq

from optiqm.core import BaseModule, InputError, ModuleResult, ParamSpec, SheetData, register
from optiqm.core.parsing import clean_frame, find_column, require_rows, to_float


def _irr(cfs: list[float]) -> float | None:
    def npv_fn(r: float) -> float:
        return sum(cf / ((1.0 + r) ** t) for t, cf in enumerate(cfs))
    if not (any(x < 0 for x in cfs) and any(x > 0 for x in cfs)):
        return None
    try:
        return float(brentq(npv_fn, -0.95, 5.0))
    except ValueError:
        return None


def _payback(cfs: list[float]) -> float | None:
    cum = cfs[0]
    if cum >= 0:
        return 0.0
    for t in range(1, len(cfs)):
        prev = cum
        cum += cfs[t]
        if cum >= 0 and cfs[t] > 0:
            return (t - 1) + abs(prev) / cfs[t]
    return None


@register
class CapitalInvestment(BaseModule):
    key = "capital_investment"
    name = "Capital Investment (NPV & IRR)"
    category = "Biaya & Keuangan"
    description = "Evaluasi kelayakan investasi (Net Present Value, IRR, Payback Period, dan Profitability Index)."
    sheet_prefixes = ("NPV", "IRR", "INVEST")
    params = (ParamSpec("discount_rate", "Tingkat Diskonto / Bunga (%)", "number", 10.0),)
    table_hint = "Kolom: Year (tahun 0, 1, 2, ...), diikuti kolom arus kas satu atau lebih proyek (tahun 0 negatif)."

    def template(self) -> SheetData:
        df = pd.DataFrame(
            [[0, -100000, -120000], [1, 35000, 30000], [2, 40000, 45000], [3, 45000, 55000], [4, 30000, 60000]],
            columns=["Year", "Proyek A", "Proyek B"],
        )
        return SheetData(params={"discount_rate": 10}, tables={"main": df})

    def solve(self, data: SheetData) -> ModuleResult:
        p = self.resolved_params(data)
        rate = float(p["discount_rate"])
        rate = rate / 100.0 if rate > 1.0 else rate
        if rate <= -1.0:
            raise InputError("Discount rate tidak valid.")

        df = clean_frame(data.table("main"))
        require_rows(df, 2, "Tabel arus kas")
        c_yr = find_column(df, ["Year", "Tahun", "Period", "t"], required=False) or df.columns[0]
        projs = [c for c in df.columns if c != c_yr]
        if not projs:
            raise InputError("Minimal harus ada 1 kolom proyek.")
        years = [int(round(to_float(df.at[i, c_yr], "Year"))) for i in range(len(df))]

        summary_rows = []
        npvs = []
        for pr in projs:
            cfs = [to_float(df.at[i, pr], f"{pr} tahun {years[i]}") for i in range(len(df))]
            pvs = [cf / ((1.0 + rate) ** t) for t, cf in zip(years, cfs)]
            npv = sum(pvs)
            init_out = -cfs[0] if cfs[0] < 0 else sum(-c for c in cfs if c < 0)
            pi = (npv + init_out) / init_out if init_out > 0 else None
            irr_v = _irr(cfs)
            pb = _payback(cfs)
            npvs.append(npv)
            summary_rows.append([pr, npv, f"{irr_v * 100:.2f}%" if irr_v is not None else "-",
                                 f"{pb:.2f} thn" if pb is not None else "Tidak kembali",
                                 pi if pi is not None else "-", "Layak (NPV > 0)" if npv > 0 else "Tidak Layak"])

        best_i = int(np.argmax(npvs))
        r = ModuleResult()
        r.metric("Proyek Terbaik (NPV)", projs[best_i], highlight=True)
        r.metric(f"NPV ({projs[best_i]})", npvs[best_i], highlight=True)
        r.table("Evaluasi Kelayakan Proyek",
                ["Proyek", f"NPV (@{rate*100:.1f}%)", "IRR", "Payback Period", "Profitability Index", "Keputusan"],
                summary_rows)
        r.chart("Perbandingan NPV Proyek", "bar", {
            "x": projs, "series": [{"name": "NPV", "data": npvs}],
            "x_label": "Proyek", "y_label": "NPV",
        })
        r.interpretation = f"Dengan tingkat diskonto {rate*100:.1f}%, proyek terbaik adalah '{projs[best_i]}' (NPV = {npvs[best_i]:,.2f})."
        return r
