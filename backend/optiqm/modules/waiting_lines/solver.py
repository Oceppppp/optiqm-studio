"""Formula antrian: M/M/1, M/M/s, M/D/1, dan M/M/1 Populasi Terbatas."""

from __future__ import annotations

import math

from optiqm.core import InputError


def mm1(lam: float, mu: float) -> dict:
    if lam >= mu:
        raise InputError("Sistem M/M/1 tidak stabil (λ harus lebih kecil daripada μ).")
    rho = lam / mu
    p0 = 1.0 - rho
    lq = (lam ** 2) / (mu * (mu - lam))
    l = lam / (mu - lam)
    wq = lq / lam
    w = l / lam
    pn = [(1.0 - rho) * (rho ** n) for n in range(11)]
    return {"rho": rho, "p0": p0, "pw": rho, "lq": lq, "l": l, "wq": wq, "w": w, "pn": pn}


def mms(lam: float, mu: float, s: int) -> dict:
    if s < 1:
        raise InputError("Jumlah server s minimal 1.")
    if lam >= s * mu:
        raise InputError("Sistem M/M/s tidak stabil (λ harus < s·μ).")
    a = lam / mu
    rho = a / s
    sum_terms = sum((a ** n) / math.factorial(n) for n in range(s))
    last_term = ((a ** s) / math.factorial(s)) * (1.0 / (1.0 - rho))
    p0 = 1.0 / (sum_terms + last_term)
    lq = (p0 * (a ** s) * rho) / (math.factorial(s) * ((1.0 - rho) ** 2))
    l = lq + a
    wq = lq / lam
    w = wq + 1.0 / mu
    pw = last_term * p0
    pn = [((a ** n) / math.factorial(n) * p0) if n < s else ((a ** n) / (math.factorial(s) * (s ** (n - s))) * p0)
          for n in range(11)]
    return {"rho": rho, "p0": p0, "pw": pw, "lq": lq, "l": l, "wq": wq, "w": w, "pn": pn}


def md1(lam: float, mu: float) -> dict:
    if lam >= mu:
        raise InputError("Sistem M/D/1 tidak stabil (λ harus < μ).")
    rho = lam / mu
    lq = (lam ** 2) / (2.0 * mu * (mu - lam))
    wq = lq / lam
    w = wq + 1.0 / mu
    l = lam * w
    return {"rho": rho, "p0": 1.0 - rho, "pw": rho, "lq": lq, "l": l, "wq": wq, "w": w, "pn": []}


def mm1_finite(lam: float, mu: float, N: int) -> dict:
    """M/M/1/K/K (Finite population N, 1 server). lam = laju kedatangan per individu."""
    if N < 1:
        raise InputError("Ukuran populasi N minimal 1.")
    ratio = lam / mu
    terms = [math.factorial(N) / math.factorial(N - n) * (ratio ** n) for n in range(N + 1)]
    p0 = 1.0 / sum(terms)
    pn = [t * p0 for t in terms]
    l = sum(n * pn[n] for n in range(N + 1))
    eff_lam = lam * (N - l)
    lq = l - (1.0 - p0)
    w = l / eff_lam if eff_lam > 0 else 0.0
    wq = lq / eff_lam if eff_lam > 0 else 0.0
    return {"rho": 1.0 - p0, "p0": p0, "pw": 1.0 - p0, "lq": lq, "l": l, "wq": wq, "w": w,
            "pn": pn[:11], "eff_lam": eff_lam}
