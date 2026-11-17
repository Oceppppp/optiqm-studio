"""Test modul Perencanaan Produksi: Aggregate Planning, MRP, Lot Sizing."""

import pytest

from conftest import metric, run_template


def test_aggregate_planning():
    r = run_template("aggregate_planning")
    assert metric(r, "Total Biaya Agregat") > 0


def test_mrp_speaker_kit():
    r = run_template("mrp")
    # Produk A butuh 50 di P8 & 20 di P6, on_hand A=10 -> net P6=10 (release P5=10), P8=50 (release P7=50)
    # Cek B butuh 2*10=20 di P5 (stok 15 -> net 5) & 2*50=100 di P7
    assert metric(r, "Jumlah Item") == 5
    assert metric(r, "Total Planned Releases") > 0


def test_lot_sizing_wagner_whitin():
    r = run_template("lot_sizing")
    # Wagner-Whitin <= biaya metode heuristik lainnya
    comp = next(t for t in r.tables if t.title.startswith("Perbandingan"))
    ww_cost = comp.rows[0][3]
    for row in comp.rows:
        assert ww_cost <= row[3] + 1e-6
