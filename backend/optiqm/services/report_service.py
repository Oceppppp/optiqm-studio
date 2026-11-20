"""Generator laporan gabungan Excel (.xlsx) dan PDF untuk semua hasil batch."""

from __future__ import annotations

import io
from typing import Any
from xml.sax.saxutils import escape as _xml_escape

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
_ANALYSIS_BG = PatternFill("solid", fgColor="F6F9F8")
_BOLD_WHITE = Font(bold=True, color="FFFFFF")
_BOLD = Font(bold=True)
_BOLD_TEAL = Font(bold=True, color="0F5257")

_PDF_GLYPH_MAP = str.maketrans({
    "≤": "<=", "≥": ">=", "→": "->", "←": "<-", "−": "-", "×": "x",
    "σ": "sigma", "μ": "mu", "λ": "lambda", "α": "alpha", "β": "beta",
    "ρ": "rho", "π": "pi", "Δ": "Delta", "θ": "theta", "Φ": "Phi",
    "Σ": "Sum", "∏": "Prod", "√": "sqrt", "∞": "inf", "≈": "~", "≡": "=",
    "·": "*", "⁻": "-", "⁺": "+", "¹": "^1", "₁": "1", "₂": "2",
    "⌈": "ceil(", "⌉": ")", "\u0304": "", "\u0302": "",
})


def _pdf_text(val: Any) -> str:
    """Escape karakter XML dan transliterasi simbol matematika agar aman di ReportLab Helvetica."""
    s = str(val if val is not None else "").translate(_PDF_GLYPH_MAP)
    return _xml_escape(s)


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

        if res.get("analysis"):
            ws.append(["Analisis Mendalam"])
            ws.cell(ws.max_row, 1).font = _BOLD_WHITE
            ws.cell(ws.max_row, 1).fill = _TEAL
            for sec in res["analysis"]:
                ws.append([sec.get("title", "")])
                ws.cell(ws.max_row, 1).font = _BOLD_TEAL
                ws.cell(ws.max_row, 1).fill = _ANALYSIS_BG
                if sec.get("content"):
                    ws.append([sec["content"]])
                for b in sec.get("bullets") or []:
                    ws.append([f"• {b}"])
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
    h4 = ParagraphStyle("H4", parent=styles["Heading4"], textColor=colors.HexColor("#0F5257"), fontSize=9.2, spaceBefore=4, spaceAfter=2)
    body = ParagraphStyle("Body", parent=styles["Normal"], fontSize=9, leading=12)
    bullet_style = ParagraphStyle("Bullet", parent=body, leftIndent=12, spaceAfter=1.5)

    story = [
        Paragraph(_pdf_text(f"OptiQM Studio — Laporan Hasil Analisis ({workspace_name})"), h1),
        Paragraph(_pdf_text(f"Total modul dijalankan: {len(items)}"), body),
        Spacer(1, 8),
    ]

    # Tabel ringkasan eksekutif
    sum_data = [["#", "Kasus", "Modul", "Status", "Metrik Utama"]]
    for idx, it in enumerate(items, start=1):
        res = it.get("result") or {}
        if it.get("status") == "ok":
            top_m = "; ".join(f"{m['label']}={m['value']}" for m in (res.get("summary") or [])[:3])
            sum_data.append([str(idx), _fmt_cell(it.get("name")), _fmt_cell(it.get("module_name") or it.get("module")), "Sukses", _fmt_cell(top_m, 95)])
        else:
            sum_data.append([str(idx), _fmt_cell(it.get("name")), _fmt_cell(it.get("module")), "Error", _fmt_cell(it.get("error"), 95)])
    story.append(_styled_table(sum_data, col_widths=[25, 130, 140, 55, 410]))

    for idx, it in enumerate(items, start=1):
        res = it.get("result") or {}
        story.append(Paragraph(_pdf_text(f"{idx}. {it.get('name')} — {it.get('module_name') or it.get('module')}"), h2))
        if it.get("status") != "ok":
            story.append(Paragraph(_pdf_text(f"Error: {it.get('error')}"), body))
            continue
        if res.get("interpretation"):
            story.append(Paragraph(_pdf_text(res["interpretation"]), body))
        if res.get("summary"):
            story.append(Paragraph("Metrik Kunci", h3))
            m_rows = [["Metrik", "Nilai"]] + [[_fmt_cell(m["label"], 60), _fmt_cell(f"{m['value']} {m.get('unit', '')}".strip(), 60)] for m in res["summary"]]
            story.append(_styled_table(m_rows, col_widths=[240, 220]))
        if res.get("analysis"):
            story.append(Paragraph("Analisis Mendalam", h3))
            for sec in res["analysis"]:
                story.append(Paragraph(_pdf_text(sec.get("title", "")), h4))
                if sec.get("content"):
                    story.append(Paragraph(_pdf_text(sec["content"]), body))
                for b in sec.get("bullets") or []:
                    story.append(Paragraph(f"&bull; {_pdf_text(b)}", bullet_style))
        for tbl in (res.get("tables") or [])[:4]:
            cols = [_fmt_cell(c, 35) for c in (tbl.get("columns") or [])[:10]]
            if not cols:
                continue
            story.append(Paragraph(_pdf_text(tbl["title"]), h3))
            rows = [[_fmt_cell(v) for v in row[:10]] for row in (tbl.get("rows") or [])[:25]]
            story.append(_styled_table([cols, *rows]))
    doc.build(story)
    return buf.getvalue()


def _fmt_cell(v: Any, limit: int = 40) -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:,.4g}"
    return str(v).translate(_PDF_GLYPH_MAP)[:limit]


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
        ws.column_dimensions[get_column_letter(col)].width = min(55, max(12, max_len + 3))
        for r in range(1, ws.max_row + 1):
            val = ws.cell(r, col).value
            wrap = isinstance(val, str) and len(val) > 55
            ws.cell(r, col).alignment = Alignment(vertical="center", wrap_text=wrap)
