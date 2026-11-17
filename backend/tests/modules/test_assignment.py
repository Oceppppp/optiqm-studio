"""Test modul Assignment (contoh Heizer & Render, unbalanced, maximize)."""

import pandas as pd
import pytest

from optiqm.core import SheetData, get

from conftest import metric, run_template


def test_template_fix_it_shop():
    r = run_template("assignment")
    # Adams->P3 (6), Brown->P2 (10), Cooper->P1 (9) = 25
    assert metric(r, "Total Biaya Minimum") == pytest.approx(25)


def test_unbalanced_and_maximize():
    df = pd.DataFrame([["W1", 10, 15, 9], ["W2", 9, 18, 5]], columns=["Worker", "T1", "T2", "T3"])
    r = get("assignment").solve(SheetData({"objective": "max"}, {"main": df}))
    # W1->T1 (10) + W2->T2 (18) = 28
    assert metric(r, "Total Optimal") == pytest.approx(28)
    assert r.warnings
