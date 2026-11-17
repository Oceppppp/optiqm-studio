"""Modul Cost-Volume Analysis (perbandingan beberapa alternatif proses/mesin)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from optiqm.core import BaseModule, ModuleResult, ParamSpec, SheetData, register
from optiqm.core.parsing import clean_frame, find_column, require_rows, to_float


@register
class CostVolume(BaseModule):
    key = "cost_volume"
    name = "Cost-Volume Analysis"
    category = "Biaya & Keuangan"
    description = "Membandingkan biaya total beberapa alternatif proses/mesin dan mencari titik potong (crossover)."
    sheet_prefixes = ("CVA", "COSTVOL")
    params = (ParamSpec("volume", "Volume Rencana", "number", 2500.0),)
    table_hint = "Kolom: Alternative, Fixed_Cost, Variable_Cost."

    def template(self) -> SheetData:
        df = pd.DataFrame(
            [["Mesin Manual", 20000, 14], ["Mesin Semi-Otomatis", 50000, 6], ["Mesin Otomatis", 90000, 2]],
            columns=["Alternative", "Fixed_Cost", "Variable_Cost"],
        )
        return SheetData(params={"volume": 2500}, tables={"main": df})

    def solve(self, data: SheetData) -> ModuleResult:
        p = self.resolved_params(data)
        vol = float(p["volume"])
        df = clean_frame(data.table("main"))
        require_rows(df, 2, "Tabel alternatif biaya")
        c_nm = df.columns[0]
        c_fc = find_column(df, ["Fixed_Cost", "Fixed", "FC", "BiayaTetap"])
        c_vc = find_column(df, ["Variable_Cost", "Variable", "VC", "BiayaVariabel"])

        alts = [(str(df.at[i, c_nm]).strip(), to_float(df.at[i, c_fc], "FC"), to_float(df.at[i, c_vc], "VC"))
                for i in range(len(df))]

        crossovers = []
        for i in range(len(alts)):
            for j in range(i + 1, len(alts)):
                n1, f1, v1 = alts[i]
                n2, f2, v2 = alts[j]
                if abs(v1 - v2) > 1e-12:
                    xv = (f2 - f1) / (v1 - v2)
                    if xv >= 0:
                        crossovers.append([f"{n1} vs {n2}", xv, f1 + v1 * xv])

        costs_at_vol = [(nm, fc, vc, fc + vc * vol) for nm, fc, vc in alts]
        best = min(costs_at_vol, key=lambda t: t[3])
        max_x = max([c[1] for c in crossovers] + [vol]) * 1.4 or 1000.0
        xs = np.linspace(0, max_x, 11).tolist()

        r = ModuleResult()
        r.metric(f"Terbaik pada Volume {vol:g}", best[0], highlight=True)
        r.metric("Total Biaya Minimum", best[3], highlight=True)
        r.table("Biaya per Alternatif pada Volume Rencana",
                ["Alternatif", "Fixed Cost", "Variable Cost", f"Total Biaya (V={vol:g})"], costs_at_vol)
        if crossovers:
            r.table("Titik Potong (Crossover Points)", ["Pasangan", "Volume Crossover", "Biaya pada Titik Potong"], crossovers)
        r.chart("Kurva Biaya Total Alternatif", "line", {
            "x": [round(x, 1) for x in xs],
            "series": [{"name": nm, "data": [fc + vc * x for x in xs]} for nm, fc, vc in alts],
            "x_label": "Volume", "y_label": "Biaya Total",
        })
        r.interpretation = f"Pada volume {vol:g}, alternatif termurah adalah '{best[0]}' (total biaya {best[3]:,.2f})."
        return r
