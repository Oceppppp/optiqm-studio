"""Konversi grid 2D (baris x kolom sel) <-> SheetData sesuai konvensi penanda ``[nama]``."""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

from optiqm.core import SheetData

_MARKER = re.compile(r"^\[\s*([A-Za-z0-9_ \-]+?)\s*\]$")
_NUMBER = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$")


def _is_blank(v: Any) -> bool:
    return v is None or (isinstance(v, float) and v != v) or (isinstance(v, str) and not v.strip())


def _coerce(v: Any) -> Any:
    """String angka -> int/float; string kosong -> None."""
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        if _NUMBER.match(s):
            f = float(s)
            return int(f) if f.is_integer() and "." not in s and "e" not in s.lower() else f
        return s
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v


def _trim(row: list[Any]) -> list[Any]:
    row = [_coerce(v) for v in row]
    while row and _is_blank(row[-1]):
        row.pop()
    return row


def _marker(row: list[Any]) -> str | None:
    cells = [v for v in row if not _is_blank(v)]
    if len(cells) == 1 and isinstance(cells[0], str) and not _is_blank(row[0]):
        m = _MARKER.match(cells[0].strip())
        if m:
            return m.group(1).strip().lower().replace(" ", "_")
    return None


def _frame(header: list[Any], rows: list[list[Any]]) -> pd.DataFrame:
    width = max([len(header)] + [len(r) for r in rows]) if (header or rows) else 0
    cols, seen = [], set()
    for j in range(width):
        name = str(header[j]).strip() if j < len(header) and not _is_blank(header[j]) else f"Kolom{j + 1}"
        base, k = name, 2
        while name in seen:
            name, k = f"{base}_{k}", k + 1
        seen.add(name)
        cols.append(name)
    data = [r + [None] * (width - len(r)) for r in rows]
    return pd.DataFrame(data, columns=cols)


def grid_to_sheet(grid: list[list[Any]]) -> SheetData:
    """Parse grid sel menjadi SheetData."""
    rows = [_trim(list(r)) for r in grid]
    has_markers = any(_marker(r) for r in rows)
    sheet = SheetData()

    if not has_markers:
        body = [r for r in rows if r]
        if body:
            sheet.tables["main"] = _frame(body[0], body[1:])
        return sheet

    section: str | None = None
    header: list[Any] | None = None
    buf: list[list[Any]] = []

    def flush() -> None:
        if section and section != "params" and header is not None:
            sheet.tables[section] = _frame(header, buf)

    for r in rows:
        name = _marker(r)
        if name:
            flush()
            section, header, buf = name, None, []
            continue
        if section is None:
            continue
        if section == "params":
            if r and not _is_blank(r[0]):
                sheet.params[str(r[0]).strip()] = r[1] if len(r) > 1 else None
            continue
        if not r:  # baris kosong = akhir tabel
            if header is not None:
                flush()
                section, header, buf = None, None, []
            continue
        if header is None:
            header = r
        else:
            buf.append(r)
    flush()
    return sheet
