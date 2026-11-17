"""Modul Center of Gravity (Penentuan koordinat pusat distribusi)."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from optiqm.core import BaseModule, InputError, ModuleResult, SheetData, register
from optiqm.core.parsing import clean_frame, find_column, require_rows, to_float


@register
class CenterOfGravity(BaseModule):
    key = "center_of_gravity"
    name = "Center of Gravity"
    category = "Lokasi & Tata Letak"
    description = "Menghitung koordinat pusat distribusi (Cx, Cy) yang meminimalkan jarak transportasi berbobot."
    sheet_prefixes = ("COG", "GRAVITY")
    table_hint = "Kolom: Location, X, Y, Load (volume/beban pengiriman)."

    def template(self) -> SheetData:
        # Quain's Discount (Heizer & Render): Cx = 66.7, Cy = 93.3
        df = pd.DataFrame(
            [["Chicago", 30, 120, 2000],
             ["Pittsburgh", 90, 110, 1000],
             ["New York", 130, 130, 1000],
             ["Atlanta", 60, 40, 2000]],
            columns=["Location", "X", "Y", "Load"],
        )
        return SheetData(tables={"main": df})

    def solve(self, data: SheetData) -> ModuleResult:
        df = clean_frame(data.table("main"))
        require_rows(df, 1, "Tabel koordinat lokasi")
        c_nm = find_column(df, ["Location", "Lokasi", "Name", "Kota"], required=False) or df.columns[0]
        c_x = find_column(df, ["X", "CoordX", "Lon"])
        c_y = find_column(df, ["Y", "CoordY", "Lat"])
        c_w = find_column(df, ["Load", "Weight", "Volume", "Demand", "Bobot"])

        names = [str(x).strip() for x in df[c_nm]]
        xs = np.array([to_float(df.at[i, c_x], f"X {names[i]}") for i in range(len(df))])
        ys = np.array([to_float(df.at[i, c_y], f"Y {names[i]}") for i in range(len(df))])
        ws = np.array([to_float(df.at[i, c_w], f"Load {names[i]}") for i in range(len(df))])
        if (ws < 0).any() or ws.sum() <= 0:
            raise InputError("Beban (Load) harus non-negatif dan total > 0.")

        cx = float((xs * ws).sum() / ws.sum())
        cy = float((ys * ws).sum() / ws.sum())
        dists = [math.hypot(x - cx, y - cy) for x, y in zip(xs, ys)]
        weighted_dist = float(sum(d * w for d, w in zip(dists, ws)))

        r = ModuleResult()
        r.metric("Koordinat Pusat X*", cx, highlight=True)
        r.metric("Koordinat Pusat Y*", cy, highlight=True)
        r.metric("Total Jarak Berbobot", weighted_dist)
        r.table("Rincian Lokasi & Jarak ke Pusat",
                ["Lokasi", "X", "Y", "Beban (Q)", "X·Q", "Y·Q", "Jarak ke Pusat"],
                [[names[i], xs[i], ys[i], ws[i], xs[i] * ws[i], ys[i] * ws[i], dists[i]] for i in range(len(names))])
        r.chart("Peta Koordinat & Center of Gravity", "scatter", {
            "series": [
                {"name": "Lokasi Tujuan", "points": [[float(x), float(y)] for x, y in zip(xs, ys)]},
                {"name": "Center of Gravity (Cx, Cy)", "points": [[cx, cy]]},
            ],
            "x_label": "Koordinat X", "y_label": "Koordinat Y",
        })
        r.interpretation = f"Titik Center of Gravity berada di koordinat ({cx:,.2f}, {cy:,.2f})."
        return r
