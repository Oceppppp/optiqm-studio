"""Integration test: I/O (Excel/CSV/JSON), auto-detect, Batch Runner, FastAPI endpoints, dan Report PDF/XLSX."""

from fastapi.testclient import TestClient

from optiqm.api import create_app
from optiqm.io import sheet_to_csv, sheets_to_xlsx
from optiqm.services import sample_workbook_items

client = TestClient(create_app())


def test_list_modules_and_templates():
    res = client.get("/api/modules")
    assert res.status_code == 200
    data = res.json()
    assert data["count"] == 43

    tpl_xlsx = client.get("/api/modules/transportation/template?format=xlsx")
    assert tpl_xlsx.status_code == 200
    assert len(tpl_xlsx.content) > 500

    tpl_csv = client.get("/api/modules/eoq/template?format=csv")
    assert tpl_csv.status_code == 200


def test_upload_10_sheet_workbook_and_run_all_and_export():
    # 1. Unduh workbook contoh 10 sheet
    wb_res = client.get("/api/templates/sample-workbook.xlsx")
    assert wb_res.status_code == 200

    # 2. Upload ke /api/workspace/import -> auto-detect semua 10 modul
    imp = client.post(
        "/api/workspace/import",
        files=[("files", ("Tugas_MO.xlsx", wb_res.content,
                          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))],
    )
    assert imp.status_code == 200
    cases = imp.json()["cases"]
    assert len(cases) == 10
    assert all(c["detected"] and c["status"] == "valid" for c in cases)

    # 3. Jalankan semua 10 modul sekaligus via /api/batch/run
    run = client.post("/api/batch/run", json={"cases": cases})
    assert run.status_code == 200
    batch = run.json()
    assert batch["total"] == 10
    assert batch["succeeded"] == 10
    assert batch["failed"] == 0

    # 4. Ekspor laporan gabungan Excel & PDF
    rx = client.post("/api/report/xlsx", json={"workspace_name": "Tugas_MO", "items": batch["results"]})
    assert rx.status_code == 200
    assert len(rx.content) > 2000

    rp = client.post("/api/report/pdf", json={"workspace_name": "Tugas_MO", "items": batch["results"]})
    assert rp.status_code == 200
    assert rp.content[:4] == b"%PDF"


def test_batch_error_isolation():
    cases = [
        {"id": "1", "name": "LP Baik", "module": "linear_programming", "enabled": True,
         "sheet": client.get("/api/modules").json()["modules"][0]["template"]},
        {"id": "2", "name": "Error Case", "module": "eoq", "enabled": True,
         "sheet": {"params": {"D": -5, "S": 10, "H": 1}, "tables": {}}},
    ]
    # Pastikan case 1 pakai LP template asli
    lp_tpl = next(m["template"] for m in client.get("/api/modules").json()["modules"] if m["key"] == "linear_programming")
    cases[0]["sheet"] = lp_tpl
    res = client.post("/api/batch/run", json={"cases": cases}).json()
    assert res["succeeded"] == 1
    assert res["failed"] == 1
