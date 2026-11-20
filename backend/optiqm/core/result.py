"""Format hasil standar untuk SEMUA modul.

Karena seragam, frontend dan generator laporan cukup memiliki satu
komponen generik untuk menampilkan hasil modul apa pun.

Jenis chart (``Chart.kind``) dan bentuk ``data``-nya:

* ``line`` / ``bar`` / ``area``::

      {"x": [..label/angka..], "series": [{"name": str, "data": [num|None,...]}],
       "x_label": str, "y_label": str}

* ``scatter``::

      {"series": [{"name": str, "points": [[x, y], ...]}], "x_label", "y_label"}

* ``lp_region`` (grafik LP 2 variabel)::

      {"lines": [{"name": str, "points": [[x1,y1],[x2,y2]]}],
       "polygon": [[x, y], ...],          # daerah feasible (urut)
       "optimum": [x, y] | None, "x_label": str, "y_label": str}

* ``network`` (graf / diagram jaringan)::

      {"nodes": [{"id": str, "label": str, "highlight": bool}],
       "edges": [{"source": str, "target": str, "label": str, "highlight": bool}],
       "directed": bool}

* ``gantt``::

      {"tasks": [{"name": str, "start": num, "end": num, "highlight": bool}]}
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import math

ChartKind = Literal["line", "bar", "area", "scatter", "lp_region", "network", "gantt"]


def clean(v: Any) -> Any:
    """Konversi nilai numpy/NaN/inf menjadi tipe JSON-friendly."""
    if v is None:
        return None
    if hasattr(v, "item") and not isinstance(v, (list, dict)):
        try:
            v = v.item()
        except (ValueError, AttributeError):
            pass
    if isinstance(v, float):
        if math.isnan(v):
            return None
        if math.isinf(v):
            return "∞" if v > 0 else "-∞"
        return round(v, 6)
    if isinstance(v, (list, tuple)):
        return [clean(x) for x in v]
    if isinstance(v, dict):
        return {str(k): clean(x) for k, x in v.items()}
    return v


@dataclass
class Metric:
    label: str
    value: Any
    unit: str = ""
    highlight: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"label": self.label, "value": clean(self.value), "unit": self.unit,
                "highlight": self.highlight}


@dataclass
class Table:
    title: str
    columns: list[str]
    rows: list[list[Any]]
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"title": self.title, "columns": [str(c) for c in self.columns],
                "rows": [clean(list(r)) for r in self.rows], "note": self.note}

    @classmethod
    def from_frame(cls, title: str, df, index: bool = True, note: str = "") -> "Table":
        """Buat Table dari pandas DataFrame."""
        if index:
            df = df.reset_index()
        return cls(title=title, columns=[str(c) for c in df.columns],
                   rows=df.values.tolist(), note=note)


@dataclass
class Chart:
    title: str
    kind: ChartKind
    data: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"title": self.title, "kind": self.kind, "data": clean(self.data)}


@dataclass
class AnalysisSection:
    """Satu blok analisis mendalam (metodologi, bedah hasil, atau rekomendasi)."""

    title: str
    content: str = ""
    bullets: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "content": self.content,
            "bullets": list(self.bullets),
        }


@dataclass
class ModuleResult:
    """Hasil penyelesaian satu kasus."""

    summary: list[Metric] = field(default_factory=list)
    tables: list[Table] = field(default_factory=list)
    charts: list[Chart] = field(default_factory=list)
    steps: list[Table] = field(default_factory=list)   # langkah/iterasi (mis. tabel simplex)
    warnings: list[str] = field(default_factory=list)
    interpretation: str = ""                            # ringkasan naratif hasil
    analysis: list[AnalysisSection] = field(default_factory=list)  # analisis mendalam terstruktur

    # helper builder -------------------------------------------------------
    def metric(self, label: str, value: Any, unit: str = "", highlight: bool = False) -> "ModuleResult":
        self.summary.append(Metric(label, value, unit, highlight))
        return self

    def table(self, title: str, columns: list[str], rows: list[list[Any]], note: str = "") -> "ModuleResult":
        self.tables.append(Table(title, columns, rows, note))
        return self

    def chart(self, title: str, kind: ChartKind, data: dict[str, Any]) -> "ModuleResult":
        self.charts.append(Chart(title, kind, data))
        return self

    def analyze(self, title: str, content: str = "", bullets: list[str] | None = None) -> "ModuleResult":
        self.analysis.append(AnalysisSection(title=title, content=content, bullets=list(bullets or [])))
        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": [m.to_dict() for m in self.summary],
            "tables": [t.to_dict() for t in self.tables],
            "charts": [c.to_dict() for c in self.charts],
            "steps": [t.to_dict() for t in self.steps],
            "warnings": list(self.warnings),
            "interpretation": self.interpretation,
            "analysis": [a.to_dict() for a in self.analysis],
        }
