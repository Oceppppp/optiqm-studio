"""Test Penjadwalan, Produktivitas, Capital Investment, Statistik, dan Error Analysis."""

import pytest

from conftest import metric, run_template


def test_scheduling_and_line_balancing():
    rl = run_template("line_balancing")
    assert metric(rl, "Cycle Time") == pytest.approx(12)
    assert metric(rl, "Jumlah Stasiun Kerja") == 6

    rs = run_template("job_shop_scheduling")
    # SPT order: B(2), D(3), A(6), C(8), E(9) -> flow: 2, 5, 11, 19, 28 => avg = 65/5 = 13.0
    assert metric(rs, "Rata-rata Waktu Penyelesaian") == pytest.approx(13.0)

    rj = run_template("johnsons_rule")
    assert metric(rj, "Makespan (Total Waktu Selesai)") == pytest.approx(35)


def test_productivity_and_investment():
    rlc = run_template("learning_curve")
    # 100 * 8^(log2 0.8) = 100 * 0.8^3 = 51.2
    assert metric(rlc, "Waktu Unit ke-8") == pytest.approx(51.2)

    rp = run_template("productivity")
    assert metric(rp, "MFP (Periode 1)") == pytest.approx(1000 / 800)

    rw = run_template("work_measurement")
    assert metric(rw, "Waktu Standar (Standard Time)") > metric(rw, "Total Waktu Normal")

    rn = run_template("capital_investment")
    assert metric(rn, "NPV (Proyek B)") if False else metric(rn, "Proyek Terbaik (NPV)") == "Proyek B"


def test_statistics_and_error():
    rs = run_template("descriptive_statistics")
    assert metric(rs, "Rata-rata (Waktu_Layanan)") > 10

    re = run_template("error_analysis")
    assert metric(re, "MAD") == pytest.approx((5 + 5 + 7 + 5 + 5) / 5)
