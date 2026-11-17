"""Eksekusi batch banyak modul sekaligus (paralel + terisolasi error)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import time
from typing import Any

from optiqm.core import OptiQMError, SheetData, get


def run_case(case: dict[str, Any]) -> dict[str, Any]:
    cid = case.get("id", "")
    name = case.get("name", "Kasus")
    mod_key = case.get("module")
    t0 = time.perf_counter()
    if not mod_key:
        return {"id": cid, "name": name, "module": None, "status": "error",
                "error": "Modul belum dipilih.", "duration_ms": 0.0, "result": None}
    try:
        mod = get(mod_key)
        sheet = SheetData.from_dict(case.get("sheet") or {})
        res = mod.solve(sheet)
        dt = (time.perf_counter() - t0) * 1000.0
        return {
            "id": cid, "name": name, "module": mod.key, "module_name": mod.name,
            "category": mod.category, "status": "ok", "error": None,
            "duration_ms": round(dt, 2), "result": res.to_dict(),
        }
    except OptiQMError as exc:
        dt = (time.perf_counter() - t0) * 1000.0
        return {
            "id": cid, "name": name, "module": mod_key, "status": "error",
            "error": str(exc), "duration_ms": round(dt, 2), "result": None,
        }
    except Exception as exc:  # pragma: no cover
        dt = (time.perf_counter() - t0) * 1000.0
        return {
            "id": cid, "name": name, "module": mod_key, "status": "error",
            "error": f"Kesalahan internal solver: {exc}", "duration_ms": round(dt, 2), "result": None,
        }


def run_batch(cases: list[dict[str, Any]], max_workers: int = 4) -> dict[str, Any]:
    active = [c for c in cases if c.get("enabled", True)]
    t0 = time.perf_counter()
    if len(active) <= 1:
        results = [run_case(c) for c in active]
    else:
        with ThreadPoolExecutor(max_workers=min(max_workers, len(active))) as pool:
            results = list(pool.map(run_case, active))
    total_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    ok = sum(1 for r in results if r["status"] == "ok")
    return {
        "total": len(results), "succeeded": ok, "failed": len(results) - ok,
        "duration_ms": total_ms, "results": results,
    }
