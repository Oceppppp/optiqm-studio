"""Test Break-Even, Cost-Volume, Game Theory, Markov, dan Simulation."""

import pytest

from conftest import metric, run_template


def test_breakeven_and_cost_volume():
    rb = run_template("breakeven")
    # 10000 / (20 - 8) = 833.333
    assert metric(rb, "BEP (Unit)") == pytest.approx(10000 / 12, rel=1e-4)

    rc = run_template("cost_volume")
    # Pada V=2500: Manual=20k+35k=55k; Semi=50k+15k=65k; Otomatis=90k+5k=95k -> Manual!
    assert metric(rc, "Terbaik pada Volume 2500") == "Mesin Manual"


def test_game_theory():
    r = run_template("game_theory")
    assert metric(r, "Nilai Permainan (Value of Game)") == pytest.approx(1.0)


def test_markov_and_simulation():
    rm = run_template("markov_analysis")
    assert metric(rm, "Steady State (Toko A)") == "75.00%"
    assert metric(rm, "Steady State (Toko B)") == "25.00%"

    rs = run_template("simulation")
    assert metric(rs, "Nilai Harapan Teoritis") == pytest.approx(2.95)
