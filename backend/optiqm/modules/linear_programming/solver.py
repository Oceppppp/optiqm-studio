"""Linear Programming: solver numerik + analisis sensitivitas (bebas I/O)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import linprog

from optiqm.core import InputError, SolverError

SIGNS = {"<=": "<=", "≤": "<=", "=<": "<=", ">=": ">=", "≥": ">=", "=>": ">=", "=": "=", "==": "="}


@dataclass
class LPProblem:
    variables: list[str]
    c: np.ndarray                 # koefisien fungsi tujuan
    A: np.ndarray                 # koefisien kendala (m x n)
    signs: list[str]              # "<=", ">=", "="
    b: np.ndarray                 # RHS
    constraint_names: list[str]
    maximize: bool


@dataclass
class LPSolution:
    x: np.ndarray
    objective: float
    slack: np.ndarray             # slack/surplus per kendala (>= 0)
    shadow_prices: np.ndarray     # dual value per kendala
    reduced_costs: np.ndarray
    iterations: int


def normalize_sign(sign: object, row: str) -> str:
    s = str(sign).strip()
    if s not in SIGNS:
        raise InputError(f"Tanda kendala '{sign}' pada '{row}' tidak dikenal (gunakan <=, >=, atau =).")
    return SIGNS[s]


def solve_lp(p: LPProblem) -> LPSolution:
    sense = -1.0 if p.maximize else 1.0
    A_ub, b_ub, A_eq, b_eq, ub_idx, eq_idx = [], [], [], [], [], []
    for i, s in enumerate(p.signs):
        if s == "<=":
            A_ub.append(p.A[i]); b_ub.append(p.b[i]); ub_idx.append((i, 1.0))
        elif s == ">=":
            A_ub.append(-p.A[i]); b_ub.append(-p.b[i]); ub_idx.append((i, -1.0))
        else:
            A_eq.append(p.A[i]); b_eq.append(p.b[i]); eq_idx.append(i)

    res = linprog(
        sense * p.c,
        A_ub=np.array(A_ub) if A_ub else None, b_ub=np.array(b_ub) if b_ub else None,
        A_eq=np.array(A_eq) if A_eq else None, b_eq=np.array(b_eq) if b_eq else None,
        bounds=[(0, None)] * len(p.c), method="highs",
    )
    if res.status == 2:
        raise SolverError("Masalah tidak memiliki solusi layak (infeasible).")
    if res.status == 3:
        raise SolverError("Masalah tidak terbatas (unbounded) — fungsi tujuan bisa tak hingga.")
    if not res.success:
        raise SolverError(f"Solver gagal: {res.message}")

    m = len(p.signs)
    shadow = np.zeros(m)
    if ub_idx and res.ineqlin is not None:
        for (i, flip), mg in zip(ub_idx, res.ineqlin.marginals):
            shadow[i] = sense * flip * mg
    if eq_idx and res.eqlin is not None:
        for i, mg in zip(eq_idx, res.eqlin.marginals):
            shadow[i] = sense * mg
    lhs = p.A @ res.x
    slack = np.abs(p.b - lhs)
    reduced = sense * np.asarray(res.lower.marginals) if res.lower is not None else np.zeros(len(p.c))
    return LPSolution(
        x=res.x, objective=float(p.c @ res.x), slack=slack,
        shadow_prices=shadow, reduced_costs=reduced, iterations=int(getattr(res, "nit", 0)),
    )


def feasible_region(p: LPProblem, x_opt: np.ndarray | None) -> dict:
    """Data grafik metode grafik untuk LP 2 variabel."""
    A, b = p.A, p.b
    # kumpulkan semua garis: kendala + sumbu x1=0, x2=0
    lines = [(A[i], b[i]) for i in range(len(b))] + [(np.array([1.0, 0.0]), 0.0), (np.array([0.0, 1.0]), 0.0)]
    pts = []
    for i in range(len(lines)):
        for j in range(i + 1, len(lines)):
            M = np.vstack([lines[i][0], lines[j][0]])
            if abs(np.linalg.det(M)) < 1e-12:
                continue
            pt = np.linalg.solve(M, [lines[i][1], lines[j][1]])
            if _feasible(p, pt):
                pts.append(pt)
    polygon: list[list[float]] = []
    if pts:
        P = np.unique(np.round(np.array(pts), 9), axis=0)
        center = P.mean(axis=0)
        order = np.argsort(np.arctan2(P[:, 1] - center[1], P[:, 0] - center[0]))
        polygon = P[order].tolist()

    xmax = max([pt[0] for pt in polygon] + [1.0]) * 1.4
    ymax = max([pt[1] for pt in polygon] + [1.0]) * 1.4
    drawn = []
    for i, name in enumerate(p.constraint_names):
        a1, a2 = A[i]
        if abs(a2) > 1e-12:
            seg = [[0.0, b[i] / a2], [xmax, (b[i] - a1 * xmax) / a2]]
        elif abs(a1) > 1e-12:
            seg = [[b[i] / a1, 0.0], [b[i] / a1, ymax]]
        else:
            continue
        drawn.append({"name": f"{name}: {a1:g}{p.variables[0]} + {a2:g}{p.variables[1]} {p.signs[i]} {b[i]:g}",
                      "points": seg})
    return {
        "lines": drawn, "polygon": polygon,
        "optimum": x_opt.tolist() if x_opt is not None else None,
        "x_label": p.variables[0], "y_label": p.variables[1],
        "x_max": xmax, "y_max": ymax,
    }


def corner_points(p: LPProblem, polygon: list[list[float]]) -> list[list[float]]:
    return [[pt[0], pt[1], float(p.c @ np.array(pt))] for pt in polygon]


def _feasible(p: LPProblem, pt: np.ndarray, tol: float = 1e-7) -> bool:
    if (pt < -tol).any():
        return False
    lhs = p.A @ pt
    for v, s, rhs in zip(lhs, p.signs, p.b):
        if s == "<=" and v > rhs + tol:
            return False
        if s == ">=" and v < rhs - tol:
            return False
        if s == "=" and abs(v - rhs) > tol:
            return False
    return True
