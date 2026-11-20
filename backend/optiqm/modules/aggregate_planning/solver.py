"""Solver Aggregate Planning: Chase, Level, dan Optimal (LP)."""

from __future__ import annotations

import numpy as np
from scipy.optimize import linprog

from optiqm.core import SolverError


def solve_aggregate(
    periods: list[str], demand: np.ndarray, reg_cap: np.ndarray, ot_cap: np.ndarray, sub_cap: np.ndarray,
    costs: dict[str, float], init_inv: float, init_prod: float, strategy: str, allow_backorder: bool,
) -> dict:
    T = len(periods)
    if strategy in {"chase", "level"}:
        return _heuristic(periods, demand, reg_cap, ot_cap, sub_cap, costs, init_inv, init_prod, strategy)

    total_cap = float(reg_cap.sum() + ot_cap.sum() + sub_cap.sum() + init_inv)
    total_dem = float(demand.sum())
    if total_cap < total_dem - 1e-6:
        raise SolverError(
            f"Total kapasitas tersedia ({total_cap:,.2f}) lebih kecil dari total permintaan ({total_dem:,.2f}); "
            "permintaan horizon tidak mungkin terpenuhi seluruhnya."
        )

    # LP Optimal: variabel per periode t = [R_t, O_t, S_t, I+_t, I-_t, H_t, L_t] -> 7*T variabel
    # (H_t = hire / kenaikan produksi, L_t = layoff / penurunan produksi)
    k = 7
    c = np.zeros(k * T)
    lb = np.zeros(k * T)
    ub = np.full(k * T, np.inf)
    for t in range(T):
        b = t * k
        c[b + 0] = costs["regular"]
        c[b + 1] = costs["overtime"]
        c[b + 2] = costs["subcontract"]
        c[b + 3] = costs["holding"]
        c[b + 4] = costs["backorder"]
        c[b + 5] = costs["hire"]
        c[b + 6] = costs["layoff"]
        ub[b + 0] = reg_cap[t]
        ub[b + 1] = ot_cap[t]
        ub[b + 2] = sub_cap[t]
        if not allow_backorder or t == T - 1:
            # Backorder pada akhir horizon wajib 0 agar seluruh permintaan benar-benar terpenuhi
            ub[b + 4] = 0.0

    A_eq, b_eq = [], []
    for t in range(T):
        # Keseimbangan persediaan: I_{t-1} - B_{t-1} + R_t + O_t + S_t - I_t + B_t = D_t
        row = np.zeros(k * T)
        if t > 0:
            row[(t - 1) * k + 3] = 1.0
            row[(t - 1) * k + 4] = -1.0
        row[t * k + 0] = 1.0
        row[t * k + 1] = 1.0
        row[t * k + 2] = 1.0
        row[t * k + 3] = -1.0
        row[t * k + 4] = 1.0
        rhs = demand[t] - (init_inv if t == 0 else 0.0)
        A_eq.append(row); b_eq.append(rhs)

        # Perubahan tingkat produksi reguler: R_t - R_{t-1} - H_t + L_t = 0
        row2 = np.zeros(k * T)
        row2[t * k + 0] = 1.0
        if t > 0:
            row2[(t - 1) * k + 0] = -1.0
        row2[t * k + 5] = -1.0
        row2[t * k + 6] = 1.0
        A_eq.append(row2); b_eq.append(init_prod if t == 0 else 0.0)

    res = linprog(c, A_eq=np.array(A_eq), b_eq=np.array(b_eq), bounds=list(zip(lb, ub)), method="highs")
    if not res.success:
        raise SolverError(f"Aggregate Planning tidak layak (kapasitas kurang?): {res.message}")

    x = res.x.reshape(T, k)
    return _pack_plan(periods, demand, x[:, 0], x[:, 1], x[:, 2], x[:, 3], x[:, 4], x[:, 5], x[:, 6], costs)


def _heuristic(periods, demand, reg_cap, ot_cap, sub_cap, costs, init_inv, init_prod, strategy):
    T = len(periods)
    R, O, S, I, B, H, L = [np.zeros(T) for _ in range(7)]
    inv = init_inv
    prev_r = init_prod
    avg_need = max(0.0, (demand.sum() - init_inv) / T)
    for t in range(T):
        need = max(0.0, demand[t] - inv) if strategy == "chase" else avg_need
        r_t = min(need, reg_cap[t])
        rem = max(0.0, demand[t] - inv - r_t)
        o_t = min(rem, ot_cap[t])
        rem = max(0.0, rem - o_t)
        s_t = min(rem, sub_cap[t])
        end_bal = inv + r_t + o_t + s_t - demand[t]
        R[t], O[t], S[t] = r_t, o_t, s_t
        I[t], B[t] = max(0.0, end_bal), max(0.0, -end_bal)
        H[t], L[t] = max(0.0, r_t - prev_r), max(0.0, prev_r - r_t)
        inv, prev_r = end_bal, r_t
    return _pack_plan(periods, demand, R, O, S, I, B, H, L, costs)


def _pack_plan(periods, demand, R, O, S, I, B, H, L, costs):
    rows = []
    tot = {"regular": 0.0, "overtime": 0.0, "subcontract": 0.0, "holding": 0.0, "backorder": 0.0, "hire_layoff": 0.0}
    for t, per in enumerate(periods):
        c_reg = R[t] * costs["regular"]
        c_ot = O[t] * costs["overtime"]
        c_sub = S[t] * costs["subcontract"]
        c_hold = I[t] * costs["holding"]
        c_bo = B[t] * costs["backorder"]
        c_hl = H[t] * costs["hire"] + L[t] * costs["layoff"]
        tot["regular"] += c_reg; tot["overtime"] += c_ot; tot["subcontract"] += c_sub
        tot["holding"] += c_hold; tot["backorder"] += c_bo; tot["hire_layoff"] += c_hl
        rows.append([per, demand[t], R[t], O[t], S[t], I[t], B[t], H[t], L[t],
                     c_reg + c_ot + c_sub + c_hold + c_bo + c_hl])
    return {"rows": rows, "totals": tot, "total_cost": sum(tot.values()),
            "periods": periods, "demand": demand.tolist(),
            "prod": (R + O + S).tolist(), "inv": I.tolist()}
