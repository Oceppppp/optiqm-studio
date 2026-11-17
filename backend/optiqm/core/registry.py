"""Registry plugin modul dengan auto-discovery.

Setiap sub-package di ``optiqm.modules`` cukup mengimpor ``register`` dan
mendekorasi kelas modulnya. ``discover()`` mengimpor semua sub-package
sehingga modul baru otomatis muncul tanpa mengubah kode lain.
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
from typing import TypeVar

from .base_module import BaseModule
from .errors import ModuleNotFound

log = logging.getLogger(__name__)

_REGISTRY: dict[str, BaseModule] = {}
_DISCOVERED = False

T = TypeVar("T", bound=type[BaseModule])


def register(cls: T) -> T:
    """Dekorator: daftarkan kelas modul (instance tunggal) ke registry."""
    if not getattr(cls, "key", None):
        raise ValueError(f"{cls.__name__} wajib mendefinisikan atribut 'key'.")
    if cls.key in _REGISTRY:
        raise ValueError(f"Modul dengan key '{cls.key}' sudah terdaftar.")
    _REGISTRY[cls.key] = cls()
    return cls


def discover() -> None:
    """Impor semua sub-package ``optiqm.modules`` (idempoten)."""
    global _DISCOVERED
    if _DISCOVERED:
        return
    import optiqm.modules as pkg

    for info in pkgutil.iter_modules(pkg.__path__):
        if info.name.startswith("_"):
            continue
        try:
            importlib.import_module(f"{pkg.__name__}.{info.name}")
        except Exception:  # pragma: no cover - modul rusak jangan matikan app
            log.exception("Gagal memuat modul '%s'", info.name)
    _DISCOVERED = True


def get(key: str) -> BaseModule:
    discover()
    try:
        return _REGISTRY[key]
    except KeyError as exc:
        raise ModuleNotFound(f"Modul '{key}' tidak dikenal.") from exc


def all_modules() -> list[BaseModule]:
    discover()
    return sorted(_REGISTRY.values(), key=lambda m: (m.category, m.name))
