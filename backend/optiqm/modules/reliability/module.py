"""Modul Reliability (Keandalan sistem seri & paralel)."""

from __future__ import annotations

import math

import pandas as pd

from optiqm.core import BaseModule, InputError, ModuleResult, SheetData, register
from optiqm.core.parsing import clean_frame, find_column, require_rows, to_float


@register
class Reliability(BaseModule):
    key = "reliability"
    name = "Reliability (Keandalan Sistem)"
    category = "Kualitas & Keandalan"
    description = "Menghitung keandalan total sistem dengan konfigurasi seri (tahapan) dan paralel (redundansi)."
    sheet_prefixes = ("REL", "RELIABILITY", "KEANDALAN")
    table_hint = ("Setiap baris = satu komponen/tahap. Kolom: Stage (tahap seri yang sama digabung paralel), "
                  "Component, Reliability (0..1), Parallel_Units (opsional, default 1).")

    def template(self) -> SheetData:
        # Contoh klasik Heizer & Render: Stage 1 (R=0.90), Stage 2 (2 paralel @ 0.80 -> 0.96), Stage 3 (R=0.99)
        df = pd.DataFrame(
            [["Tahap 1", "Sensor Utama", 0.90, 1],
             ["Tahap 2", "Prosesor A", 0.80, 1],
             ["Tahap 2", "Prosesor Backup", 0.80, 1],
             ["Tahap 3", "Aktuator", 0.99, 1]],
            columns=["Stage", "Component", "Reliability", "Parallel_Units"],
        )
        return SheetData(tables={"main": df})

    def solve(self, data: SheetData) -> ModuleResult:
        df = clean_frame(data.table("main"))
        require_rows(df, 1, "Tabel komponen keandalan")
        c_stg = find_column(df, ["Stage", "Tahap", "System"], required=False)
        c_cmp = find_column(df, ["Component", "Komponen", "Name"], required=False) or df.columns[0]
        c_rel = find_column(df, ["Reliability", "R", "Keandalan"])
        c_par = find_column(df, ["Parallel_Units", "Parallel", "Count", "Units", "Jumlah"], required=False)

        stages: dict[str, list[tuple[str, float]]] = {}
        for i in range(len(df)):
            stg = str(df.at[i, c_stg]).strip() if c_stg else f"Stage_{i + 1}"
            cmp_name = str(df.at[i, c_cmp]).strip()
            rel = to_float(df.at[i, c_rel], f"Reliability {cmp_name}")
            rel = rel / 100.0 if rel > 1.0 else rel
            if not (0.0 <= rel <= 1.0):
                raise InputError(f"Keandalan '{cmp_name}' harus antara 0 dan 1.")
            cnt = int(round(to_float(df.at[i, c_par]))) if c_par and not pd.isna(df.at[i, c_par]) else 1
            for k in range(max(1, cnt)):
                stages.setdefault(stg, []).append((cmp_name if cnt == 1 else f"{cmp_name} #{k+1}", rel))

        stage_rows = []
        sys_rel = 1.0
        for stg, comps in stages.items():
            # Dalam 1 tahap, komponen tersusun paralel: R_stage = 1 - prod(1 - R_i)
            r_stg = 1.0 - math.prod(1.0 - rv for _, rv in comps)
            sys_rel *= r_stg
            stage_rows.append([stg, len(comps), "Paralel" if len(comps) > 1 else "Tunggal",
                               ", ".join(f"{n} ({rv:.3f})" for n, rv in comps), r_stg])

        r = ModuleResult()
        r.metric("Keandalan Sistem Total (Rs)", sys_rel, highlight=True)
        r.metric("Keandalan (%)", f"{sys_rel * 100:.4f}%", highlight=True)
        r.metric("Probabilitas Kegagalan (1 - Rs)", f"{(1 - sys_rel) * 100:.4f}%")
        r.table("Keandalan per Tahap (Seri)", ["Tahap", "Jumlah Unit", "Susunan", "Komponen", "Keandalan Tahap"], stage_rows)
        r.chart("Keandalan per Tahap", "bar", {
            "x": [row[0] for row in stage_rows],
            "series": [{"name": "Keandalan", "data": [row[4] for row in stage_rows]}],
            "x_label": "Tahap", "y_label": "Reliability",
        })
        r.interpretation = f"Keandalan sistem total (seri dari {len(stages)} tahap) adalah {sys_rel:.6f} ({sys_rel*100:.2f}%)."
        return r
