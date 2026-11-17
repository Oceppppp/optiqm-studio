"""Penulis file template Excel/CSV dari SheetData."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from optiqm.core import SheetData

_MARK_FONT = Font(bold=True, color="0F5257")
_HEAD_FILL = PatternFill("solid", fgColor="E6F0EF")


def _safe_title(name: str, used: set[str]) -> str:
    title = "".join(ch for ch in name if ch not in '[]:*?/\\')[:31] or "Sheet"
    base, i = title, 2
    while title in used:
        suffix = f"_{i}"
        title, i = base[: 31 - len(suffix)] + suffix, i + 1
    used.add(title)
    return title


def sheets_to_xlsx(items: Iterable[tuple[str, SheetData]]) -> bytes:
    """Tulis beberapa (nama_sheet, SheetData) ke satu workbook."""
    wb = Workbook()
    wb.remove(wb.active)
    used: set[str] = set()
    for name, sheet in items:
        ws = wb.create_sheet(_safe_title(name, used))
        header_next = False
        for r, row in enumerate(sheet.to_grid(), start=1):
            for c, val in enumerate(row, start=1):
                cell = ws.cell(row=r, column=c, value=val)
                if c == 1 and isinstance(val, str) and val.startswith("["):
                    cell.font = _MARK_FONT
                elif header_next:
                    cell.font = Font(bold=True)
                    cell.fill = _HEAD_FILL
            first = row[0] if row else None
            header_next = isinstance(first, str) and first.startswith("[") and first != "[params]"
        for col in range(1, ws.max_column + 1):
            ws.column_dimensions[get_column_letter(col)].width = 16
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def sheet_to_csv(sheet: SheetData) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    for row in sheet.to_grid():
        writer.writerow(["" if v is None else v for v in row])
    return buf.getvalue().encode("utf-8-sig")
