"""Integer & Mixed-Integer Linear Programming (MILP) menggunakan SciPy HiGHS."""

from __future__ import annotations

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

from optiqm.core import InputError, SolverError
from optiqm.modules.linear_programming.solver import LPProblem


def solve_milp(p: LPProblem, var_types: list[str]) -> tuple[np.ndarray, float, np.ndarray]:
    """Selesaikan MILP. ``var_types`` berisi 'int', 'bin', atau 'real' per variabel."""
    n = len(p.c)
    integrality = np.zeros(n, dtype=int)
    lb = np.zeros(n, dtype=float)
    ub = np.full(n, np.inf, dtype=float)
    for j, vt in enumerate(var_types):
        t = vt.strip().lower()
        if t in {"int", "integer", "bulat"}:
            integrality[j] = 1
        elif t in {"bin", "binary", "0-1", "biner"}:
            integrality[j] = 1
            ub[j] = 1.0
        elif t in {"real", "cont", "continuous", "kontinu"}:
            integrality[j] = 0
        else:
            raise InputError(f"Tipe variabel '{vt}' tidak valid (gunakan: int, bin, atau real).")

    constraints = []
    for i, sg in enumerate(p.signs):
        row = p.A[i : i + 1]
        rhs = float(p.b[i])
        if sg == "<=":
            constraints.append(LinearConstraint(row, -np.inf, rhs))
        elif sg == ">=":
            constraints.append(LinearConstraint(row, rhs, np.inf))
        else:
            constraints.append(LinearConstraint(row, rhs, rhs))

    sense = -1.0 if p.maximize else 1.0
    res = milp(c=sense * p.c, integrality=integrality, bounds=Bounds(lb, ub), constraints=constraints)
    if res.status == 2:
        raise SolverError("Masalah Integer Programming infeasible.")
    if res.status == 3:
        raise SolverError("Masalah Integer Programming unbounded.")
    if not res.success:
        raise SolverError(f"MILP solver gagal: {res.message}")

    x = res.x
    slack = np.abs(p.b - p.A @ x)
    return x, float(p.c @ x), slack
