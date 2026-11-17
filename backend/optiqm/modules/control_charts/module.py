"""Modul Control Charts (SPC: X-bar & R, p-chart, c-chart)."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from optiqm.core import BaseModule, InputError, ModuleResult, ParamSpec, SheetData, register
from optiqm.core.parsing import clean_frame, find_column, require_rows, to_float

# Konstanta SPC standar ASTM/Heizer & Render untuk n = 2..10: (A2, D3, D4)
SPC_CONSTANTS = {
    2: (1.880, 0.0, 3.267), 3: (1.023, 0.0, 2.574), 4: (0.729, 0.0, 2.282),
    5: (0.577, 0.0, 2.114), 6: (0.483, 0.0, 2.004), 7: (0.419, 0.076, 1.924),
    8: (0.373, 0.136, 1.864), 9: (0.337, 0.184, 1.816), 10: (0.308, 0.223, 1.777),
}


@register
class ControlCharts(BaseModule):
    key = "control_charts"
    name = "Quality Control Charts (SPC)"
    category = "Kualitas & Keandalan"
    description = "Peta kendali proses statistik (X-bar & R chart, p-chart proporsi cacat, dan c-chart jumlah cacat)."
    sheet_prefixes = ("QC", "SPC", "CONTROL")
    params = (
        ParamSpec("chart_type", "Jenis Peta Kendali", "choice", "xbar_r", ("xbar_r", "p", "c")),
        ParamSpec("sample_size", "Ukuran Sampel n (untuk p-chart bila tidak ada kolom n)", "integer", 100),
        ParamSpec("z_sigma", "Batas Kontrol (sigma, default 3)", "number", 3.0),
    )
    table_hint = ("xbar_r: Sample + kolom X1..Xn. p-chart: Sample, Defects, (opsional Size). c-chart: Sample, Defects.")

    def template(self) -> SheetData:
        df = pd.DataFrame(
            [[f"S{i}", 16.1, 16.0, 15.9, 16.2] for i in range(1, 9)],
            columns=["Sample", "X1", "X2", "X3", "X4"],
        )
        df.loc[4, "X1"] = 16.5  # sedikit variasi
        return SheetData(params={"chart_type": "xbar_r", "z_sigma": 3}, tables={"main": df})

    def solve(self, data: SheetData) -> ModuleResult:
        p = self.resolved_params(data)
        ctype = p["chart_type"]
        z = float(p["z_sigma"])
        df = clean_frame(data.table("main"))
        require_rows(df, 2, "Tabel sampel SPC")
        samples = [str(x).strip() for x in df.iloc[:, 0]]

        r = ModuleResult()
        if ctype == "xbar_r":
            obs_cols = list(df.columns[1:])
            n = len(obs_cols)
            if n not in SPC_CONSTANTS:
                raise InputError(f"Jumlah observasi per sampel ({n}) harus antara 2 dan 10.")
            A2, D3, D4 = SPC_CONSTANTS[n]
            mat = np.array([[to_float(df.at[i, c], f"{samples[i]}/{c}") for c in obs_cols] for i in range(len(df))])
            xbars = mat.mean(axis=1)
            rs = mat.max(axis=1) - mat.min(axis=1)
            xdbar, rbar = float(xbars.mean()), float(rs.mean())
            scale = z / 3.0
            ucl_x, lcl_x = xdbar + scale * A2 * rbar, xdbar - scale * A2 * rbar
            ucl_r, lcl_r = D4 * rbar, D3 * rbar
            ooc = [samples[i] for i in range(len(df))
                   if xbars[i] > ucl_x or xbars[i] < lcl_x or rs[i] > ucl_r or rs[i] < lcl_r]

            r.metric("X̄̄ (Garis Tengah X-bar)", xdbar, highlight=True)
            r.metric("UCL / LCL X-bar", f"{ucl_x:.4f} / {lcl_x:.4f}")
            r.metric("R̄ (Garis Tengah R)", rbar)
            r.metric("Titik Out of Control", len(ooc), highlight=bool(ooc))
            r.table("Statistik per Sampel (X-bar & R)", ["Sampel", "X-bar", "Range (R)", "Status"],
                    [[samples[i], xbars[i], rs[i], "Out of Control" if samples[i] in ooc else "In Control"]
                     for i in range(len(df))])
            r.chart("Peta Kendali X-bar", "line", {
                "x": samples,
                "series": [
                    {"name": "X-bar", "data": xbars.tolist()},
                    {"name": "UCL", "data": [ucl_x] * len(samples)},
                    {"name": "CL", "data": [xdbar] * len(samples)},
                    {"name": "LCL", "data": [lcl_x] * len(samples)},
                ], "x_label": "Sampel", "y_label": "Rata-rata",
            })
            r.chart("Peta Kendali R (Range)", "line", {
                "x": samples,
                "series": [
                    {"name": "R", "data": rs.tolist()},
                    {"name": "UCL", "data": [ucl_r] * len(samples)},
                    {"name": "CL", "data": [rbar] * len(samples)},
                    {"name": "LCL", "data": [lcl_r] * len(samples)},
                ], "x_label": "Sampel", "y_label": "Range",
            })
        elif ctype == "p":
            c_def = find_column(df, ["Defects", "Cacat", "Count", "D"])
            c_n = find_column(df, ["Size", "SampleSize", "n", "Total"], required=False)
            defs = [to_float(df.at[i, c_def], "Defects") for i in range(len(df))]
            ns = [to_float(df.at[i, c_n], "Size") if c_n else float(p["sample_size"]) for i in range(len(df))]
            pbar = sum(defs) / sum(ns)
            ps = [d / n for d, n in zip(defs, ns)]
            ucls = [min(1.0, pbar + z * math.sqrt(pbar * (1 - pbar) / n)) for n in ns]
            lcls = [max(0.0, pbar - z * math.sqrt(pbar * (1 - pbar) / n)) for n in ns]
            ooc = [samples[i] for i in range(len(df)) if ps[i] > ucls[i] or ps[i] < lcls[i]]
            r.metric("p̄ (Proporsi Cacat Rata-rata)", pbar, highlight=True)
            r.metric("Titik Out of Control", len(ooc), highlight=bool(ooc))
            r.table("Data p-chart", ["Sampel", "n", "Cacat", "Proporsi (p)", "LCL", "UCL", "Status"],
                    [[samples[i], ns[i], defs[i], ps[i], lcls[i], ucls[i], "Out of Control" if samples[i] in ooc else "In Control"]
                     for i in range(len(df))])
            r.chart("Peta Kendali p-chart", "line", {
                "x": samples,
                "series": [{"name": "p", "data": ps}, {"name": "UCL", "data": ucls},
                           {"name": "p-bar", "data": [pbar] * len(samples)}, {"name": "LCL", "data": lcls}],
                "x_label": "Sampel", "y_label": "Proporsi Cacat",
            })
        else:  # c-chart
            c_def = find_column(df, ["Defects", "Cacat", "Count", "c"])
            cs = [to_float(df.at[i, c_def], "Defects") for i in range(len(df))]
            cbar = sum(cs) / len(cs)
            ucl = cbar + z * math.sqrt(cbar)
            lcl = max(0.0, cbar - z * math.sqrt(cbar))
            ooc = [samples[i] for i in range(len(df)) if cs[i] > ucl or cs[i] < lcl]
            r.metric("c̄ (Rata-rata Cacat/Unit)", cbar, highlight=True)
            r.metric("UCL / LCL", f"{ucl:.3f} / {lcl:.3f}")
            r.metric("Titik Out of Control", len(ooc), highlight=bool(ooc))
            r.table("Data c-chart", ["Sampel", "Jumlah Cacat (c)", "Status"],
                    [[samples[i], cs[i], "Out of Control" if samples[i] in ooc else "In Control"] for i in range(len(df))])
            r.chart("Peta Kendali c-chart", "line", {
                "x": samples,
                "series": [{"name": "c", "data": cs}, {"name": "UCL", "data": [ucl] * len(samples)},
                           {"name": "c-bar", "data": [cbar] * len(samples)}, {"name": "LCL", "data": [lcl] * len(samples)}],
                "x_label": "Sampel", "y_label": "Cacat",
            })
        msg = "Semua titik terkendali" if not ooc else f"Terdeteksi {len(ooc)} titik out-of-control ({', '.join(ooc)})"
        r.interpretation = f"Peta kendali {ctype}: {msg}."
        return r
