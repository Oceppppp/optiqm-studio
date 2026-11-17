"""Test modul Linear Programming (contoh Shader Electronics / Heizer-Render)."""

import pandas as pd
import pytest

from optiqm.core import SheetData, SolverError, get

from conftest import metric, run_template


def test_template_solves_optimal():
    r = run_template("linear_programming")
    # max 50X1 + 40X2 ; 3X1+5X2<=150 ; X1<=20 ; 8X1+5X2<=300  -> X1=30? (cek X1<=20)
    assert metric(r, "X1") == pytest.approx(20, abs=1e-6)
    assert metric(r, "X2") == pytest.approx(18, abs=1e-6)
    assert metric(r, "Nilai Optimal Z") == pytest.approx(1720, abs=1e-6)
    assert any(c.kind == "lp_region" for c in r.charts)


def test_shader_electronics_shadow_price():
    df = pd.DataFrame([["Obj", 7, 5, None, None], ["Elektronik", 4, 3, "<=", 240],
                       ["Perakitan", 2, 1, "<=", 100]], columns=["Name", "X1", "X2", "Sign", "RHS"])
    r = get("linear_programming").solve(SheetData({"objective": "max"}, {"main": df}))
    assert metric(r, "Nilai Optimal Z") == pytest.approx(410)
    sens = next(t for t in r.tables if t.title.startswith("Kendala"))
    assert sens.rows[0][5] == pytest.approx(1.5)
    assert sens.rows[1][5] == pytest.approx(0.5)


def test_minimize_with_ge():
    df = pd.DataFrame([["Obj", 2, 3, None, None], ["A", 1, 1, ">=", 10], ["B", 1, 0, ">=", 4]],
                      columns=["Name", "X1", "X2", "Sign", "RHS"])
    r = get("linear_programming").solve(SheetData({"objective": "min"}, {"main": df}))
    assert metric(r, "Nilai Optimal Z") == pytest.approx(20)


def test_infeasible():
    df = pd.DataFrame([["Obj", 1, 1, None, None], ["A", 1, 1, "<=", 5], ["B", 1, 1, ">=", 10]],
                      columns=["Name", "X1", "X2", "Sign", "RHS"])
    with pytest.raises(SolverError):
        get("linear_programming").solve(SheetData({"objective": "max"}, {"main": df}))
