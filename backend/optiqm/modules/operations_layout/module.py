"""Modul Operations Layout (Process Layout — minimasi Load × Distance)."""

from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

from optiqm.core import BaseModule, InputError, ModuleResult, SheetData, register
from optiqm.core.parsing import clean_frame, require_rows, to_float


def _total_cost(perm: list[int], flows: np.ndarray, dist: np.ndarray) -> float:
    n = len(perm)
    cost = 0.0
    for i in range(n):
        for j in range(n):
            if i != j:
                cost += flows[i, j] * dist[perm[i], perm[j]]
    return float(cost)


@register
class OperationsLayout(BaseModule):
    key = "operations_layout"
    name = "Operations Layout (Process Layout)"
    category = "Lokasi & Tata Letak"
    description = "Mengatur penempatan departemen ke ruangan untuk meminimalkan total biaya perpindahan (Load × Distance)."
    sheet_prefixes = ("LAYOUT",)
    table_hint = ("Dua blok tabel: [main] (atau [flows]) matriks aliran antar-departemen, dan "
                  "[distances] matriks jarak antar-ruangan.")

    def template(self) -> SheetData:
        flows = pd.DataFrame(
            [["Assembly", 0, 50, 100, 0, 0, 20],
             ["Painting", 0, 0, 30, 50, 10, 0],
             ["Machine", 0, 0, 0, 20, 0, 0],
             ["Receiving", 0, 0, 0, 0, 30, 0],
             ["Shipping", 0, 0, 0, 0, 0, 0],
             ["Testing", 0, 0, 0, 0, 0, 0]],
            columns=["Dept", "Assembly", "Painting", "Machine", "Receiving", "Shipping", "Testing"],
        )
        dist = pd.DataFrame(
            [["Room 1", 0, 20, 40, 20, 40, 60],
             ["Room 2", 20, 0, 20, 40, 20, 40],
             ["Room 3", 40, 20, 0, 60, 40, 20],
             ["Room 4", 20, 40, 60, 0, 20, 40],
             ["Room 5", 40, 20, 40, 20, 0, 20],
             ["Room 6", 60, 40, 20, 40, 20, 0]],
            columns=["Room", "Room 1", "Room 2", "Room 3", "Room 4", "Room 5", "Room 6"],
        )
        return SheetData(tables={"main": flows, "distances": dist})

    def solve(self, data: SheetData) -> ModuleResult:
        f_df = clean_frame(data.table("flows", required=False) if "flows" in data.tables else data.table("main"))
        d_df = clean_frame(data.table("distances"))
        require_rows(f_df, 2, "Matriks aliran [flows]")
        require_rows(d_df, 2, "Matriks jarak [distances]")
        depts = [str(x).strip() for x in f_df.iloc[:, 0]]
        rooms = [str(x).strip() for x in d_df.iloc[:, 0]]
        n = len(depts)
        if len(rooms) != n or len(f_df.columns) - 1 != n or len(d_df.columns) - 1 != n:
            raise InputError("Matriks aliran dan matriks jarak harus persegi dengan ukuran yang sama.")

        F = np.array([[to_float(f_df.iloc[i, j + 1]) for j in range(n)] for i in range(n)], dtype=float)
        F_sym = F + F.T - np.diag(np.diag(F)) if not np.allclose(F, F.T) else F
        D = np.array([[to_float(d_df.iloc[i, j + 1]) for j in range(n)] for i in range(n)], dtype=float)

        init_perm = list(range(n))
        init_cost = _total_cost(init_perm, F_sym, D)

        if n <= 7:
            best_perm = list(min(itertools.permutations(range(n)), key=lambda p: _total_cost(list(p), F_sym, D)))
            best_cost = _total_cost(best_perm, F_sym, D)
        else:
            best_perm = list(init_perm)
            best_cost = init_cost
            improved = True
            while improved:
                improved = False
                for i in range(n):
                    for j in range(i + 1, n):
                        cand = list(best_perm)
                        cand[i], cand[j] = cand[j], cand[i]
                        c = _total_cost(cand, F_sym, D)
                        if c < best_cost - 1e-9:
                            best_perm, best_cost, improved = cand, c, True

        r = ModuleResult()
        r.metric("Total Biaya Load×Distance Optimal", best_cost, highlight=True)
        r.metric("Biaya Penempatan Awal", init_cost)
        r.metric("Penghematan", max(0.0, init_cost - best_cost))
        r.table("Penempatan Departemen Optimal", ["Departemen", "Ruangan Awal", "Ruangan Optimal"],
                [[depts[i], rooms[i], rooms[best_perm[i]]] for i in range(n)])
        r.interpretation = (f"Layout optimal: " + ", ".join(f"{depts[i]}→{rooms[best_perm[i]]}" for i in range(n))
                            + f" (total biaya {best_cost:,.2f}).")
        return r
