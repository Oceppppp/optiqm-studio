"""Kontrak (interface) yang wajib diikuti setiap modul solver."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from .result import ModuleResult
from .sheet import ParamSpec, SheetData


class BaseModule(ABC):
    """Basis semua modul.

    Subclass cukup mendefinisikan metadata + tiga method:

    * :meth:`template` - contoh data (dipakai untuk file template & data awal di UI)
    * :meth:`solve`    - membaca ``SheetData`` lalu menghasilkan ``ModuleResult``

    Modul didaftarkan ke registry dengan dekorator ``@register``.
    """

    key: ClassVar[str]                     # id unik, mis. "transportation"
    name: ClassVar[str]                    # nama tampilan
    category: ClassVar[str]                # kategori menu, mis. "Distribusi"
    description: ClassVar[str] = ""
    sheet_prefixes: ClassVar[tuple[str, ...]] = ()   # prefix nama sheet utk auto-detect
    params: ClassVar[tuple[ParamSpec, ...]] = ()      # parameter skalar
    table_hint: ClassVar[str] = ""          # penjelasan format tabel utk pengguna

    @abstractmethod
    def template(self) -> SheetData:
        """Contoh data input yang valid (soal contoh)."""

    @abstractmethod
    def solve(self, data: SheetData) -> ModuleResult:
        """Selesaikan kasus. Lempar ``InputError``/``SolverError`` bila gagal."""

    # ------------------------------------------------------------------ helpers
    def resolved_params(self, data: SheetData) -> dict[str, Any]:
        """Gabungkan parameter input dengan default dari ``params`` + konversi tipe."""
        from .parsing import coerce_param

        out: dict[str, Any] = {}
        for spec in self.params:
            out[spec.name] = coerce_param(spec, data.param(spec.name, spec.default))
        return out

    def metadata(self) -> dict[str, Any]:
        tpl = self.template()
        tpl.params.setdefault("module", self.key)
        return {
            "key": self.key,
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "sheet_prefixes": list(self.sheet_prefixes),
            "params": [p.to_dict() for p in self.params],
            "table_hint": self.table_hint,
            "template": tpl.to_dict(),
        }
