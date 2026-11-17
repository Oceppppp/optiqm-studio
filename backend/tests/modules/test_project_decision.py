"""Test modul Project Management, Crashing, Waiting Lines, Decision Table, Decision Tree."""

import pytest

from optiqm.core import SheetData, get

from conftest import metric, run_template


def test_pert_cpm_milwaukee():
    r = run_template("project_management")
    assert metric(r, "Durasi Proyek") == pytest.approx(15)
    assert "A → C → E → G → H" in metric(r, "Jalur Kritis")
    assert any(c.kind == "network" for c in r.charts)
    assert any(c.kind == "gantt" for c in r.charts)


def test_project_crashing():
    r = run_template("project_crashing")
    # Normal=15 -> 14: crash A (750); di 14 jalur B-D-G-H ikut kritis, crash G (1500) -> total 2250
    assert metric(r, "Tambahan Biaya Crash") == pytest.approx(2250)


def test_waiting_lines_mm1_and_mms():
    r = run_template("waiting_lines")
    assert metric(r, "Rata-rata dalam Sistem (L)") == pytest.approx(2.0)
    assert metric(r, "Rata-rata Antri (Lq)") == pytest.approx(4 / 3, rel=1e-4)

    rm = get("waiting_lines").solve(SheetData({"model": "mms", "arrival_rate": 2, "service_rate": 3, "servers": 2}))
    # M/M/2: a=2/3, rho=1/3 -> Lq = 1/12 = 0.083333? cek: P0 = 1/(1 + 2/3 + (4/9)/2 * 3/2) = 1/(1+2/3+1/3)=0.5
    # Lq = 0.5 * (4/9) * (1/3) / (2 * (2/3)^2) = (2/27) / (8/9) = 1/12
    assert metric(rm, "Rata-rata Antri (Lq)") == pytest.approx(1 / 12, rel=1e-4)


def test_decision_table_and_tree():
    rd = run_template("decision_table")
    assert metric(rd, "Keputusan Terbaik (EMV)") == "Pabrik Kecil"
    assert metric(rd, "EMV Terbaik") == pytest.approx(40000)
    assert metric(rd, "EVPI (Nilai Informasi Sempurna)") == pytest.approx(60000)

    rt = run_template("decision_tree")
    assert metric(rt, "EMV Optimal") == pytest.approx(40000)
    assert metric(rt, "Keputusan Awal Terbaik") == "Bangun Pabrik Kecil"
