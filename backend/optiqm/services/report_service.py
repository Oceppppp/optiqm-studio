"""Generator laporan gabungan Excel (.xlsx) dan PDF untuk semua hasil batch."""

from __future__ import annotations

import io
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table as RLTable, TableStyle

from optiqm.io.writers import _safe_title

_TEAL = PatternFill("solid", fgColor="0F5257")
_SOFT = PatternFill("solid", fgColor="E9F2F1")
_BOLD_WHITE = Font(bold=True, color="FFFFFF")
_BOLD = Font(bold=True)


def export_excel(workspace_name: str, items: list[dict[str, Any]]) -> bytes:
    wb = Workbook()
    ws0 = wb.active
    ws0.title = "Ringkasan Eksekutif"
    used = {"Ringkasan Eksekutif"}

    ws0.append([f"OptiQM Studio — Laporan Gabungan: {workspace_name}"])
    ws0.cell(1, 1).font = Font(bold=True, size=14, color="0F5257")
    ws0.append([])
    headers = ["No", "Kasus", "Modul", "Status", "Ringkasan Utama", "Interpretasi"]
    ws0.append(headers)
    for col in range(1, len(headers) + 1):
        c = ws0.cell(3, col)
        c.font, c.fill = _BOLD_WHITE, _TEAL

    for idx, it in enumerate(items, start=1):
        res = it.get("result") or {}
        if it.get("status") != "ok":
            ws0.append([idx, it.get("name"), it.get("module_name") or it.get("module"), "Error", it.get("error"), ""])
            continue
        metrics = "; ".join(f"{m['label']}: {m['value']}" for m in (res.get("summary") or [])[:4])
        ws0.append([idx, it.get("name"), it.get("module_name") or it.get("module"), "Sukses", metrics, res.get("interpretation", "")])

        ws = wb.create_sheet(_safe_title(f"{idx}_{it.get('name', 'Kasus')}", used))
        ws.append([f"{it.get('name')} ({it.get('module_name') or it.get('module')})"])
        ws.cell(1, 1).font = Font(bold=True, size=13, color="0F5257")
        if res.get("interpretation"):
            ws.append([res["interpretation"]])
        ws.append([])

        if res.get("summary"):
            ws.append(["Metrik Utama", "Nilai", "Satuan"])
            for col in range(1, 4):
                ws.cell(ws.max_row, col).font = _BOLD
                ws.cell(ws.max_row, col).fill = _SOFT
            for m in res["summary"]:
                ws.append([m["label"], m["value"], m.get("unit", "")])
            ws.append([])

        for tbl in res.get("tables") or []:
            ws.append([tbl["title"]])
            ws.cell(ws.max_row, 1).font = Font(bold=True, color="0F5257")
            ws.append(tbl["columns"])
            for col in range(1, len(tbl["columns"]) + 1):
                c = ws.cell(ws.max_row, col)
                c.font, c.fill = _BOLD_WHITE, _TEAL
            for row in tbl["rows"]:
                ws.append(row)
            ws.append([])
        _autofit(ws)

    _autofit(ws0)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def export_pdf(workspace_name: str, items: list[dict[str, Any]]) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=28, rightMargin=28, topMargin=28, bottomMargin=28)
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("H1", parent=styles["Heading1"], textColor=colors.HexColor("#0F5257"), fontSize=16, spaceAfter=8)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], textColor=colors.HexColor("#0F5257"), fontSize=12, spaceBefore=10, spaceAfter=4)
    h3 = ParagraphStyle("H3", parent=styles["Heading3"], fontSize=10, spaceBefore=6, spaceAfter=3)
    body = ParagraphStyle("Body", parent=styles["Normal"], fontSize=9, leading=12)

    story = [
        Paragraph(f"OptiQM Studio — Laporan Hasil Analisis ({workspace_name})", h1),
        Paragraph(f"Total modul dijalankan: {len(items)}", body),
        Spacer(1, 8),
    ]

    # Tabel ringkasan eksekutif
    sum_data = [["#", "Kasus", "Modul", "Status", "Metrik Utama"]]
    for idx, it in enumerate(items, start=1):
        res = it.get("result") or {}
        if it.get("status") == "ok":
            top_m = "; ".join(f"{m['label']}={m['value']}" for m in (res.get("summary") or [])[:3])
            sum_data.append([str(idx), str(it.get("name")), str(it.get("module_name") or it.get("module")), "Sukses", top_m[:95]])
        else:
            sum_data.append([str(idx), str(it.get("name")), str(it.get("module")), "Error", str(it.get("error"))[:95]])
    story.append(_styled_table(sum_data, col_widths=[25, 130, 140, 55, 410]))

    for idx, it in enumerate(items, start=1):
        res = it.get("result") or {}
        story.append(Paragraph(f"{idx}. {it.get('name')} — {it.get('module_name') or it.get('module')}", h2))
        if it.get("status") != "ok":
            story.append(Paragraph(f"Error: {it.get('error')}", body))
            continue
        if res.get("interpretation"):
            story.append(Paragraph(res["interpretation"], body))
        if res.get("summary"):
            story.append(Paragraph("Metrik Kunci", h3))
            m_rows = [["Metrik", "Nilai"]] + [[str(m["label"]), f"{m['value']} {m.get('unit', '')}".strip()] for m in res["summary"]]
            story.append(_styled_table(m_rows, col_widths=[240, 220]))
        for tbl in (res.get("tables") or [])[:4]:
            story.append(Paragraph(tbl["title"], h3))
            cols = [str(c) for c in tbl["columns"][:10]]
            rows = [[_fmt_cell(v) for v in row[:10]] for row in tbl["rows"][:25]]
            story.append(_styled_table([cols, *rows]))
    doc.build(story)
    return buf.getvalue()


def _fmt_cell(v: Any) -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:,.4g}"
    return str(v)[:40]


def _styled_table(data: list[list[str]], col_widths=None) -> RLTable:
    t = RLTable(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F5257")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F7F6")]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D0D7D5")),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def _autofit(ws) -> None:
    for col in range(1, ws.max_column + 1):
        max_len = max((len(str(ws.cell(r, col).value or "")) for r in range(1, ws.max_row + 1)), default=10)
        ws.column_dimensions[get_column_letter(col)].width = min(45, max(12, max_len + 3))
        for r in range(1, ws.max_row + 1):
            ws.cell(r, col).alignment = Alignment(vertical="center")
