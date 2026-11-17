"""Modul Aggregate Planning."""

from __future__ import annotations

import numpy as np
import pandas as pd

from optiqm.core import BaseModule, ModuleResult, ParamSpec, SheetData, register
from optiqm.core.parsing import clean_frame, find_column, require_rows, to_float

from .solver import solve_aggregate


@register
class AggregatePlanning(BaseModule):
    key = "aggregate_planning"
    name = "Aggregate Planning"
    category = "Perencanaan Produksi"
    description = "Perencanaan produksi jangka menengah (Chase, Level, atau Optimal LP) untuk meminimalkan biaya total."
    sheet_prefixes = ("AGG", "AGGREGATE")
    params = (
        ParamSpec("strategy", "Strategi", "choice", "optimal", ("optimal", "chase", "level")),
        ParamSpec("regular_cost", "Biaya Regular/Unit", "number", 40.0),
        ParamSpec("overtime_cost", "Biaya Overtime/Unit", "number", 60.0),
        ParamSpec("subcontract_cost", "Biaya Subkontrak/Unit", "number", 75.0),
        ParamSpec("holding_cost", "Biaya Simpan/Unit/Periode", "number", 5.0),
        ParamSpec("backorder_cost", "Biaya Backorder/Unit/Periode", "number", 20.0),
        ParamSpec("hire_cost", "Biaya Penambahan Kapasitas/Unit", "number", 10.0),
        ParamSpec("layoff_cost", "Biaya Pengurangan Kapasitas/Unit", "number", 15.0),
        ParamSpec("initial_inventory", "Persediaan Awal", "number", 0.0),
        ParamSpec("initial_production", "Produksi Reguler Periode Sebelumnya", "number", 800.0),
        ParamSpec("allow_backorder", "Izinkan Backorder", "boolean", True),
    )
    table_hint = "Kolom: Period, Demand, Regular_Cap, Overtime_Cap (opsional), Subcontract_Cap (opsional)."

    def template(self) -> SheetData:
        df = pd.DataFrame(
            [["Jan", 800, 800, 200, 150],
             ["Feb", 1000, 800, 200, 150],
             ["Mar", 1200, 800, 200, 150],
             ["Apr", 900, 800, 200, 150],
             ["May", 700, 800, 200, 150],
             ["Jun", 1100, 800, 200, 150]],
            columns=["Period", "Demand", "Regular_Cap", "Overtime_Cap", "Subcontract_Cap"],
        )
        return SheetData(params={"strategy": "optimal"}, tables={"main": df})

    def solve(self, data: SheetData) -> ModuleResult:
        p = self.resolved_params(data)
        df = clean_frame(data.table("main"))
        require_rows(df, 1, "Tabel rencana agregat")
        c_per = find_column(df, ["Period", "Periode", "Bulan"], required=False) or df.columns[0]
        c_dem = find_column(df, ["Demand", "Permintaan"])
        c_reg = find_column(df, ["Regular_Cap", "Regular", "KapasitasReguler"], required=False)
        c_ot = find_column(df, ["Overtime_Cap", "Overtime", "Lembur"], required=False)
        c_sub = find_column(df, ["Subcontract_Cap", "Subcontract", "Subkontrak"], required=False)

        periods = [str(v).strip() for v in df[c_per]]
        demand = np.array([to_float(df.at[i, c_dem], f"Demand {periods[i]}") for i in range(len(df))])
        reg = np.array([to_float(df.at[i, c_reg]) if c_reg and not pd.isna(df.at[i, c_reg]) else 1e9 for i in range(len(df))])
        ot = np.array([to_float(df.at[i, c_ot]) if c_ot and not pd.isna(df.at[i, c_ot]) else 0.0 for i in range(len(df))])
        sub = np.array([to_float(df.at[i, c_sub]) if c_sub and not pd.isna(df.at[i, c_sub]) else 0.0 for i in range(len(df))])

        costs = {
            "regular": float(p["regular_cost"]), "overtime": float(p["overtime_cost"]),
            "subcontract": float(p["subcontract_cost"]), "holding": float(p["holding_cost"]),
            "backorder": float(p["backorder_cost"]), "hire": float(p["hire_cost"]), "layoff": float(p["layoff_cost"]),
        }
        out = solve_aggregate(periods, demand, reg, ot, sub, costs,
                              float(p["initial_inventory"]), float(p["initial_production"]),
                              p["strategy"], bool(p["allow_backorder"]))

        r = ModuleResult()
        r.metric("Total Biaya Agregat", out["total_cost"], highlight=True)
        r.metric("Biaya Regular", out["totals"]["regular"])
        r.metric("Biaya Overtime + Subkontrak", out["totals"]["overtime"] + out["totals"]["subcontract"])
        r.metric("Biaya Simpan + Backorder", out["totals"]["holding"] + out["totals"]["backorder"])

        r.table("Jadwal Produksi Agregat",
                ["Periode", "Demand", "Regular", "Overtime", "Subkontrak", "Stok Akhir", "Backorder", "Naik Kap.", "Turun Kap.", "Biaya"],
                out["rows"])
        r.chart("Demand vs Total Produksi", "bar", {
            "x": out["periods"],
            "series": [
                {"name": "Demand", "data": out["demand"]},
                {"name": "Total Produksi", "data": out["prod"]},
                {"name": "Persediaan Akhir", "data": out["inv"]},
            ],
            "x_label": "Periode", "y_label": "Unit",
        })
        r.interpretation = f"Strategi '{p['strategy']}' menghasilkan total biaya agregat {out['total_cost']:,.2f}."
        return r
