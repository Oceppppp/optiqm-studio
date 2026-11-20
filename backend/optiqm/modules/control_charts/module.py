"""Modul Control Charts (SPC: X-bar & R, p-chart, c-chart)."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from optiqm.core import BaseModule, InputError, ModuleResult, ParamSpec, SheetData, register
from optiqm.core.parsing import clean_frame, find_column, require_rows, to_float

# Konstanta SPC standar ASTM/Heizer & Render untuk n = 2..10: (A2, D3, D4, d2)
SPC_CONSTANTS = {
    2: (1.880, 0.0, 3.267, 1.128), 3: (1.023, 0.0, 2.574, 1.693), 4: (0.729, 0.0, 2.282, 2.059),
    5: (0.577, 0.0, 2.114, 2.326), 6: (0.483, 0.0, 2.004, 2.534), 7: (0.419, 0.076, 1.924, 2.704),
    8: (0.373, 0.136, 1.864, 2.847), 9: (0.337, 0.184, 1.816, 2.970), 10: (0.308, 0.223, 1.777, 3.078),
}


def _max_one_side_run(vals: list[float], cl: float) -> int:
    best = cur = 0
    prev_sign = 0
    for v in vals:
        s = 1 if v > cl + 1e-12 else (-1 if v < cl - 1e-12 else 0)
        if s == 0:
            cur = 0
            prev_sign = 0
        elif s == prev_sign:
            cur += 1
        else:
            cur = 1
            prev_sign = s
        if cur > best:
            best = cur
    return best


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
        if z <= 0:
            raise InputError("Batas kontrol z_sigma harus > 0 (umumnya 3).")
        df = clean_frame(data.table("main"))
        require_rows(df, 2, "Tabel sampel SPC")
        samples = [str(x).strip() for x in df.iloc[:, 0]]

        r = ModuleResult()
        if ctype == "xbar_r":
            obs_cols = list(df.columns[1:])
            n = len(obs_cols)
            if n not in SPC_CONSTANTS:
                raise InputError(f"Jumlah observasi per sampel ({n}) harus antara 2 dan 10.")
            A2, D3, D4, d2 = SPC_CONSTANTS[n]
            mat = np.array([[to_float(df.at[i, c], f"{samples[i]}/{c}") for c in obs_cols] for i in range(len(df))])
            xbars = mat.mean(axis=1)
            rs = mat.max(axis=1) - mat.min(axis=1)
            xdbar, rbar = float(xbars.mean()), float(rs.mean())
            scale = z / 3.0
            ucl_x, lcl_x = xdbar + scale * A2 * rbar, xdbar - scale * A2 * rbar
            # Skala batas kendali R untuk sembarang z: 1 ± (z/3)*(D4 - 1); identik (D4, D3) saat z = 3
            ucl_r = (1.0 + scale * (D4 - 1.0)) * rbar
            lcl_r = max(0.0, (1.0 - scale * (D4 - 1.0)) * rbar)
            ooc_x = [samples[i] for i in range(len(df)) if xbars[i] > ucl_x or xbars[i] < lcl_x]
            ooc_r = [samples[i] for i in range(len(df)) if rs[i] > ucl_r or rs[i] < lcl_r]
            ooc = [samples[i] for i in range(len(df))
                   if xbars[i] > ucl_x or xbars[i] < lcl_x or rs[i] > ucl_r or rs[i] < lcl_r]
            sigma_hat = rbar / d2
            max_run = _max_one_side_run(xbars.tolist(), xdbar)

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
            r.analyze(
                "Metodologi Peta Kendali Variabel (X-bar & R)",
                f"Dianalisis {len(df)} subgrup dengan ukuran sampel n = {n} pada batas ±{z:g}σ menggunakan konstanta ASTM "
                f"(A₂ = {A2:.3f}, D₃ = {D3:.3f}, D₄ = {D4:.3f}, d₂ = {d2:.3f}).",
                [
                    f"Peta X-bar: CL = X̄̄ = {xdbar:.4f}, UCL = {ucl_x:.4f}, LCL = {lcl_x:.4f}.",
                    f"Peta R: CL = R̄ = {rbar:.4f}, UCL = {ucl_r:.4f}, LCL = {lcl_r:.4f}.",
                    f"Estimasi Simpangan Baku Proses (σ̂ = R̄ / d₂) = {sigma_hat:.4f} (rentang natural proses 6σ̂ ≈ {6 * sigma_hat:.4f}).",
                ],
            )
            stab_bullets = [
                f"Pelanggaran batas X-bar: {len(ooc_x)} titik ({', '.join(ooc_x) or 'tidak ada'}); pelanggaran batas R: {len(ooc_r)} titik ({', '.join(ooc_r) or 'tidak ada'}).",
                f"Uji Pola Run (Western Electric): deret terpanjang di satu sisi garis tengah X̄̄ adalah {max_run} sampel "
                f"({'PERINGATAN: ≥7 titik berturut-turut mengindikasikan pergeseran rata-rata proses!' if max_run >= 7 else 'normal (<7 titik)'}).",
            ]
            r.analyze("Diagnostik Stabilitas & Pola Pergeseran Proses", "Evaluasi variasi antar-subgrup (mean) dan dalam-subgrup (dispersi):", stab_bullets)
        elif ctype == "p":
            c_def = find_column(df, ["Defects", "Cacat", "Count", "D"])
            c_n = find_column(df, ["Size", "SampleSize", "n", "Total"], required=False)
            defs = [to_float(df.at[i, c_def], f"Defects {samples[i]}") for i in range(len(df))]
            ns = [to_float(df.at[i, c_n], f"Size {samples[i]}") if c_n else float(p["sample_size"]) for i in range(len(df))]
            for s_nm, d_v, n_v in zip(samples, defs, ns):
                if n_v <= 0:
                    raise InputError(f"Ukuran sampel n pada '{s_nm}' harus > 0.")
                if d_v < 0 or d_v > n_v:
                    raise InputError(f"Jumlah cacat pada '{s_nm}' ({d_v:g}) harus berada di antara 0 dan ukuran sampel n ({n_v:g}).")
            pbar = sum(defs) / sum(ns)
            ps = [d / n for d, n in zip(defs, ns)]
            ucls = [min(1.0, pbar + z * math.sqrt(pbar * (1 - pbar) / n)) for n in ns]
            lcls = [max(0.0, pbar - z * math.sqrt(pbar * (1 - pbar) / n)) for n in ns]
            ooc = [samples[i] for i in range(len(df)) if ps[i] > ucls[i] or ps[i] < lcls[i]]
            max_run = _max_one_side_run(ps, pbar)
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
            r.analyze(
                "Metodologi p-Chart (Proporsi Cacat Binomial)",
                f"Mengevaluasi {len(df)} sampel (total {sum(defs):,.0f} unit cacat dari {sum(ns):,.0f} unit diperiksa) pada batas ±{z:g}σ: "
                "UCL/LCL = p̄ ± z·√(p̄(1 − p̄)/n_i).",
                [
                    f"Proporsi cacat rata-rata p̄ = {pbar:.4f} ({pbar * 100:.2f}% atau ≈ {pbar * 1e6:,.0f} DPMO).",
                    f"Rentang proporsi observasi: {min(ps)*100:.2f}% s.d. {max(ps)*100:.2f}%; rentang batas kendali: LCL {min(lcls):.4f} s.d. UCL {max(ucls):.4f}.",
                    f"Deret satu sisi terpanjang: {max_run} sampel ({'indikasi pergeseran tren cacat!' if max_run >= 7 else 'tidak ada pola run mencurigakan'}).",
                ],
            )
        else:  # c-chart
            c_def = find_column(df, ["Defects", "Cacat", "Count", "c"])
            cs = [to_float(df.at[i, c_def], f"Defects {samples[i]}") for i in range(len(df))]
            if any(v < 0 for v in cs):
                raise InputError("Jumlah cacat (c) pada c-chart tidak boleh negatif.")
            cbar = sum(cs) / len(cs)
            ucl = cbar + z * math.sqrt(cbar)
            lcl = max(0.0, cbar - z * math.sqrt(cbar))
            ooc = [samples[i] for i in range(len(df)) if cs[i] > ucl or cs[i] < lcl]
            max_run = _max_one_side_run(cs, cbar)
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
            r.analyze(
                "Metodologi c-Chart (Jumlah Cacat Poisson per Unit)",
                f"Mengevaluasi {len(df)} unit inspeksi (total {sum(cs):,.0f} temuan cacat) dengan asumsi Poisson: σ_c = √c̄, batas = c̄ ± {z:g}√c̄.",
                [
                    f"Garis tengah c̄ = {cbar:.3f} cacat/unit (σ_c = {math.sqrt(cbar):.3f}); LCL = {lcl:.3f}, UCL = {ucl:.3f}.",
                    f"Rentang cacat per unit: {min(cs):g} s.d. {max(cs):g}; deret satu sisi terpanjang: {max_run} sampel.",
                ],
            )

        rec_bullets = []
        if ooc:
            rec_bullets.append(
                f"PROSES TIDAK TERKENDALI pada sampel {', '.join(ooc)}: segera lakukan root-cause analysis (5-Why / Fishbone) untuk menghilangkan assignable cause "
                "(mesin aus, bahan baku berbeda, operator baru, atau kesalahan kalibrasi)."
            )
            rec_bullets.append("Setelah penyebab khusus dieliminasi, keluarkan titik out-of-control dan hitung ulang batas kendali baru sebagai standar operasional.")
        else:
            rec_bullets.append("Proses berada dalam kendali statistik (variasi yang muncul hanyalah common-cause variation). Jangan lakukan penyesuaian mesin berlebihan (over-adjustment).")
            rec_bullets.append("Langkah lanjutan: bandingkan lebar kendali proses terhadap batas spesifikasi pelanggan (USL/LSL) untuk menghitung indeks kapabilitas Cp/Cpk.")
        r.analyze("Rekomendasi Pengendalian Kualitas", "Tindak lanjut tim QA/QC:", rec_bullets)

        msg = "Semua titik terkendali" if not ooc else f"Terdeteksi {len(ooc)} titik out-of-control ({', '.join(ooc)})"
        r.interpretation = f"Peta kendali {ctype}: {msg}."
        return r
