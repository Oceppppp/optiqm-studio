"""Metode-metode peramalan deret waktu & kausal (konvensi POM-QM / Heizer-Render)."""

from __future__ import annotations

import numpy as np

from optiqm.core import InputError


def naive(y: list[float]) -> tuple[list[float | None], float]:
    fc = [None] + y[:-1]
    return fc, y[-1]


def moving_average(y: list[float], k: int) -> tuple[list[float | None], float]:
    if k < 1 or k > len(y):
        raise InputError(f"Panjang Moving Average ({k}) harus antara 1 dan {len(y)}.")
    fc: list[float | None] = [None] * k + [float(np.mean(y[i - k : i])) for i in range(k, len(y))]
    return fc, float(np.mean(y[-k:]))


def weighted_moving_average(y: list[float], weights: list[float]) -> tuple[list[float | None], float]:
    k = len(weights)
    if k < 1 or k > len(y):
        raise InputError(f"Jumlah bobot ({k}) harus antara 1 dan {len(y)}.")
    w = np.array(weights, dtype=float)
    if (w < 0).any():
        raise InputError("Semua bobot WMA harus bernilai ≥ 0.")
    if abs(w.sum()) < 1e-12:
        raise InputError("Total bobot tidak boleh 0.")
    w = w / w.sum()
    fc: list[float | None] = [None] * k + [float(np.dot(w, y[i - k : i])) for i in range(k, len(y))]
    return fc, float(np.dot(w, y[-k:]))


def exponential_smoothing(y: list[float], alpha: float, f0: float | None = None) -> tuple[list[float | None], float]:
    if not (0 < alpha <= 1):
        raise InputError("Alpha harus di antara 0 dan 1 (mis. 0.3).")
    fc: list[float | None] = [y[0] if f0 is None else float(f0)]
    for i in range(1, len(y)):
        fc.append(alpha * y[i - 1] + (1.0 - alpha) * fc[-1])
    next_f = alpha * y[-1] + (1.0 - alpha) * fc[-1]
    return fc, float(next_f)


def trend_adjusted_exp(y: list[float], alpha: float, beta: float,
                       f0: float | None = None, t0: float = 0.0) -> tuple[list[float | None], float]:
    if not (0 < alpha <= 1) or not (0 <= beta <= 1):
        raise InputError("Alpha (0..1] dan Beta [0..1] harus valid.")
    F = y[0] if f0 is None else float(f0)
    T = float(t0)
    fit: list[float | None] = [F + T]
    for i in range(1, len(y)):
        # Standar Holt / Heizer-Render: F_t = a*A_{t-1} + (1-a)*(F_{t-1}+T_{t-1}), T_t = b*(F_t - F_{t-1}) + (1-b)*T_{t-1}
        F_prev = F
        F = alpha * y[i - 1] + (1.0 - alpha) * (F_prev + T)
        T = beta * (F - F_prev) + (1.0 - beta) * T
        fit.append(F + T)
    F_last = alpha * y[-1] + (1.0 - alpha) * (F + T)
    T_last = beta * (F_last - F) + (1.0 - beta) * T
    return fit, float(F_last + T_last)


def linear_regression(y: list[float], x: list[float] | None = None, x_next: float | None = None) -> dict:
    n = len(y)
    if n < 2:
        raise InputError("Regresi linear membutuhkan minimal 2 data.")
    xs = np.arange(1, n + 1, dtype=float) if x is None else np.array(x, dtype=float)
    ys = np.array(y, dtype=float)
    xm, ym = xs.mean(), ys.mean()
    denom = float(((xs - xm) ** 2).sum())
    if denom < 1e-12:
        raise InputError("Variasi variabel X nol; tidak dapat menghitung regresi.")
    b = float(((xs - xm) * (ys - ym)).sum() / denom)
    a = float(ym - b * xm)
    fc = (a + b * xs).tolist()
    ss_tot = float(((ys - ym) ** 2).sum())
    ss_res = float(((ys - np.array(fc)) ** 2).sum())
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 1e-12 else 1.0
    xn = (n + 1.0) if x_next is None else float(x_next)
    return {"fc": fc, "next": float(a + b * xn), "a": a, "b": b, "r2": r2}


def seasonal_multiplicative(y: list[float], season_len: int) -> dict:
    n = len(y)
    if season_len < 2 or n < season_len:
        raise InputError("Panjang musim minimal 2 dan jumlah data >= panjang musim.")
    overall_avg = float(np.mean(y))
    if overall_avg <= 1e-12:
        raise InputError("Metode musiman multiplikatif membutuhkan rata-rata permintaan bernilai positif (> 0).")
    # Indeks musiman rata-rata per posisi musim (metode rata-rata sederhana ala POM-QM)
    buckets = [[] for _ in range(season_len)]
    for i, val in enumerate(y):
        buckets[i % season_len].append(val)
    raw_idx = [float(np.mean(b)) / overall_avg for b in buckets]
    if any(v <= 1e-12 for v in raw_idx):
        raise InputError("Setiap posisi musim harus memiliki rata-rata permintaan positif (> 0) untuk model multiplikatif.")
    norm_factor = season_len / sum(raw_idx)
    indices = [v * norm_factor for v in raw_idx]

    deseason = [y[i] / indices[i % season_len] for i in range(n)]
    reg = linear_regression(deseason)
    fc = [reg["fc"][i] * indices[i % season_len] for i in range(n)]
    next_f = reg["next"] * indices[n % season_len]
    return {"fc": fc, "next": float(next_f), "indices": indices, "a": reg["a"], "b": reg["b"]}
