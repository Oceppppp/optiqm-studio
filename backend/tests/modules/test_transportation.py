"""Test modul Transportation (soal Sunray/Heizer-Render, degenerasi, dummy, max)."""

import pandas as pd
import pytest

from optiqm.core import SheetData, get

from conftest import metric, run_template


def test_template_optimal_cost():
    r = run_template("transportation")
    # 5*100? Cek optimal: A->G1(100)=500? wait:
    # A:5,4,3 sup 100 -> A->G1 100 (500) atau A->G3 100 (300)
    # Optimal: A->G1 100 (500)? No: C->G1 200 (1800)? wait: A->G1:100(500), B->G2:200(800)+G1:100(800), C->G1:100(900)+G3:200(1000) = 4000
    # Better: A->G1:100(500), B->G1:200(1600)+G2:100(400), C->G2:100(700)+G3:200(1000) = 4200;
    # Wait: A->G1:100(500), B->G2:200(800)+G3:100(300), C->G1:200(1800)+G3:100(500) = 3900!
    assert metric(r, "Total Biaya Optimal") == pytest.approx(3900)


@pytest.mark.parametrize("method", ["northwest", "least_cost", "vogel"])
def test_all_initial_methods_reach_same_optimum(method):
    df = pd.DataFrame(
        [["Des Moines", 5, 4, 3, 100],
         ["Evansville", 8, 4, 3, 300],
         ["Fort Lauderdale", 9, 7, 5, 300],
         ["Demand", 300, 200, 200, None]],
        columns=["Source", "Albuquerque", "Boston", "Cleveland", "Supply"],
    )
    r = get("transportation").solve(SheetData({"objective": "min", "initial_method": method}, {"main": df}))
    assert metric(r, "Total Biaya Optimal") == pytest.approx(3900)


def test_unbalanced_adds_dummy_warning():
    df = pd.DataFrame(
        [["S1", 10, 20, 50], ["S2", 15, 12, 80], ["Demand", 60, 40, None]],
        columns=["Source", "D1", "D2", "Supply"],
    )
    r = get("transportation").solve(SheetData({"objective": "min"}, {"main": df}))
    assert r.warnings
    assert metric(r, "Total Biaya Optimal") == pytest.approx(10 * 50 + 15 * 10 + 12 * 40)


def test_maximize_profit():
    df = pd.DataFrame(
        [["P1", 10, 12, 50], ["P2", 8, 15, 50], ["Demand", 50, 50, None]],
        columns=["Source", "D1", "D2", "Supply"],
    )
    r = get("transportation").solve(SheetData({"objective": "max"}, {"main": df}))
    assert metric(r, "Total Keuntungan Optimal") == pytest.approx(10 * 50 + 15 * 50)
