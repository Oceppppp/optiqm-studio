"""Helper konversi & validasi data tabel yang dipakai bersama oleh modul."""

from __future__ import annotations

from typing import Any, Iterable

import numpy as np
import pandas as pd

from .errors import InputError
from .sheet import ParamSpec

_TRUE = {"1", "true", "yes", "ya", "y", "t"}


def to_float(value: Any, what: str = "nilai", allow_inf: bool = False) -> float:
    """Konversi ke float; mendukung koma desimal ('1,5'), pemisah ribuan ('1,200.50' / '1.200,50'), dan persen ('10%')."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        raise InputError(f"{what} kosong.")
    if isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(value, bool):
        f = float(value)
        if np.isnan(f) or (not allow_inf and np.isinf(f)):
            raise InputError(f"{what} '{value}' bukan angka berhingga yang valid.")
        return f
    s = str(value).strip().replace(" ", "")
    pct = s.endswith("%")
    if pct:
        s = s[:-1]
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif s.count(",") == 1 and s.count(".") == 0:
        s = s.replace(",", ".")
    elif s.count(",") > 1 and s.count(".") == 0:
        s = s.replace(",", "")
    try:
        f = float(s)
    except ValueError as exc:
        raise InputError(f"{what} '{value}' bukan angka.") from exc
    if np.isnan(f) or (not allow_inf and np.isinf(f)):
        raise InputError(f"{what} '{value}' bukan angka berhingga yang valid.")
    return f / 100 if pct else f


def to_float_or_none(value: Any) -> float | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return to_float(value)


def coerce_param(spec: ParamSpec, value: Any) -> Any:
    """Konversi nilai parameter sesuai ``spec.type``."""
    if value is None or (isinstance(value, str) and not value.strip()):
        if spec.required:
            raise InputError(f"Parameter '{spec.label}' wajib diisi.")
        return spec.default
    if spec.type == "number":
        return to_float(value, spec.label)
    if spec.type == "integer":
        return int(round(to_float(value, spec.label)))
    if spec.type == "boolean":
        return value if isinstance(value, bool) else str(value).strip().lower() in _TRUE
    if spec.type == "choice":
        s = str(value).strip().lower()
        for c in spec.choices:
            if c.lower() == s:
                return c
        raise InputError(f"Parameter '{spec.label}' harus salah satu dari: {', '.join(spec.choices)}.")
    return str(value).strip()


def clean_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Buang baris/kolom yang seluruhnya kosong dan rapikan nama kolom."""
    df = df.replace(r"^\s*$", np.nan, regex=True)
    df = df.dropna(how="all").dropna(axis=1, how="all")
    df.columns = [str(c).strip() for c in df.columns]
    return df.reset_index(drop=True)


def numeric_matrix(df: pd.DataFrame, what: str = "tabel") -> np.ndarray:
    """Konversi seluruh isi DataFrame menjadi matriks float."""
    out = np.empty(df.shape, dtype=float)
    for i in range(df.shape[0]):
        for j in range(df.shape[1]):
            out[i, j] = to_float(df.iat[i, j], f"{what} baris {i + 1} kolom '{df.columns[j]}'")
    return out


def numeric_column(df: pd.DataFrame, col: str, what: str | None = None,
                   allow_blank: bool = False) -> list[float | None]:
    if col not in df.columns:
        raise InputError(f"Kolom '{col}' tidak ditemukan. Kolom tersedia: {', '.join(map(str, df.columns))}.")
    vals: list[float | None] = []
    for i, v in enumerate(df[col].tolist()):
        if allow_blank:
            vals.append(to_float_or_none(v))
        else:
            vals.append(to_float(v, f"{what or col} baris {i + 1}"))
    return vals


def find_column(df: pd.DataFrame, candidates: Iterable[str], required: bool = True) -> str | None:
    """Cari nama kolom secara case-insensitive dari beberapa kandidat sinonim."""
    norm = {str(c).strip().lower().replace(" ", "").replace("_", ""): c for c in df.columns}
    for cand in candidates:
        key = cand.lower().replace(" ", "").replace("_", "")
        if key in norm:
            return norm[key]
    if required:
        raise InputError(
            f"Kolom wajib tidak ditemukan (salah satu dari: {', '.join(candidates)}). "
            f"Kolom tersedia: {', '.join(map(str, df.columns))}."
        )
    return None


def require_rows(df: pd.DataFrame, n: int = 1, what: str = "tabel") -> None:
    if len(df) < n:
        raise InputError(f"{what} minimal harus memiliki {n} baris data.")
