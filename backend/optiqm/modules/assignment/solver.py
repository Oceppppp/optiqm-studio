"""Algoritma Hungarian untuk Assignment Problem (dengan langkah reduksi)."""

from __future__ import annotations

import numpy as np
from scipy.optimize import linear_sum_assignment


def hungarian_solve(cost: np.ndarray, maximize: bool = False) -> tuple[np.ndarray, list[tuple[str, np.ndarray]]]:
    """Kembalikan array penugasan (row_idx, col_idx) dan langkah reduksi matriks."""
    m, n = cost.shape
    size = max(m, n)
    padded = np.zeros((size, size), dtype=float)
    padded[:m, :n] = cost
    work = padded.max() - padded if maximize else padded.copy()

    steps: list[tuple[str, np.ndarray]] = []
    if maximize:
        steps.append(("Konversi ke Matriks Minimasi (Opportunity Loss)", work.copy()))

    row_min = work.min(axis=1, keepdims=True)
    r_red = work - row_min
    steps.append(("Setelah Reduksi Baris", r_red.copy()))

    col_min = r_red.min(axis=0, keepdims=True)
    c_red = r_red - col_min
    steps.append(("Setelah Reduksi Kolom", c_red.copy()))

    row_ind, col_ind = linear_sum_assignment(work)
    return np.column_stack([row_ind, col_ind]), steps
