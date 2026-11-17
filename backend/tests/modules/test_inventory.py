"""Test modul persediaan: EOQ, POQ, Quantity Discount, Safety Stock, ABC."""

import pytest

from conftest import metric, run_template


def test_eoq_sharp_inc():
    r = run_template("eoq")
    assert metric(r, "EOQ (Q*)") == pytest.approx(200)
    assert metric(r, "Total Biaya Persediaan") == pytest.approx(100)
    assert metric(r, "Frekuensi Order / Tahun") == pytest.approx(5)
    assert metric(r, "Reorder Point (ROP)") == pytest.approx(16)


def test_poq_nathan():
    r = run_template("production_order_quantity")
    assert metric(r, "Lot Produksi Optimal (Qp*)") == pytest.approx(282.8427, rel=1e-4)


def test_quantity_discount_wohls():
    r = run_template("quantity_discount")
    assert metric(r, "Kuantitas Order Optimal (Q*)") == pytest.approx(1000)
    assert metric(r, "Total Biaya Minimum") == pytest.approx(24725)


def test_safety_stock_memphis():
    r = run_template("safety_stock")
    assert metric(r, "Safety Stock") == pytest.approx(16.4485, abs=0.05)
    assert metric(r, "Reorder Point (ROP)") == pytest.approx(366.45, abs=0.1)


def test_abc_analysis():
    r = run_template("abc_analysis")
    assert metric(r, "Item Kelas A") == 3
    assert metric(r, "Item Kelas B") == 2
    assert metric(r, "Item Kelas C") == 5
