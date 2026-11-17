"""Pembaca file: Excel (.xlsx/.xlsm), CSV/TSV/TXT, dan JSON.

Setiap reader menghasilkan daftar :class:`RawCase` (nama kasus + SheetData).
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from pathlib import PurePath

from openpyxl import load_workbook

from optiqm.core import InputError, SheetData

from .grid import grid_to_sheet

MAX_ROWS = 5000
MAX_COLS = 200


@dataclass
class RawCase:
    name: str          # nama sheet / file
    source: str        # nama file asal
    sheet: SheetData


def read_excel(content: bytes, filename: str) -> list[RawCase]:
    try:
        wb = load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    except Exception as exc:
        raise InputError(f"File Excel '{filename}' tidak dapat dibaca: {exc}") from exc
    cases = []
    for ws in wb.worksheets:
        grid = [list(row[:MAX_COLS]) for row in ws.iter_rows(max_row=MAX_ROWS, values_only=True)]
        sheet = grid_to_sheet(grid)
        if sheet.tables or sheet.params:
            cases.append(RawCase(ws.title, filename, sheet))
    wb.close()
    return cases


def read_csv(content: bytes, filename: str) -> list[RawCase]:
    text = _decode(content)
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ","
    grid = list(csv.reader(io.StringIO(text), delimiter=delimiter))[:MAX_ROWS]
    return [RawCase(PurePath(filename).stem, filename, grid_to_sheet(grid))]


def read_json(content: bytes, filename: str) -> list[RawCase]:
    """Format: ``{"cases": [{"name", "module", "params", "tables"}]}`` atau satu objek kasus."""
    try:
        data = json.loads(_decode(content))
    except json.JSONDecodeError as exc:
        raise InputError(f"JSON '{filename}' tidak valid: {exc}") from exc
    items = data.get("cases", [data]) if isinstance(data, dict) else data
    cases = []
    for i, item in enumerate(items):
        sheet = SheetData.from_dict(item)
        if item.get("module"):
            sheet.params.setdefault("module", item["module"])
        cases.append(RawCase(item.get("name") or f"{PurePath(filename).stem}_{i + 1}", filename, sheet))
    return cases


READERS = {
    ".xlsx": read_excel, ".xlsm": read_excel,
    ".csv": read_csv, ".tsv": read_csv, ".txt": read_csv,
    ".json": read_json, ".oqm": read_json,
}


def read_file(content: bytes, filename: str) -> list[RawCase]:
    ext = PurePath(filename).suffix.lower()
    reader = READERS.get(ext)
    if reader is None:
        raise InputError(
            f"Format '{ext or filename}' tidak didukung. Gunakan: {', '.join(sorted(READERS))}. "
            "(File .xls lama: simpan ulang sebagai .xlsx)"
        )
    return reader(content, filename)


def _decode(content: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return content.decode(enc)
        except UnicodeDecodeError:
            continue
    raise InputError("Encoding file tidak dikenali.")
