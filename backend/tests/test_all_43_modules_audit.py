"""Audit komprehensif: verifikasi matematis, edge cases, analisis mendalam, dan ekspor untuk SEMUA 43 modul."""

from __future__ import annotations

import json
import math

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from optiqm.api import create_app
from optiqm.core import InputError, SheetData, SolverError, all_modules, get
from optiqm.core.parsing import to_float
from optiqm.services import export_excel, export_pdf

from conftest import metric, run_template

client = TestClient(create_app())


# ---------------------------------------------------------------------------
# 1. Semua 43 modul berjalan sukses, JSON-valid, dan punya Analisis Mendalam
# ---------------------------------------------------------------------------
def test_all_43_modules_run_and_have_deep_analysis():
    mods = all_modules()
    assert len(mods) == 43

    for mod in mods:
        res = mod.solve(mod.template())
        payload = res.to_dict()
        # Harus valid JSON
        encoded = json.dumps(payload, allow_nan=False)
        assert len(encoded) > 100
        assert res.interpretation.strip(), f"{mod.key} kehilangan interpretation"
        assert len(res.analysis) >= 2, f"{mod.key} harus memiliki minimal 2 blok analisis mendalam"
        for sec in res.analysis:
            assert sec.title.strip(), f"{mod.key} punya judul analisis kosong"
            assert sec.content.strip() or sec.bullets, f"{mod.key} punya isi analisis kosong"


def test_batch_and_reports_all_43_modules_end_to_end():
    mods = all_modules()
    cases = [
        {
            "id": f"m_{i}",
            "name": f"Kasus_{m.key}",
            "module": m.key,
            "enabled": True,
            "sheet": m.template().to_dict(),
        }
        for i, m in enumerate(mods, start=1)
    ]
    run = client.post("/api/batch/run", json={"cases": cases})
    assert run.status_code == 200
    body = run.json()
    assert body["total"] == 43
    assert body["succeeded"] == 43
    assert body["failed"] == 0
    for item in body["results"]:
        assert item["status"] == "ok"
        assert len(item["result"]["analysis"]) >= 2

    xlsx = export_excel("Audit_43_Modul", body["results"])
    assert len(xlsx) > 15000
    pdf = export_pdf("Audit_43_Modul", body["results"])
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 10000


# ---------------------------------------------------------------------------
# 2. Verifikasi perbaikan bug kritis & angka matematis eksak
# ---------------------------------------------------------------------------
def test_aggregate_planning_no_ending_backorder_and_all_strategies():
    # Bug lama: LP meninggalkan Backorder = 1100 pada Jun karena backorder_cost (20) < regular_cost (40)
    r = run_template("aggregate_planning")
    sched_tbl = r.tables[0]
    last_row = sched_tbl.rows[-1]
    assert last_row[0] == "Jun"
    assert last_row[6] == pytest.approx(0.0, abs=1e-6)  # Backorder akhir wajib 0
    # Total produksi harus memenuhi total demand (800+1000+1200+900+700+1100 = 5700)
    tot_prod = sum(row[2] + row[3] + row[4] for row in sched_tbl.rows)
    assert tot_prod == pytest.approx(5700.0, abs=1e-5)

    # Chase & Level juga harus sukses
    for strat in ("chase", "level"):
        tpl = get("aggregate_planning").template()
        tpl.params["strategy"] = strat
        rs = get("aggregate_planning").solve(tpl)
        assert metric(rs, "Total Biaya Agregat") >= metric(r, "Total Biaya Agregat") - 1e-6

    # Kapasitas total kurang dari permintaan -> SolverError jelas
    bad_df = pd.DataFrame([["P1", 1000, 300, 100, 0]], columns=["Period", "Demand", "Regular_Cap", "Overtime_Cap", "Subcontract_Cap"])
    with pytest.raises(SolverError):
        get("aggregate_planning").solve(SheetData({"strategy": "optimal"}, {"main": bad_df}))


def test_operations_layout_no_double_counting_heizer_render():
    # Template Heizer & Render (matriks segitiga atas): biaya awal = 10,800, optimal = 7,400 (bukan 21,600 / 14,800!)
    r = run_template("operations_layout")
    assert metric(r, "Biaya Penempatan Awal") == pytest.approx(10800.0)
    assert metric(r, "Total Biaya Load×Distance Optimal") == pytest.approx(7400.0)
    assert metric(r, "Penghematan") == pytest.approx(3400.0)


def test_integer_programming_binary_lp_relaxation_bounds_and_nan_type():
    # Binary knapsack: max 60X1+100X2+120X3 s.t. 10X1+20X2+30X3 <= 50, X_i in {0,1}
    # Solusi LP Relaxation benar = 240 (X1=1, X2=1, X3=2/3), BUKAN 300 (X1=5)!
    df = pd.DataFrame(
        [["Objective", 60, 100, 120, None, None],
         ["Type", "bin", "bin", None, None, None],  # None/NaN -> fallback ke default_type="bin"
         ["Kapasitas", 10, 20, 30, "<=", 50]],
        columns=["Name", "X1", "X2", "X3", "Sign", "RHS"],
    )
    r = get("integer_programming").solve(SheetData({"objective": "max", "default_type": "bin"}, {"main": df}))
    assert metric(r, "Nilai Optimal Z (Integer)") == pytest.approx(220.0)
    assert metric(r, "Nilai LP Relaxation") == pytest.approx(240.0)


def test_breakeven_single_param_edit_and_multiproduct():
    # Mengedit parameter price/variable_cost pada template single-product harus langsung berpengaruh!
    tpl = get("breakeven").template()
    tpl.params["price"] = 30.0
    tpl.params["variable_cost"] = 10.0
    r = get("breakeven").solve(tpl)
    assert metric(r, "BEP (Unit)") == pytest.approx(500.0)  # 10000 / (30 - 10)
    assert metric(r, "BEP (Nilai Penjualan)") == pytest.approx(15000.0)

    # Multi-produk (2 produk) tetap menggunakan tabel
    mp_df = pd.DataFrame(
        [["A", 10, 6, 50], ["B", 20, 10, 50]],
        columns=["Product", "Price", "Variable_Cost", "Share"],
    )
    rm = get("breakeven").solve(SheetData({"fixed_cost": 7000, "volume": 1500}, {"main": mp_df}))
    # w_price = 15, w_vc = 8, w_cm = 7 -> BEP unit = 1000, BEP rev = 15000
    assert metric(rm, "BEP (Unit)") == pytest.approx(1000.0)
    assert metric(rm, "BEP (Nilai Penjualan)") == pytest.approx(15000.0)


def test_eoq_param_precedence_and_table_fallback():
    # 1. Edit params mengalahkan tabel [main] jika keduanya ada
    df_old = pd.DataFrame([["D", 1000], ["S", 10], ["H", 0.5], ["working_days", 250], ["lead_time", 4]],
                          columns=["Parameter", "Value"])
    r1 = get("eoq").solve(SheetData({"D": 4000, "S": 10, "H": 0.5, "working_days": 200, "lead_time": 5}, {"main": df_old}))
    assert metric(r1, "EOQ (Q*)") == pytest.approx(400.0)
    assert metric(r1, "Reorder Point (ROP)") == pytest.approx(100.0)  # (4000/200)*5

    # 2. Upload Excel yang HANYA berisi tabel [main] Parameter|Value (tanpa params) tetap bekerja!
    df_only = pd.DataFrame([["D", 2000], ["S", 25], ["H", 1.0], ["working_days", 250], ["lead_time", 3]],
                           columns=["Parameter", "Value"])
    r2 = get("eoq").solve(SheetData({}, {"main": df_only}))
    assert metric(r2, "EOQ (Q*)") == pytest.approx(math.sqrt(2 * 2000 * 25 / 1.0))
    assert metric(r2, "Reorder Point (ROP)") == pytest.approx(24.0)


def test_capital_investment_non_sequential_years_irr_and_pi():
    # Year=[0, 2], CF=[-100, 121] -> pada r=10%: NPV=0, IRR=10.00%, PI=1.0
    df = pd.DataFrame([[0, -100], [2, 121]], columns=["Year", "Proyek X"])
    r = get("capital_investment").solve(SheetData({"discount_rate": 10}, {"main": df}))
    assert metric(r, "NPV (Proyek X)") == pytest.approx(0.0, abs=1e-6)
    row = r.tables[0].rows[0]
    assert row[2] == "10.00%"
    assert row[5] == pytest.approx(1.0, abs=1e-5)

    # Arus kas dengan 2 tahun negatif: PI = PV(inflows)/PV(outflows)
    df2 = pd.DataFrame([[0, -100], [1, -110], [2, 242]], columns=["Year", "Proyek Y"])
    r2 = get("capital_investment").solve(SheetData({"discount_rate": 10}, {"main": df2}))
    # PV_out = 100 + 110/1.1 = 200; PV_in = 242/1.21 = 200 -> NPV = 0, PI = 1.0
    assert metric(r2, "NPV (Proyek Y)") == pytest.approx(0.0, abs=1e-6)
    assert r2.tables[0].rows[0][5] == pytest.approx(1.0, abs=1e-5)


def test_job_shop_dynamic_critical_ratio():
    tpl = get("job_shop_scheduling").template()
    tpl.params["rule"] = "cr"
    r = get("job_shop_scheduling").solve(tpl)
    # Dynamic CR pada template Heizer & Render -> A -> B -> C -> D -> E (avg completion = 15.4, avg lateness = 2.2)
    seq = [row[0] for row in r.tables[0].rows]
    assert seq == ["A", "B", "C", "D", "E"]
    assert metric(r, "Rata-rata Waktu Penyelesaian") == pytest.approx(15.4)
    assert metric(r, "Rata-rata Keterlambatan") == pytest.approx(2.2)


def test_decision_tree_validation_and_no_double_count():
    # Node non-terminal tanpa anak tidak boleh double-count payoff, dan root pay dihitung
    df = pd.DataFrame(
        [["R", "-", "decision", "Akar", None, -10],
         ["C1", "R", "chance", "Opsi A", None, 50],
         ["C2", "R", "terminal", "Opsi B", None, 30]],
        columns=["Node", "Parent", "Type", "Branch", "Probability", "Payoff"],
    )
    r = get("decision_tree").solve(SheetData({"payoff_type": "profit"}, {"main": df}))
    # Opsi A (childless chance -> payoff 50), Opsi B (terminal -> 30); best = 50 + root(-10) = 40 (BUKAN 100!)
    assert metric(r, "EMV Optimal") == pytest.approx(40.0)

    # Parent tidak ditemukan -> InputError
    bad_orphan = pd.DataFrame(
        [["R", "-", "decision", "Akar", None, 0],
         ["X", "MISSING", "terminal", "Orphan", None, 10]],
        columns=["Node", "Parent", "Type", "Branch", "Probability", "Payoff"],
    )
    with pytest.raises(InputError):
        get("decision_tree").solve(SheetData({"payoff_type": "profit"}, {"main": bad_orphan}))


def test_control_charts_z_scaling_and_validation():
    tpl = get("control_charts").template()
    tpl.params["z_sigma"] = 2.0
    r2 = get("control_charts").solve(tpl)
    tpl3 = get("control_charts").template()
    tpl3.params["z_sigma"] = 3.0
    r3 = get("control_charts").solve(tpl3)
    # Pada z=2, UCL peta R harus lebih sempit dibanding z=3
    ucl_r_2 = r2.charts[1].data["series"][1]["data"][0]
    ucl_r_3 = r3.charts[1].data["series"][1]["data"][0]
    assert ucl_r_2 < ucl_r_3

    # p-chart: Defects > Size harus raise InputError
    bad_p = pd.DataFrame([["S1", 120, 100], ["S2", 5, 100]], columns=["Sample", "Defects", "Size"])
    with pytest.raises(InputError):
        get("control_charts").solve(SheetData({"chart_type": "p"}, {"main": bad_p}))


def test_acceptance_sampling_exact_aoql_and_full_inspection():
    # N == n (inspeksi 100%): AOQ = 0 dan AOQL = 0.000%
    r_full = get("acceptance_sampling").solve(
        SheetData({"n": 100, "c": 2, "aql": 0.02, "ltpd": 0.10, "lot_size": 100, "distribution": "binomial"})
    )
    assert metric(r_full, "AOQL (Maksimum Rata-rata Cacat Lolos)") == "0.000%"

    # N < n -> InputError
    with pytest.raises(InputError):
        get("acceptance_sampling").solve(SheetData({"n": 50, "c": 2, "lot_size": 30}))


def test_mrp_past_due_warning_and_explosion():
    # A (LT=2) butuh 10 di P1 -> past due; A -> 2*B (LT=1) -> B juga harus meledak dan punya warning past-due!
    bom = pd.DataFrame([["A", "B", 2]], columns=["Parent", "Child", "Qty"])
    items = pd.DataFrame([["A", 2, 0, 0], ["B", 1, 0, 0]], columns=["Item", "Lead_Time", "On_Hand", "Lot_Size"])
    mps = pd.DataFrame([["A", 1, 10, 0]], columns=["Item", "Period", "Gross_Requirement", "Scheduled_Receipt"])
    r = get("mrp").solve(SheetData({"horizon": 4}, {"main": bom, "items": items, "mps": mps}))
    assert len(r.warnings) >= 2
    assert metric(r, "Total Planned Releases") == pytest.approx(30.0)  # A=10 + B=20


def test_project_management_pert_validation_and_multi_critical_path():
    # Invalid PERT a > m -> InputError
    bad_pert = pd.DataFrame([["A", "-", 5, 3, 7]], columns=["Activity", "Predecessors", "Optimistic", "Most_Likely", "Pessimistic"])
    with pytest.raises(InputError):
        get("project_management").solve(SheetData({}, {"main": bad_pert}))

    # Dua jalur kritis paralel dengan varians berbeda: pilih varians terbesar!
    # Jalur 1: A (a=4,m=4,b=4 -> t=4, var=0); Jalur 2: B (a=1,m=4,b=7 -> t=4, var=1)
    df_par = pd.DataFrame(
        [["A", "-", 4, 4, 4], ["B", "-", 1, 4, 7]],
        columns=["Activity", "Predecessors", "Optimistic", "Most_Likely", "Pessimistic"],
    )
    r = get("project_management").solve(SheetData({}, {"main": df_par}))
    assert metric(r, "Durasi Proyek") == pytest.approx(4.0)
    assert metric(r, "Std. Deviasi Jalur Kritis") == pytest.approx(1.0)
    assert len(r.warnings) >= 1


def test_project_crashing_negative_slope_and_large_span_cap():
    bad_cc = pd.DataFrame([["A", "-", 10, 5, 1000, 900]],
                          columns=["Activity", "Predecessors", "Normal_Time", "Crash_Time", "Normal_Cost", "Crash_Cost"])
    with pytest.raises(InputError):
        get("project_crashing").solve(SheetData({"target_duration": "5"}, {"main": bad_cc}))

    # Rentang durasi sangat besar (1000 -> 100) harus tetap cepat (<=25 titik kurva)
    big = pd.DataFrame([["A", "-", 1000, 100, 10000, 19000]],
                       columns=["Activity", "Predecessors", "Normal_Time", "Crash_Time", "Normal_Cost", "Crash_Cost"])
    r = get("project_crashing").solve(SheetData({"target_duration": "500"}, {"main": big}))
    assert len(r.charts[0].data["x"]) <= 25
    assert metric(r, "Tambahan Biaya Crash") == pytest.approx(5000.0)


def test_location_breakeven_default_volume():
    # Tanpa param volume eksplisit -> pakai default LocationBreakeven = 2000 (bukan 2500!)
    tpl = get("location_breakeven").template()
    r = get("location_breakeven").solve(SheetData({}, tpl.tables))
    assert metric(r, "Terbaik pada Volume 2000") == "Bowling Green"
    assert metric(r, "Total Biaya Minimum") == pytest.approx(150000.0)


def test_work_measurement_validation_and_constant_obs():
    tpl = get("work_measurement").template()
    tpl.params["confidence"] = 100
    with pytest.raises(InputError):
        get("work_measurement").solve(tpl)

    # Observasi identik -> std=0 -> req_n minimal 1 (bukan 0)
    df = pd.DataFrame([["E1", 100, 2.0, 2.0, 2.0]], columns=["Element", "Rating", "Obs_1", "Obs_2", "Obs_3"])
    r = get("work_measurement").solve(SheetData({"allowance": 15, "confidence": 95, "accuracy": 5}, {"main": df}))
    assert metric(r, "Sampel Minimum Dibutuhkan") == 1


def test_waiting_lines_large_s_and_N_no_overflow():
    r_mms = get("waiting_lines").solve(SheetData({"model": "mms", "arrival_rate": 100, "service_rate": 1.2, "servers": 120}))
    assert metric(r_mms, "Rata-rata dalam Sistem (L)") > 0
    r_fin = get("waiting_lines").solve(SheetData({"model": "mm1_finite_population", "arrival_rate": 0.01, "service_rate": 5.0, "population": 200}))
    assert metric(r_fin, "Rata-rata dalam Sistem (L)") > 0


def test_assignment_infeasible_prohibited_raises_solver_error():
    df = pd.DataFrame([["W1", "X", "X"], ["W2", 5, 6]], columns=["Worker", "T1", "T2"])
    with pytest.raises(SolverError):
        get("assignment").solve(SheetData({"objective": "min"}, {"main": df}))


def test_network_parallel_edges():
    # Max flow: dua sisi paralel 1->2 dengan kap 5 dan 7 -> total aliran = 12
    df_mf = pd.DataFrame([["1", "2", 5], ["1", "2", 7]], columns=["From", "To", "Capacity"])
    r_mf = get("max_flow").solve(SheetData({"source": "1", "sink": "2"}, {"main": df_mf}))
    assert metric(r_mf, "Aliran Maksimum") == pytest.approx(12.0)

    # Shortest route & MST: sisi paralel harus pilih yang terpendek (3, bukan 9)
    df_sr = pd.DataFrame([["1", "2", 3], ["1", "2", 9]], columns=["From", "To", "Distance"])
    r_sr = get("shortest_route").solve(SheetData({"start": "1", "end": "2"}, {"main": df_sr}))
    assert metric(r_sr, "Total Jarak Terpendek") == pytest.approx(3.0)
    r_mst = get("minimal_spanning_tree").solve(SheetData({}, {"main": df_sr}))
    assert metric(r_mst, "Total Panjang / Biaya Minimum") == pytest.approx(3.0)


def test_parsing_thousands_and_nan_rejection():
    assert to_float("1,250.50") == pytest.approx(1250.5)
    assert to_float("1.250,50") == pytest.approx(1250.5)
    assert to_float("1,5") == pytest.approx(1.5)
    assert to_float("1,000,000") == pytest.approx(1000000.0)
    with pytest.raises(InputError):
        to_float("nan")
    with pytest.raises(InputError):
        to_float("inf")
