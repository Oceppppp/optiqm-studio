"""Metrik akurasi peramalan (MAD, MSE, RMSE, MAPE, Bias, Tracking Signal)."""

from __future__ import annotations

import math

import numpy as np


def error_metrics(actual: list[float], forecast: list[float | None]) -> dict:
    rows = []
    errs = []
    abs_errs = []
    sq_errs = []
    pct_errs = []
    for i, (y, f) in enumerate(zip(actual, forecast)):
        if f is None or (isinstance(f, float) and math.isnan(f)):
            rows.append([y, None, None, None, None, None])
            continue
        e = y - f
        ae = abs(e)
        se = e * e
        pe = (ae / abs(y) * 100.0) if abs(y) > 1e-12 else None
        errs.append(e); abs_errs.append(ae); sq_errs.append(se)
        if pe is not None:
            pct_errs.append(pe)
        rows.append([y, f, e, ae, se, pe])

    n = len(errs)
    mad = float(np.mean(abs_errs)) if n else 0.0
    mse = float(np.mean(sq_errs)) if n else 0.0
    rmse = math.sqrt(mse)
    mape = float(np.mean(pct_errs)) if pct_errs else 0.0
    bias = float(np.mean(errs)) if n else 0.0
    cum_err = float(np.sum(errs)) if n else 0.0
    ts = (cum_err / mad) if mad > 1e-12 else 0.0
    return {
        "rows": rows, "n": n, "mad": mad, "mse": mse, "rmse": rmse,
        "mape": mape, "bias": bias, "cum_err": cum_err, "tracking_signal": ts,
    }
