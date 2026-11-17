"""Algoritma Lot Sizing (L4L, EOQ, POQ, Part-Period Balancing, Wagner-Whitin)."""

from __future__ import annotations

import math

import numpy as np


def eval_schedule(demands: list[float], orders: list[float], S: float, H: float) -> dict:
    inv = 0.0
    ending = []
    setup_cost = 0.0
    hold_cost = 0.0
    for d, q in zip(demands, orders):
        if q > 1e-9:
            setup_cost += S
        inv = inv + q - d
        ending.append(max(0.0, inv))
        hold_cost += max(0.0, inv) * H
    return {"orders": orders, "ending": ending, "setup_cost": setup_cost,
            "hold_cost": hold_cost, "total_cost": setup_cost + hold_cost}


def lot_for_lot(demands: list[float], S: float, H: float) -> dict:
    return eval_schedule(demands, list(demands), S, H)


def fixed_eoq(demands: list[float], S: float, H: float) -> dict:
    avg_d = float(np.mean(demands))
    q_eoq = max(1.0, round(math.sqrt(2.0 * avg_d * S / H))) if avg_d > 0 else 0.0
    orders = []
    inv = 0.0
    for d in demands:
        if inv < d - 1e-9:
            q = q_eoq
            while inv + q < d - 1e-9:
                q += q_eoq
            orders.append(q)
            inv += q - d
        else:
            orders.append(0.0)
            inv -= d
    return eval_schedule(demands, orders, S, H)


def periodic_order_qty(demands: list[float], S: float, H: float) -> dict:
    avg_d = float(np.mean(demands))
    q_eoq = math.sqrt(2.0 * avg_d * S / H) if avg_d > 0 else 1.0
    interval = max(1, round(q_eoq / avg_d)) if avg_d > 0 else 1
    orders = [0.0] * len(demands)
    i = 0
    while i < len(demands):
        if demands[i] > 0:
            orders[i] = sum(demands[i : i + interval])
            i += interval
        else:
            i += 1
    return eval_schedule(demands, orders, S, H)


def part_period_balancing(demands: list[float], S: float, H: float) -> dict:
    epp = S / H if H > 0 else float("inf")
    n = len(demands)
    orders = [0.0] * n
    i = 0
    while i < n:
        if demands[i] <= 0:
            i += 1
            continue
        cum_pp = 0.0
        best_j = i
        prev_diff = epp
        for j in range(i + 1, n):
            cum_pp += demands[j] * (j - i)
            diff = abs(cum_pp - epp)
            if cum_pp >= epp:
                best_j = j if diff < prev_diff else j - 1
                break
            prev_diff = diff
            best_j = j
        orders[i] = sum(demands[i : best_j + 1])
        i = best_j + 1
    return eval_schedule(demands, orders, S, H)


def wagner_whitin(demands: list[float], S: float, H: float) -> dict:
    """Pemrograman dinamis untuk meminimalkan total biaya setup + simpan."""
    n = len(demands)
    dp = [float("inf")] * (n + 1)
    choice = [0] * (n + 1)
    dp[0] = 0.0
    for j in range(1, n + 1):
        for i in range(1, j + 1):
            hold = sum(demands[k - 1] * (k - i) * H for k in range(i, j + 1))
            setup = S if sum(demands[i - 1 : j]) > 0 else 0.0
            cand = dp[i - 1] + setup + hold
            if cand < dp[j] - 1e-9:
                dp[j] = cand
                choice[j] = i - 1
    orders = [0.0] * n
    cur = n
    while cur > 0:
        prev = choice[cur]
        orders[prev] = sum(demands[prev:cur])
        cur = prev
    return eval_schedule(demands, orders, S, H)
