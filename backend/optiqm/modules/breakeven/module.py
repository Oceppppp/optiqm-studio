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
        p_pr = float(p["price"])
        p_vc = float(p["variable_cost"])
        if fc < 0 or vol < 0 or p_pr < 0 or p_vc < 0:
            raise InputError("Biaya tetap, volume, harga jual, dan biaya variabel tidak boleh negatif.")
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
                if any(s < 0 for s in raw_shares):
                    raise InputError("Proporsi penjualan (Share) tidak boleh negatif.")
                s_sum = sum(raw_shares)
                if s_sum <= 0:
                    raise InputError("Total proporsi penjualan harus > 0.")
                for i in range(len(cdf)):
                    nm = str(cdf.at[i, c_nm]).strip()
                    pr = to_float(cdf.at[i, c_pr], f"Price {nm}")
                    vc = to_float(cdf.at[i, c_vc], f"VC {nm}")
                    if pr < 0 or vc < 0:
                        raise InputError(f"Harga dan biaya variabel pada '{nm}' tidak boleh negatif.")
                    sh = raw_shares[i] / s_sum
                    rows.append((nm, pr, vc, sh))

        # Jika hanya 1 baris di tabel dan masih identik dengan default template (20, 8),
        # sedangkan pengguna mengubah parameter single-product (price/variable_cost), gunakan parameter.
        if len(rows) == 1:
            t_nm, t_pr, t_vc, _ = rows[0]
            tbl_is_default = (abs(t_pr - 20.0) < 1e-9 and abs(t_vc - 8.0) < 1e-9)
            param_edited = (abs(p_pr - 20.0) > 1e-9 or abs(p_vc - 8.0) > 1e-9)
            if tbl_is_default and param_edited:
                rows = [(t_nm, p_pr, p_vc, 1.0)]

        if not rows:
            rows = [("Produk", p_pr, p_vc, 1.0)]

        w_price = sum(pr * sh for _, pr, _, sh in rows)
        w_vc = sum(vc * sh for _, _, vc, sh in rows)
        w_cm = w_price - w_vc
        if w_cm <= 0:
            raise InputError(f"Margin kontribusi rata-rata ({w_cm:,.2f}) harus > 0 agar titik impas dapat dicapai.")

        cm_ratio = w_cm / w_price if w_price > 0 else 0.0
        bep_units = fc / w_cm
        bep_rev = fc / cm_ratio if cm_ratio > 0 else 0.0
        rev_at_v = w_price * vol
        tc_at_v = fc + w_vc * vol
        profit_at_v = rev_at_v - tc_at_v
        mos_units = vol - bep_units
        mos_pct = (mos_units / vol * 100.0) if vol > 0 else 0.0
        dol = (w_cm * vol / profit_at_v) if abs(profit_at_v) > 1e-9 else None

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

        # Analisis mendalam
        mode_txt = "Single-Product" if len(rows) == 1 else f"Multi-Product ({len(rows)} produk tertimbang bauran penjualan)"
        r.analyze(
            "Metodologi & Verifikasi Rumus Break-Even",
            f"Analisis dilakukan dengan pendekatan {mode_txt} menggunakan Biaya Tetap FC = {fc:,.2f}, Harga rata-rata = {w_price:,.2f}, dan Biaya Variabel rata-rata = {w_vc:,.2f}.",
            [
                f"Margin Kontribusi (CM) = P − VC = {w_price:,.2f} − {w_vc:,.2f} = {w_cm:,.2f}/unit (Rasio CM = {cm_ratio * 100:.2f}%).",
                f"BEP Unit = FC / CM = {fc:,.2f} / {w_cm:,.2f} = {bep_units:,.2f} unit.",
                f"BEP Penjualan = FC / Rasio CM = {fc:,.2f} / {cm_ratio:.4f} = {bep_rev:,.2f}.",
            ],
        )

        pos_bullets = [
            f"Pada target volume {vol:,.2f} unit: Pendapatan = {rev_at_v:,.2f}, Biaya Total = {tc_at_v:,.2f}, sehingga Laba/Rugi = {profit_at_v:+,.2f}.",
            (
                f"Margin of Safety (MoS) = +{mos_units:,.2f} unit ({mos_pct:.1f}% di atas BEP): penjualan boleh turun hingga {mos_pct:.1f}% sebelum perusahaan mulai rugi."
                if mos_units >= 0 else
                f"Defisit terhadap BEP = {mos_units:,.2f} unit: perlu tambahan penjualan minimal {abs(mos_units):,.2f} unit lagi untuk mencapai impas."
            ),
        ]
        if dol is not None and profit_at_v > 0:
            pos_bullets.append(
                f"Degree of Operating Leverage (DOL) = {dol:.2f}×: setiap kenaikan 1% volume penjualan akan mendongkrak laba operasi sebesar {dol:.2f}% (dan sebaliknya jika volume turun)."
            )
        r.analyze(
            "Bedah Margin of Safety & Operating Leverage (DOL)",
            "Margin of Safety mengukur bantal keamanan operasional, sedangkan DOL mengukur kepekaan laba terhadap fluktuasi volume penjualan:",
            pos_bullets,
        )

        # Sensitivitas harga +10% vs efisiensi FC -10%
        bep_price_up = fc / (w_price * 1.10 - w_vc)
        bep_fc_down = (fc * 0.90) / w_cm
        rec_bullets = [
            f"Sensitivitas Pengungkit Laba: menaikkan harga jual 10% menurunkan BEP dari {bep_units:,.1f} menjadi {bep_price_up:,.1f} unit "
            f"(turun {(1 - bep_price_up / bep_units) * 100:.1f}%), sedangkan memangkas biaya tetap 10% menurunkan BEP menjadi {bep_fc_down:,.1f} unit (turun 10.0%).",
        ]
        if mos_units < 0:
            rec_bullets.append(f"Fokus utama: tingkatkan volume penjualan melampaui {bep_units:,.0f} unit atau perbaiki Margin Kontribusi melalui efisiensi biaya variabel/penyesuaian harga.")
        elif len(rows) > 1:
            best_cm_p = max(rows, key=lambda x: x[1] - x[2])
            rec_bullets.append(f"Produk dengan margin kontribusi tertinggi adalah '{best_cm_p[0]}' ({best_cm_p[1] - best_cm_p[2]:,.2f}/unit); menggeser bauran pemasaran ke produk ini akan menurunkan titik impas total.")
        else:
            rec_bullets.append("Pertahankan struktur margin kontribusi dan pantau biaya tetap agar Margin of Safety tetap di atas 20%.")
        r.analyze("Rekomendasi Strategi Harga & Struktur Biaya", "Simulasi langkah peningkatan profitabilitas:", rec_bullets)
        return r
