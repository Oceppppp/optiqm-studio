"""Metode transportasi: penyeimbangan, solusi awal (NWC/LC/VAM) dan MODI (bebas I/O)."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np

from optiqm.core import SolverError

TOL = 1e-9
Cell = tuple[int, int]


@dataclass
class TransportProblem:
    cost: np.ndarray            # biaya/keuntungan per unit (m x n), sudah seimbang
    supply: np.ndarray
    demand: np.ndarray
    sources: list[str]
    destinations: list[str]
    maximize: bool = False
    prohibited: np.ndarray | None = None   # mask rute terlarang (m x n)
    dummy_row: bool = False
    dummy_col: bool = False

    @property
    def work_cost(self) -> np.ndarray:
        """Biaya versi minimasi (keuntungan dinegasikan, rute terlarang = Big-M)."""
        w = -self.cost if self.maximize else self.cost.astype(float).copy()
        if self.prohibited is not None and self.prohibited.any():
            big = (np.abs(w[~self.prohibited]).max(initial=1.0) + 1.0) * 1e4
            w = np.where(self.prohibited, big, w)
        return w


@dataclass
class Iteration:
    alloc: np.ndarray
    basis: set[Cell]
    u: np.ndarray
    v: np.ndarray
    index: np.ndarray           # indeks perbaikan c_ij - u_i - v_j (NaN utk sel basis)
    entering: Cell | None = None
    path: list[tuple[Cell, str]] = field(default_factory=list)
    theta: float = 0.0
    leaving: Cell | None = None


def balance(cost: np.ndarray, supply: np.ndarray, demand: np.ndarray, sources: list[str],
            destinations: list[str], prohibited: np.ndarray) -> tuple:
    """Tambahkan sumber/tujuan dummy (biaya 0) bila total supply != total demand."""
    diff = supply.sum() - demand.sum()
    dummy_row = dummy_col = False
    if diff > TOL:
        cost = np.hstack([cost, np.zeros((cost.shape[0], 1))])
        prohibited = np.hstack([prohibited, np.zeros((cost.shape[0], 1), bool)])
        demand = np.append(demand, diff)
        destinations = destinations + ["Dummy"]
        dummy_col = True
    elif diff < -TOL:
        cost = np.vstack([cost, np.zeros((1, cost.shape[1]))])
        prohibited = np.vstack([prohibited, np.zeros((1, cost.shape[1]), bool)])
        supply = np.append(supply, -diff)
        sources = sources + ["Dummy"]
        dummy_row = True
    return cost, supply, demand, sources, destinations, prohibited, dummy_row, dummy_col


# ---------------------------------------------------------------- solusi awal
def initial_solution(p: TransportProblem, method: str) -> tuple[np.ndarray, set[Cell], list[list]]:
    """Kembalikan (alokasi, sel basis, log urutan alokasi)."""
    w = p.work_cost
    m, n = w.shape
    s, d = p.supply.astype(float).copy(), p.demand.astype(float).copy()
    alloc = np.zeros((m, n))
    basis: set[Cell] = set()
    rows, cols = set(range(m)), set(range(n))
    log: list[list] = []
    i = j = 0
    while rows and cols:
        note = ""
        if method == "northwest":
            i, j = min(rows), min(cols)
        elif method == "least_cost":
            i, j = min(((r, c) for r in rows for c in cols),
                       key=lambda rc: (w[rc], -min(s[rc[0]], d[rc[1]]), rc))
        else:  # vogel
            i, j, note = _vogel_pick(w, s, d, rows, cols)
        q = min(s[i], d[j])
        alloc[i, j] = q
        basis.add((i, j))
        s[i] -= q
        d[j] -= q
        log.append([len(log) + 1, p.sources[i], p.destinations[j], p.cost[i, j], q, note])
        row_done, col_done = s[i] <= TOL, d[j] <= TOL
        if row_done and (not col_done or len(rows) > 1):
            rows.discard(i)
        else:
            cols.discard(j)
    _fix_degeneracy(w, basis, m, n)
    return alloc, basis, log


def _vogel_pick(w, s, d, rows, cols) -> tuple[int, int, str]:
    def penalty(vals: list[float]) -> float:
        vals = sorted(vals)
        return vals[1] - vals[0] if len(vals) > 1 else vals[0]

    cands = []
    for r in rows:
        c_best = min(cols, key=lambda c: (w[r, c], c))
        cands.append((penalty([w[r, c] for c in cols]), r, c_best, f"penalti baris {penalty([w[r, c] for c in cols]):g}"))
    for c in cols:
        r_best = min(rows, key=lambda r: (w[r, c], r))
        cands.append((penalty([w[r, c] for r in rows]), r_best, c, f"penalti kolom {penalty([w[r, c] for r in rows]):g}"))
    # penalti terbesar; seri -> biaya sel terkecil -> alokasi terbesar
    best = max(cands, key=lambda t: (round(t[0], 9), -w[t[1], t[2]], min(s[t[1]], d[t[2]])))
    return best[1], best[2], best[3]


def _fix_degeneracy(w: np.ndarray, basis: set[Cell], m: int, n: int) -> int:
    """Tambah sel basis bernilai 0 (termurah, tanpa membentuk siklus) hingga m+n-1 sel."""
    parent = list(range(m + n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, j in basis:
        parent[find(i)] = find(m + j)
    added = 0
    for i, j in sorted(((i, j) for i in range(m) for j in range(n) if (i, j) not in basis),
                       key=lambda c: (w[c], c)):
        if len(basis) >= m + n - 1:
            break
        a, b = find(i), find(m + j)
        if a != b:
            parent[a] = b
            basis.add((i, j))
            added += 1
    return added


# ---------------------------------------------------------------------- MODI
def _potentials(w: np.ndarray, basis: set[Cell]) -> tuple[np.ndarray, np.ndarray]:
    m, n = w.shape
    u, v = np.full(m, np.nan), np.full(n, np.nan)
    u[0] = 0.0
    changed = True
    while changed:
        changed = False
        for i, j in basis:
            if not np.isnan(u[i]) and np.isnan(v[j]):
                v[j] = w[i, j] - u[i]; changed = True
            elif np.isnan(u[i]) and not np.isnan(v[j]):
                u[i] = w[i, j] - v[j]; changed = True
    if np.isnan(u).any() or np.isnan(v).any():
        raise SolverError("Gagal menghitung potensial MODI (basis tidak terhubung).")
    return u, v


def _cycle(basis: set[Cell], enter: Cell) -> list[tuple[Cell, str]]:
    """Lintasan stepping-stone tertutup untuk sel masuk (tanda + / -)."""
    adj: dict[tuple[str, int], list[tuple[str, int]]] = {}
    for i, j in basis:
        adj.setdefault(("r", i), []).append(("c", j))
        adj.setdefault(("c", j), []).append(("r", i))
    start, goal = ("c", enter[1]), ("r", enter[0])
    prev = {start: None}
    q = deque([start])
    while q:
        node = q.popleft()
        if node == goal:
            break
        for nb in adj.get(node, []):
            if nb not in prev:
                prev[nb] = node
                q.append(nb)
    if goal not in prev:
        raise SolverError("Lintasan stepping-stone tidak ditemukan.")
    nodes = [goal]
    while prev[nodes[-1]] is not None:
        nodes.append(prev[nodes[-1]])
    nodes.reverse()                                  # c_j ... r_i
    cells = []
    for a, b in zip(nodes, nodes[1:]):
        r, c = (a[1], b[1]) if a[0] == "r" else (b[1], a[1])
        cells.append((r, c))
    path = [(enter, "+")]
    path += [(cell, "-" if k % 2 == 0 else "+") for k, cell in enumerate(cells)]
    return path


def modi(p: TransportProblem, alloc: np.ndarray, basis: set[Cell], max_iter: int = 200) -> list[Iteration]:
    w = p.work_cost
    alloc, basis = alloc.copy(), set(basis)
    its: list[Iteration] = []
    for _ in range(max_iter):
        u, v = _potentials(w, basis)
        idx = w - u[:, None] - v[None, :]
        for c in basis:
            idx[c] = np.nan
        it = Iteration(alloc.copy(), set(basis), u, v, idx)
        its.append(it)
        masked = np.where(np.isnan(idx), np.inf, idx)
        if masked.min() >= -1e-9:
            return its
        enter = tuple(int(x) for x in np.unravel_index(np.argmin(masked), masked.shape))
        path = _cycle(basis, enter)
        minus = [c for c, sg in path if sg == "-"]
        theta = min(alloc[c] for c in minus)
        leaving = min((c for c in minus if abs(alloc[c] - theta) <= TOL), key=lambda c: (-w[c], c))
        for c, sg in path:
            alloc[c] += theta if sg == "+" else -theta
        alloc[np.abs(alloc) < TOL] = 0.0
        basis.add(enter)
        basis.discard(leaving)
        it.entering, it.path, it.theta, it.leaving = enter, path, theta, leaving
    raise SolverError("MODI tidak konvergen dalam batas iterasi.")


def total(p: TransportProblem, alloc: np.ndarray) -> float:
    return float((p.cost * alloc).sum())
