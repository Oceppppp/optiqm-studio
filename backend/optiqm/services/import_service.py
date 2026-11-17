"""Layanan impor file (Excel, CSV, JSON, Google Sheets) dan validasi kasus."""

from __future__ import annotations

import re
import urllib.request
import uuid
from typing import Any

from optiqm.core import InputError, OptiQMError, SheetData, all_modules, get
from optiqm.io import detect_module, read_file

_GSHEET_RE = re.compile(r"^https://docs\.google\.com/spreadsheets/d/([A-Za-z0-9_-]+)")


def import_bytes(content: bytes, filename: str) -> list[dict[str, Any]]:
    raw_cases = read_file(content, filename)
    out = []
    for rc in raw_cases:
        mod_key = detect_module(rc.name, rc.sheet.param("module"))
        status, err = _probe_case(mod_key, rc.sheet)
        out.append({
            "id": str(uuid.uuid4())[:8],
            "name": rc.name,
            "source": rc.source,
            "module": mod_key,
            "detected": mod_key is not None,
            "enabled": True,
            "status": status,
            "error": err,
            "sheet": rc.sheet.to_dict(),
        })
    return out


def import_google_sheet(url: str) -> list[dict[str, Any]]:
    """Ambil seluruh tab Google Sheets publik/link-shared sebagai .xlsx lalu impor."""
    m = _GSHEET_RE.match(url.strip())
    if not m:
        raise InputError("URL Google Sheets tidak valid (harus diawali https://docs.google.com/spreadsheets/d/...).")
    doc_id = m.group(1)
    export_url = f"https://docs.google.com/spreadsheets/d/{doc_id}/export?format=xlsx"
    req = urllib.request.Request(export_url, headers={"User-Agent": "OptiQM-Studio/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
    except Exception as exc:
        raise InputError(f"Gagal mengunduh Google Sheets (pastikan akses link publik / Anyone with link): {exc}") from exc
    return import_bytes(data, f"gsheet_{doc_id[:8]}.xlsx")


def validate_case(module_key: str | None, sheet_dict: dict[str, Any]) -> tuple[str, str | None]:
    return _probe_case(module_key, SheetData.from_dict(sheet_dict))


def sample_workbook_items() -> list[tuple[str, SheetData]]:
    """Bangun workbook contoh berisi modul paling populer (siap di-upload & Run All)."""
    featured = [
        ("LP_Produksi", "linear_programming"),
        ("TRANS_Gudang", "transportation"),
        ("ASSIGN_Tugas", "assignment"),
        ("FC_Penjualan", "forecasting"),
        ("EOQ_Persediaan", "eoq"),
        ("PERT_Proyek", "project_management"),
        ("QUEUE_Loket", "waiting_lines"),
        ("DT_Investasi", "decision_table"),
        ("BEP_Produk", "breakeven"),
        ("STAT_Sampel", "descriptive_statistics"),
    ]
    items = []
    available = {m.key: m for m in all_modules()}
    for sheet_name, key in featured:
        if key in available:
            tpl = available[key].template()
            tpl.params["module"] = key
            items.append((sheet_name, tpl))
    return items


def _probe_case(mod_key: str | None, sheet: SheetData) -> tuple[str, str | None]:
    if not mod_key:
        return "needs_module", "Modul belum terdeteksi — pilih modul secara manual."
    try:
        mod = get(mod_key)
        mod.solve(sheet)
        return "valid", None
    except OptiQMError as exc:
        return "invalid", str(exc)
    except Exception as exc:  # pragma: no cover
        return "invalid", f"Kesalahan data: {exc}"
