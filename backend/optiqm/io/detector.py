"""Deteksi otomatis modul untuk sebuah kasus.

Urutan prioritas:
1. Parameter ``module`` di blok ``[params]`` (key atau nama modul).
2. Prefix nama sheet/file, mis. ``TRANS_Gudang`` -> transportation.
3. Nama sheet mengandung key/nama modul.
"""

from __future__ import annotations

import re

from optiqm.core import all_modules


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def detect_module(case_name: str, module_param: object | None = None) -> str | None:
    modules = all_modules()
    if module_param:
        target = _norm(str(module_param))
        for m in modules:
            if target in {_norm(m.key), _norm(m.name)} or target in {_norm(p) for p in m.sheet_prefixes}:
                return m.key

    head = re.split(r"[\s_\-.]+", case_name.strip())[0].upper() if case_name.strip() else ""
    for m in modules:
        if head and head in {p.upper() for p in m.sheet_prefixes}:
            return m.key

    name = _norm(case_name)
    best = None
    for m in modules:
        for cand in (_norm(m.key), _norm(m.name)):
            if cand and cand in name and (best is None or len(cand) > best[0]):
                best = (len(cand), m.key)
    return best[1] if best else None
