"""Test Kualitas, Keandalan, Lokasi, dan Tata Letak."""

import pytest

from conftest import metric, run_template


def test_quality_and_reliability():
    rc = run_template("control_charts")
    assert metric(rc, "Titik Out of Control") >= 0
    ras = run_template("acceptance_sampling")
    assert metric(ras, "AOQL (Maksimum Rata-rata Cacat Lolos)")
    rr = run_template("reliability")
    # 0.90 * (1 - 0.2*0.2) * 0.99 = 0.90 * 0.96 * 0.99 = 0.85536
    assert metric(rr, "Keandalan Sistem Total (Rs)") == pytest.approx(0.85536)


def test_location_and_layout():
    rf = run_template("factor_rating")
    assert metric(rf, "Lokasi Terbaik") == "Prancis"
    assert metric(rf, "Skor Terbobot Tertinggi") == pytest.approx(70.35)

    rc = run_template("center_of_gravity")
    # Cx = (30*2+90*1+130*1+60*2)/6 = 400/6 = 66.6667; Cy = (240+110+130+80)/6 = 560/6 = 93.3333
    assert metric(rc, "Koordinat Pusat X*") == pytest.approx(66.6667, abs=0.01)
    assert metric(rc, "Koordinat Pusat Y*") == pytest.approx(93.3333, abs=0.01)

    rl = run_template("location_breakeven")
    assert metric(rl, "Terbaik pada Volume 2000") == "Bowling Green"

    rly = run_template("operations_layout")
    assert metric(rly, "Total Biaya Load×Distance Optimal") <= metric(rly, "Biaya Penempatan Awal")
