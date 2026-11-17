"""Preemptive (lexicographic) Goal Programming dengan LP sekuensial."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import linprog

from optiqm.core import SolverError


@dataclass
class GoalRow:
    name: str
    coeffs: np.ndarray
    target: float
    priority: int        # 0 = kendala keras (hard constraint); 1,2,... = prioritas tujuan
    w_minus: float       # penalti kekurangan (d-)
    w_plus: float        # penalti kelebihan (d+)
    sign: str            # "=" (biasa), "<=", ">=" untuk hard constraint


def solve_goal_programming(variables: list[str], rows: list[GoalRow]) -> dict:
    n = len(variables)
    goals = [r for r in rows if r.priority > 0]
    hard = [r for r in rows if r.priority == 0]
    m = len(goals)
    # Variabel: [x_0..x_{n-1}, d-_0..d-_{m-1}, d+_0..d+_{m-1}]
    total_vars = n + 2 * m

    A_eq, b_eq, A_ub, b_ub = [], [], [], []
    for h in hard:
        pad = np.zeros(2 * m)
        row = np.concatenate([h.coeffs, pad])
        if h.sign == "<=":
            A_ub.append(row); b_ub.append(h.target)
        elif h.sign == ">=":
            A_ub.append(-row); b_ub.append(-h.target)
        else:
            A_eq.append(row); b_eq.append(h.target)

    for k, g in enumerate(goals):
        # sum(a_j x_j) + d-_k - d+_k = target
        row = np.zeros(total_vars)
        row[:n] = g.coeffs
        row[n + k] = 1.0
        row[n + m + k] = -1.0
        A_eq.append(row); b_eq.append(g.target)

    priorities = sorted({g.priority for g in goals})
    achieved_steps = []
    res = None
    for pr in priorities:
        c = np.zeros(total_vars)
        for k, g in enumerate(goals):
            if g.priority == pr:
                c[n + k] = g.w_minus
                c[n + m + k] = g.w_plus
        res = linprog(
            c,
            A_ub=np.array(A_ub) if A_ub else None, b_ub=np.array(b_ub) if b_ub else None,
            A_eq=np.array(A_eq) if A_eq else None, b_eq=np.array(b_eq) if b_eq else None,
            bounds=[(0, None)] * total_vars, method="highs",
        )
        if not res.success:
            raise SolverError(f"Goal Programming gagal pada Prioritas {pr}: {res.message}")
        # Kunci pencapaian deviasi prioritas saat ini untuk level berikutnya
        A_ub.append(c); b_ub.append(float(res.fun) + 1e-7)
        achieved_steps.append((pr, float(res.fun)))

    x = res.x[:n] if res is not None else np.zeros(n)
    d_minus = res.x[n : n + m] if res is not None else np.zeros(m)
    d_plus = res.x[n + m :] if res is not None else np.zeros(m)
    return {"x": x, "d_minus": d_minus, "d_plus": d_plus, "goals": goals, "steps": achieved_steps}
