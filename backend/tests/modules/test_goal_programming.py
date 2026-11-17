"""Test modul Goal Programming."""

import pytest

from conftest import metric, run_template


def test_goal_programming_template():
    r = run_template("goal_programming")
    # 6X1 + 5X2 <= 30, X1 >= 4 -> X1=4, X2=1.2 => profit = 28+7.2 = 35.2 >= 30; lembur = 8+3.6 = 11.6 <= 12
    assert metric(r, "X1") >= 4 - 1e-6
    assert metric(r, "Prioritas Tercapai Penuh") == "3 / 3"
