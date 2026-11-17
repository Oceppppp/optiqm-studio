"""Modul Break-Even Analysis (Single & Multi-Product)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from optiqm.core import BaseModule, InputError, ModuleResult, ParamSpec, SheetData, register
from optiqm.core.parsing import clean_frame, find_column, to_float


@register
class BreakEven(BaseModule):
    key = "breakeven"
    name = "Break-Even Analysis"
    category = "Biaya & Keuangan"
    description = "Menghitung titik impas (BEP dalam unit dan rupiah/dolar) untuk satu maupun banyak produk."
    sheet_prefixes = ("BEP", "BREAKEVEN", "IMPAS")
    params = (
        ParamSpec("fixed_cost", "Biaya Tetap (Fixed Cost)", "number", 10000.0),
        ParamSpec("variable_cost", "Biaya Variabel / Unit (Single Product)", "number", 8.0),
        ParamSpec("price", "Harga Jual / Unit (Single Product)", "number", 20.0),
        ParamSpec("volume", "Volume Penjualan / Target Volume (opsional)", "number", 1500.0),
    )
    table_hint = ("Untuk single product cukup isi parameter di atas. Untuk multi-product, isi tabel [main] "
                  "dengan kolom: Product, Price, Variable_Cost, Share (proporsi penjualan dalam % atau bobot).")

    def template(self) -> SheetData:
        return SheetData(
            params={"fixed_cost": 10000, "variable_cost": 8, "price": 20, "volume": 1500},
            tables={"main": pd.DataFrame(
                [["Produk Utama", 20, 8, 100]],
                columns=["Product", "Price", "Variable_Cost", "Share"],
            )},
        )

    def solve(self, data: SheetData) -> ModuleResult:
        p = self.resolved_params(data)
        fc = float(p["fixed_cost"])
        vol = float(p["volume"])
        df = data.table("main", required=False)

        rows = []
        if df is not None and len(clean_frame(df)) > 0:
            cdf = clean_frame(df)
            c_pr = find_column(cdf, ["Price", "Harga", "P"], required=False)
            c_vc = find_column(cdf, ["Variable_Cost", "VC", "BiayaVariabel"], required=False)
            c_sh = find_column(cdf, ["Share", "Mix", "Weight", "Proporsi", "Bobot"], required=False)
            if c_pr and c_vc:
                c_nm = cdf.columns[0]
                raw_shares = [to_float(cdf.at[i, c_sh], f"Share {i+1}") if c_sh else 1.0 for i in range(len(cdf))]
                s_sum = sum(raw_shares)
                if s_sum <= 0:
                    raise InputError("Total proporsi penjualan harus > 0.")
                for i in range(len(cdf)):
                    nm = str(cdf.at[i, c_nm]).strip()
                    pr = to_float(cdf.at[i, c_pr], f"Price {nm}")
                    vc = to_float(cdf.at[i, c_vc], f"VC {nm}")
                    sh = raw_shares[i] / s_sum
                    rows.append((nm, pr, vc, sh))

        if not rows:
            rows = [("Produk", float(p["price"]), float(p["variable_cost"]), 1.0)]

        w_price = sum(pr * sh for _, pr, _, sh in rows)
        w_vc = sum(vc * sh for _, _, vc, sh in rows)
        w_cm = w_price - w_vc
        if w_cm <= 0:
            raise InputError(f"Margin kontribusi rata-rata ({w_cm:,.2f}) harus > 0 agar titik impas dapat dicapai.")

        bep_units = fc / w_cm
        bep_rev = fc / (w_cm / w_price) if w_price > 0 else 0.0
        rev_at_v = w_price * vol
        tc_at_v = fc + w_vc * vol
        profit_at_v = rev_at_v - tc_at_v

        r = ModuleResult()
        r.metric("BEP (Unit)", bep_units, unit="unit", highlight=True)
        r.metric("BEP (Nilai Penjualan)", bep_rev, highlight=True)
        r.metric("Margin Kontribusi / Unit", w_cm)
        r.metric(f"Laba pada Volume {vol:g}", profit_at_v)

        r.table("Rincian per Produk pada Titik Impas",
                ["Produk", "Harga", "Biaya Variabel", "Margin Kontribusi", "Bauran (%)", "BEP (Unit)", "BEP (Nilai)"],
                [[nm, pr, vc, pr - vc, sh * 100, bep_units * sh, bep_units * sh * pr] for nm, pr, vc, sh in rows])

        xmax = max(bep_units * 2.0, vol * 1.2, 10.0)
        xs = np.linspace(0, xmax, 11).tolist()
        r.chart("Grafik Break-Even (Biaya vs Pendapatan)", "line", {
            "x": [round(x, 1) for x in xs],
            "series": [
                {"name": "Pendapatan Total (TR)", "data": [w_price * x for x in xs]},
                {"name": "Biaya Total (TC)", "data": [fc + w_vc * x for x in xs]},
                {"name": "Biaya Tetap (FC)", "data": [fc for _ in xs]},
            ],
            "x_label": "Volume (Unit)", "y_label": "Nilai",
        })
        r.interpretation = f"Titik impas tercapai pada {bep_units:,.2f} unit (penjualan {bep_rev:,.2f}). Pada volume {vol:g}, laba = {profit_at_v:,.2f}."
        return r
