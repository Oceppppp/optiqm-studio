"""Test modul Integer Programming."""

import pandas as pd
import pytest

from optiqm.core import SheetData, get

from conftest import metric, run_template


def test_template_mixed_or_integer():
    r = run_template("integer_programming")
    # 8000*4 + 4000*2 = 40000? wait: 15*4 + 30*2 = 120 <= 200 -> Z = 700
    # 8000*2 + 4000*5 = 36000 <= 40000; 15*2 + 30*5 = 180 <= 200 -> Z = 950!
    # Check 8000*1 + 4000*6 = 32000; 15 + 180 = 195 -> Z = 100+900 = 1000!
    # Check 0, 6 -> 24000, 180 -> Z = 900. So X1=1, X2=6 -> Z=1000!
    assert metric(r, "Nilai Optimal Z (Integer)") == pytest.approx(1000)
    assert metric(r, "X1") == pytest.approx(1)
    assert metric(r, "X2") == pytest.approx(6)


def test_binary_knapsack():
    df = pd.DataFrame(
        [["Obj", 60, 100, 120, None, None],
         ["Type", "bin", "bin", "bin", None, None],
         ["Berat", 10, 20, 30, "<=", 50]],
        columns=["Name", "X1", "X2", "X3", "Sign", "RHS"],
    )
    r = get("integer_programming").solve(SheetData({"objective": "max"}, {"main": df}))
    assert metric(r, "Nilai Optimal Z (Integer)") == pytest.approx(220)
