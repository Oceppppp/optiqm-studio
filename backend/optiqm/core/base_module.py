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

    def resolved_params_with_table(
        self, data: SheetData, aliases: dict[str, str] | None = None
    ) -> dict[str, Any]:
        """Seperti ``resolved_params``, dengan fallback membaca tabel ``[main]`` (Parameter | Value)
        bila parameter belum diisi secara eksplisit di ``data.params``."""
        from .parsing import coerce_param
        from .sheet import _norm

        explicit = {
            _norm(k)
            for k, v in data.params.items()
            if v is not None and not (isinstance(v, str) and not v.strip())
        }
        table_vals: dict[str, Any] = {}
        df = data.table("main", required=False)
        if df is not None and len(df.columns) >= 2:
            alias_map = {_norm(k): _norm(v) for k, v in (aliases or {}).items()}
            for _, row in df.iterrows():
                rk, rv = row.iloc[0], row.iloc[1]
                if rk is None or (isinstance(rk, float) and rk != rk):
                    continue
                if rv is None or (isinstance(rv, float) and rv != rv):
                    continue
                if isinstance(rv, str) and not rv.strip():
                    continue
                nk = alias_map.get(_norm(str(rk)), _norm(str(rk)))
                table_vals[nk] = rv

        out: dict[str, Any] = {}
        for spec in self.params:
            nk = _norm(spec.name)
            if nk in explicit:
                raw = data.param(spec.name, spec.default)
            elif nk in table_vals:
                raw = table_vals[nk]
            else:
                raw = spec.default
            out[spec.name] = coerce_param(spec, raw)
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
