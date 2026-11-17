"""Modul Work Measurement (Time Study & Sample Size)."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy.stats import norm

from optiqm.core import BaseModule, InputError, ModuleResult, ParamSpec, SheetData, register
from optiqm.core.parsing import clean_frame, find_column, require_rows, to_float


@register
class WorkMeasurement(BaseModule):
    key = "work_measurement"
    name = "Work Measurement (Time Study)"
    category = "Produktivitas & Kerja"
    description = "Menghitung waktu normal, waktu standar (standard time), dan ukuran sampel kerja yang dibutuhkan."
    sheet_prefixes = ("WM", "TIMESTUDY", "KERJA")
    params = (
        ParamSpec("allowance", "Faktor Kelonggaran / Allowance (%, mis. 15)", "number", 15.0),
        ParamSpec("confidence", "Tingkat Kepercayaan Sampel (%)", "number", 95.0),
        ParamSpec("accuracy", "Batas Kesalahan Relatif h (%, mis. 5)", "number", 5.0),
    )
    table_hint = "Kolom: Element (elemen kerja), Rating (%, mis. 100), diikuti kolom observasi Obs_1..Obs_k."

    def template(self) -> SheetData:
        # Contoh klasik 3 elemen kerja (Heizer & Render)
        df = pd.DataFrame(
            [["Ambil Komponen", 110, 0.5, 0.48, 0.52, 0.50, 0.50],
             ["Pasang & Baut", 95, 1.2, 1.1, 1.3, 1.2, 1.2],
             ["Inspeksi & Simpan", 100, 0.4, 0.42, 0.38, 0.40, 0.40]],
            columns=["Element", "Rating", "Obs_1", "Obs_2", "Obs_3", "Obs_4", "Obs_5"],
        )
        return SheetData(params={"allowance": 15, "confidence": 95, "accuracy": 5}, tables={"main": df})

    def solve(self, data: SheetData) -> ModuleResult:
        p = self.resolved_params(data)
        allow = float(p["allowance"])
        allow = allow / 100.0 if allow >= 1.0 else allow
        conf = float(p["confidence"])
        conf = conf / 100.0 if conf > 1.0 else conf
        acc = float(p["accuracy"])
        acc = acc / 100.0 if acc >= 1.0 else acc
        if not (0.0 <= allow < 1.0):
            raise InputError("Allowance harus < 100%.")

        df = clean_frame(data.table("main"))
        require_rows(df, 1, "Tabel elemen kerja")
        c_el = find_column(df, ["Element", "Elemen", "Task", "Name"], required=False) or df.columns[0]
        c_rat = find_column(df, ["Rating", "Performance", "PRF"], required=False)
        obs_cols = [c for c in df.columns if c not in (c_el, c_rat)]
        if not obs_cols:
            raise InputError("Minimal harus ada 1 kolom observasi waktu.")

        z = float(norm.ppf(1.0 - (1.0 - conf) / 2.0))
        rows_out = []
        tot_normal = 0.0
        max_req_n = 0
        for i in range(len(df)):
            nm = str(df.at[i, c_el]).strip()
            rat = to_float(df.at[i, c_rat], f"Rating {nm}") if c_rat else 100.0
            rat_f = rat / 100.0 if rat > 3.0 else rat
            obs = [to_float(df.at[i, c], f"{nm}/{c}") for c in obs_cols if not pd.isna(df.at[i, c])]
            if not obs:
                raise InputError(f"Elemen '{nm}' tidak memiliki data observasi.")
            mean_t = float(np.mean(obs))
            std_t = float(np.std(obs, ddof=1)) if len(obs) > 1 else 0.0
            norm_t = mean_t * rat_f
            req_n = math.ceil((z * std_t / (acc * mean_t)) ** 2) if (mean_t > 0 and acc > 0) else 1
            tot_normal += norm_t
            max_req_n = max(max_req_n, req_n)
            rows_out.append([nm, len(obs), mean_t, std_t, rat_f * 100, norm_t, req_n])

        std_time = tot_normal / (1.0 - allow)
        r = ModuleResult()
        r.metric("Total Waktu Normal", tot_normal, highlight=True)
        r.metric("Waktu Standar (Standard Time)", std_time, highlight=True)
        r.metric("Sampel Minimum Dibutuhkan", max_req_n)
        r.table("Analisis Elemen Kerja",
                ["Elemen", "n Obs", "Rata-rata Observasi", "Std. Dev", "Rating (%)", "Waktu Normal", "Sampel Min"],
                rows_out)
        r.interpretation = f"Waktu normal total = {tot_normal:.4f}; dengan allowance {allow*100:.1f}%, waktu standar = {std_time:.4f}."
        return r
