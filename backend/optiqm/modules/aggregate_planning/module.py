"""Modul Aggregate Planning."""

from __future__ import annotations

import numpy as np
import pandas as pd

from optiqm.core import BaseModule, InputError, ModuleResult, ParamSpec, SheetData, SolverError, register
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
        if (demand < 0).any() or (reg < 0).any() or (ot < 0).any() or (sub < 0).any():
            raise InputError("Permintaan dan kapasitas (Regular/Overtime/Subkontrak) tidak boleh negatif.")

        costs = {
            "regular": float(p["regular_cost"]), "overtime": float(p["overtime_cost"]),
            "subcontract": float(p["subcontract_cost"]), "holding": float(p["holding_cost"]),
            "backorder": float(p["backorder_cost"]), "hire": float(p["hire_cost"]), "layoff": float(p["layoff_cost"]),
        }
        init_inv, init_prod = float(p["initial_inventory"]), float(p["initial_production"])
        if any(v < 0 for v in costs.values()) or init_inv < 0 or init_prod < 0:
            raise InputError("Semua parameter biaya, stok awal, dan produksi awal harus ≥ 0.")

        allow_bo = bool(p["allow_backorder"])
        out = solve_aggregate(periods, demand, reg, ot, sub, costs, init_inv, init_prod, p["strategy"], allow_bo)

        r = ModuleResult()
        r.metric("Total Biaya Agregat", out["total_cost"], highlight=True)
        r.metric("Biaya Regular", out["totals"]["regular"])
        r.metric("Biaya Overtime + Subkontrak", out["totals"]["overtime"] + out["totals"]["subcontract"])
        r.metric("Biaya Simpan + Backorder", out["totals"]["holding"] + out["totals"]["backorder"])

        end_bo = float(out["rows"][-1][6])
        if end_bo > 1e-6:
            r.warnings.append(
                f"Strategi '{p['strategy']}' menyisakan backorder akhir sebesar {end_bo:,.2f} unit pada periode terakhir ({periods[-1]})."
            )

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

        # Analisis mendalam: bandingkan semua 3 strategi
        comp_bullets = []
        for st_name, st_lbl in [("optimal", "Optimal (LP)"), ("chase", "Chase Strategy"), ("level", "Level Strategy")]:
            try:
                alt = out if st_name == p["strategy"] else solve_aggregate(
                    periods, demand, reg, ot, sub, costs, init_inv, init_prod, st_name, allow_bo
                )
                diff = alt["total_cost"] - out["total_cost"]
                tag = " (strategi aktif)" if st_name == p["strategy"] else f" ({diff:+,.2f} dibanding aktif)"
                comp_bullets.append(f"{st_lbl}: total biaya = {alt['total_cost']:,.2f}{tag}.")
            except SolverError:
                comp_bullets.append(f"{st_lbl}: tidak layak dengan batasan kapasitas dan backorder saat ini.")
        r.analyze(
            "Metodologi & Perbandingan Strategi Perencanaan Agregat",
            f"Perencanaan mencakup {len(periods)} periode dengan total permintaan {float(demand.sum()):,.0f} unit "
            f"(stok awal {init_inv:,.0f}, syarat backorder akhir horizon = 0 pada model LP).",
            comp_bullets,
        )

        tc = out["total_cost"]
        tots = out["totals"]
        tot_reg = sum(row[2] for row in out["rows"])
        tot_ot = sum(row[3] for row in out["rows"])
        tot_sub = sum(row[4] for row in out["rows"])
        tot_bo = sum(row[6] for row in out["rows"])
        fin_reg_cap = float(reg[reg < 1e8].sum())
        util_str = f"{tot_reg / fin_reg_cap * 100:.1f}%" if fin_reg_cap > 0 else "tak terbatas"
        peak_idx = int(np.argmax(demand))
        r.analyze(
            "Struktur Biaya & Pemanfaatan Kapasitas",
            f"Rata-rata biaya produksi agregat = {(tc / float(demand.sum())) if demand.sum() > 0 else 0.0:,.2f}/unit permintaan:",
            [
                f"Produksi Reguler: {tot_reg:,.0f} unit (utilisasi kapasitas reguler {util_str}) → biaya {tots['regular']:,.2f} ({(tots['regular']/tc*100) if tc > 0 else 0:.1f}%).",
                f"Overtime & Subkontrak: {tot_ot:,.0f} unit lembur + {tot_sub:,.0f} unit subkontrak → biaya {tots['overtime'] + tots['subcontract']:,.2f} ({((tots['overtime']+tots['subcontract'])/tc*100) if tc > 0 else 0:.1f}%).",
                f"Simpan, Backorder & Penyesuaian Kapasitas: Simpan={tots['holding']:,.2f}, Backorder={tots['backorder']:,.2f} ({tot_bo:,.0f} unit-periode), Hire/Layoff={tots['hire_layoff']:,.2f}.",
                f"Periode puncak permintaan terjadi pada '{periods[peak_idx]}' ({demand[peak_idx]:,.0f} unit vs kapasitas reguler {reg[peak_idx]:,.0f} unit).",
            ],
        )

        rec_bullets = []
        if tot_ot + tot_sub > 0:
            rec_bullets.append(
                f"Permintaan melampaui kapasitas reguler pada beberapa periode sehingga membutuhkan {tot_ot:,.0f} unit lembur dan {tot_sub:,.0f} unit subkontrak; "
                "lakukan pra-produksi (anticipation inventory) di periode sepi bila biaya simpan lebih murah dari selisih lembur."
            )
        else:
            rec_bullets.append("Kapasitas reguler mencukupi seluruh permintaan tanpa lembur maupun subkontrak.")
        if tot_bo > 0:
            rec_bullets.append(f"Terjadi backorder antarpériode sebesar {tot_bo:,.0f} unit-periode; konfirmasi toleransi keterlambatan pelanggan atau matikan 'Izinkan Backorder' bila SLA ketat.")
        if p["strategy"] != "optimal":
            rec_bullets.append("Bandingkan jadwal ini dengan strategi 'optimal' (LP) untuk melihat batas bawah biaya teoretis dan potensi penghematan.")
        r.analyze("Rekomendasi Kapasitas & Tenaga Kerja", "Langkah taktis untuk manajer operasi:", rec_bullets)
        return r
