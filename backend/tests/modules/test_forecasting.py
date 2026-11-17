"""Test modul Forecasting dengan 8 metode (Heizer & Render)."""

import pandas as pd
import pytest

from optiqm.core import SheetData, get

from conftest import metric, run_template


def test_template_exp_smoothing():
    r = run_template("forecasting")
    assert metric(r, "MAD") > 0
    assert any(c.kind == "line" for c in r.charts)


def test_moving_average_heizer_render():
    df = pd.DataFrame(
        [["Jan", 10], ["Feb", 12], ["Mar", 13], ["Apr", 16], ["May", 19], ["Jun", 23], ["Jul", 26]],
        columns=["Period", "Demand"],
    )
    r = get("forecasting").solve(SheetData({"method": "moving_average", "periods": 3}, {"main": df}))
    # (19+23+26)/3 = 22.666667
    assert metric(r, "Ramalan Periode Berikutnya") == pytest.approx(68 / 3, rel=1e-5)


def test_linear_regression_and_causal():
    df = pd.DataFrame([[1, 10, 74], [2, 20, 79], [3, 30, 84], [4, 40, 89]], columns=["Period", "X", "Demand"])
    r = get("forecasting").solve(SheetData({"method": "linear_regression"}, {"main": df}))
    assert metric(r, "Ramalan Periode Berikutnya") == pytest.approx(94)
    assert metric(r, "MAD") == pytest.approx(0, abs=1e-6)

    rc = get("forecasting").solve(SheetData({"method": "causal_regression", "x_next": 50}, {"main": df}))
    assert metric(rc, "Ramalan Periode Berikutnya") == pytest.approx(94)


@pytest.mark.parametrize("method", [
    "naive", "weighted_moving_average", "trend_adjusted_exponential_smoothing", "seasonal"
])
def test_other_methods_run(method):
    df = pd.DataFrame([[f"P{i}", 100 + (i % 4) * 20 + i * 2] for i in range(1, 13)], columns=["Period", "Demand"])
    r = get("forecasting").solve(SheetData({"method": method, "season_length": 4}, {"main": df}))
    assert metric(r, "Ramalan Periode Berikutnya") > 0
