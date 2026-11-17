"""Representasi data input yang netral terhadap format file.

Semua sumber input (Excel, CSV, JSON, Google Sheets, editor grid di UI)
dikonversi menjadi :class:`SheetData`. Modul solver hanya mengenal
``SheetData`` sehingga tidak bergantung pada format file apa pun.

Konvensi tata letak sheet (lihat ``docs/FILE_FORMAT.md``)::

    [params]                <- opsional: blok parameter key | value
    module   | transportation
    objective| min

    [main]                  <- tabel utama (header di baris berikutnya)
    Source | D1 | D2 | Supply
    S1     | 4  | 6  | 100

    [probabilities]         <- tabel tambahan opsional (bernama)
    ...

Jika sheet tidak memiliki penanda ``[...]`` sama sekali, seluruh sheet
dianggap sebagai tabel ``main`` dengan baris non-kosong pertama sebagai header.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import pandas as pd

ParamType = Literal["number", "integer", "text", "choice", "boolean"]


@dataclass(frozen=True)
class ParamSpec:
    """Deskripsi parameter skalar sebuah modul (dipakai UI untuk membuat form)."""

    name: str
    label: str
    type: ParamType = "number"
    default: Any = None
    choices: tuple[str, ...] = ()
    help: str = ""
    required: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "type": self.type,
            "default": self.default,
            "choices": list(self.choices),
            "help": self.help,
            "required": self.required,
        }


@dataclass
class SheetData:
    """Satu kasus/soal: parameter skalar + satu atau lebih tabel."""

    params: dict[str, Any] = field(default_factory=dict)
    tables: dict[str, pd.DataFrame] = field(default_factory=dict)

    # ------------------------------------------------------------------ access
    def table(self, name: str = "main", required: bool = True) -> pd.DataFrame | None:
        from .errors import InputError

        if name in self.tables:
            return self.tables[name]
        if required:
            raise InputError(f"Tabel '[{name}]' tidak ditemukan pada data input.")
        return None

    def param(self, name: str, default: Any = None) -> Any:
        """Ambil parameter (case-insensitive, spasi/underscore diabaikan)."""
        key = _norm(name)
        for k, v in self.params.items():
            if _norm(k) == key:
                return default if v is None or (isinstance(v, str) and not v.strip()) else v
        return default

    # ----------------------------------------------------------- serialization
    def to_dict(self) -> dict[str, Any]:
        return {
            "params": {k: _jsonable(v) for k, v in self.params.items()},
            "tables": {
                name: {
                    "columns": [str(c) for c in df.columns],
                    "rows": [[_jsonable(v) for v in row] for row in df.itertuples(index=False)],
                }
                for name, df in self.tables.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SheetData":
        tables = {}
        for name, t in (data.get("tables") or {}).items():
            cols = [str(c) for c in t.get("columns", [])]
            rows = [list(r) + [None] * (len(cols) - len(r)) for r in t.get("rows", [])]
            tables[name] = pd.DataFrame([r[: len(cols)] for r in rows], columns=cols)
        return cls(params=dict(data.get("params") or {}), tables=tables)

    def to_grid(self) -> list[list[Any]]:
        """Serialisasi ke grid 2D (untuk ditulis ke Excel/CSV template)."""
        grid: list[list[Any]] = []
        if self.params:
            grid.append(["[params]"])
            grid.extend([[k, _jsonable(v)] for k, v in self.params.items()])
            grid.append([])
        for name, df in self.tables.items():
            grid.append([f"[{name}]"])
            grid.append([str(c) for c in df.columns])
            grid.extend([[_jsonable(v) for v in row] for row in df.itertuples(index=False)])
            grid.append([])
        return grid


def _norm(s: str) -> str:
    return str(s).strip().lower().replace(" ", "").replace("_", "").replace("-", "")


def _jsonable(v: Any) -> Any:
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(v, "item"):  # numpy scalar
        return v.item()
    return v
