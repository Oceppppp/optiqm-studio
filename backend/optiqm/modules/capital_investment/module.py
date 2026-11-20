"""Modul Capital Investment (NPV, IRR, Payback Period, Profitability Index)."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import brentq

from optiqm.core import BaseModule, InputError, ModuleResult, ParamSpec, SheetData, register
from optiqm.core.parsing import clean_frame, find_column, require_rows, to_float


def _irr(years: list[float], cfs: list[float]) -> float | None:
    if not (any(x < 0 for x in cfs) and any(x > 0 for x in cfs)):
        return None

    def npv_fn(r: float) -> float:
        return sum(cf / ((1.0 + r) ** t) for t, cf in zip(years, cfs))

    grid = [-0.99, -0.9, -0.75, -0.5, -0.25, -0.1, 0.0, 0.05, 0.1, 0.2, 0.35, 0.5, 1.0, 2.0, 5.0, 15.0, 50.0, 200.0]
    vals = []
    for g in grid:
        try:
            v = npv_fn(g)
            vals.append((g, v))
        except (OverflowError, ZeroDivisionError):
            continue
    for (r1, v1), (r2, v2) in zip(vals, vals[1:]):
        if abs(v1) < 1e-12:
            return float(r1)
        if v1 * v2 < 0:
            try:
                return float(brentq(npv_fn, r1, r2))
            except ValueError:
                continue
    return None


def _payback(years: list[float], cfs: list[float]) -> float | None:
    cum = cfs[0]
    if cum >= 0:
        return float(years[0])
    for idx in range(1, len(cfs)):
        prev = cum
        cum += cfs[idx]
        if cum >= 0 and cfs[idx] > 0:
            span = years[idx] - years[idx - 1]
            return float(years[idx - 1] + span * (abs(prev) / cfs[idx]))
    return None


def _sign_changes(cfs: list[float]) -> int:
    nz = [1 if c > 0 else -1 for c in cfs if abs(c) > 1e-12]
    return sum(1 for a, b in zip(nz, nz[1:]) if a != b)


@register
class CapitalInvestment(BaseModule):
    key = "capital_investment"
    name = "Capital Investment (NPV & IRR)"
    category = "Biaya & Keuangan"
    description = "Evaluasi kelayakan investasi (Net Present Value, IRR, Payback Period, dan Profitability Index)."
    sheet_prefixes = ("NPV", "IRR", "INVEST")
    params = (ParamSpec("discount_rate", "Tingkat Diskonto / Bunga (%)", "number", 10.0),)
    table_hint = "Kolom: Year (tahun 0, 1, 2, ...), diikuti kolom arus kas satu atau lebih proyek (tahun 0 negatif)."

    def template(self) -> SheetData:
        df = pd.DataFrame(
            [[0, -100000, -120000], [1, 35000, 30000], [2, 40000, 45000], [3, 45000, 55000], [4, 30000, 60000]],
            columns=["Year", "Proyek A", "Proyek B"],
        )
        return SheetData(params={"discount_rate": 10}, tables={"main": df})

    def solve(self, data: SheetData) -> ModuleResult:
        p = self.resolved_params(data)
        rate = float(p["discount_rate"])
        rate = rate / 100.0 if rate > 1.0 else rate
        if rate <= -1.0:
            raise InputError("Discount rate tidak valid (harus > -100%).")

        df = clean_frame(data.table("main"))
        require_rows(df, 2, "Tabel arus kas")
        c_yr = find_column(df, ["Year", "Tahun", "Period", "t"], required=False) or df.columns[0]
        projs = [c for c in df.columns if c != c_yr]
        if not projs:
            raise InputError("Minimal harus ada 1 kolom proyek.")
        raw_years = [to_float(df.at[i, c_yr], f"Year baris {i + 1}") for i in range(len(df))]
        order = sorted(range(len(df)), key=lambda i: raw_years[i])
        years = [raw_years[i] for i in order]

        r = ModuleResult()
        summary_rows = []
        npvs = []
        proj_details = []
        for pr in projs:
            cfs = [to_float(df.at[i, pr], f"{pr} tahun {raw_years[i]:g}") for i in order]
            pvs = [cf / ((1.0 + rate) ** t) for t, cf in zip(years, cfs)]
            npv = sum(pvs)
            pv_in = sum(pv for pv in pvs if pv > 0)
            pv_out = sum(-pv for pv in pvs if pv < 0)
            pi = (pv_in / pv_out) if pv_out > 0 else None
            irr_v = _irr(years, cfs)
            pb = _payback(years, cfs)
            dpb = _payback(years, pvs)
            sc = _sign_changes(cfs)
            if sc > 1:
                r.warnings.append(
                    f"Proyek '{pr}' memiliki {sc} perubahan tanda arus kas (non-konvensional): IRR dapat lebih dari satu; jadikan NPV sebagai kriteria utama."
                )
            npvs.append(npv)
            proj_details.append({
                "name": pr, "npv": npv, "irr": irr_v, "pb": pb, "dpb": dpb, "pi": pi,
                "pv_in": pv_in, "pv_out": pv_out, "net_nom": sum(cfs),
            })
            summary_rows.append([pr, npv, f"{irr_v * 100:.2f}%" if irr_v is not None else "-",
                                 f"{pb:.2f} thn" if pb is not None else "Tidak kembali",
                                 f"{dpb:.2f} thn" if dpb is not None else "Tidak kembali",
                                 pi if pi is not None else "-", "Layak (NPV > 0)" if npv > 0 else "Tidak Layak"])

        best_i = int(np.argmax(npvs))
        r.metric("Proyek Terbaik (NPV)", projs[best_i], highlight=True)
        r.metric(f"NPV ({projs[best_i]})", npvs[best_i], highlight=True)
        r.table("Evaluasi Kelayakan Proyek",
                ["Proyek", f"NPV (@{rate*100:.1f}%)", "IRR", "Payback Period", "Discounted Payback", "Profitability Index", "Keputusan"],
                summary_rows)
        r.chart("Perbandingan NPV Proyek", "bar", {
            "x": projs, "series": [{"name": "NPV", "data": npvs}],
            "x_label": "Proyek", "y_label": "NPV",
        })
        r.interpretation = f"Dengan tingkat diskonto {rate*100:.1f}%, proyek terbaik adalah '{projs[best_i]}' (NPV = {npvs[best_i]:,.2f})."

        # Analisis mendalam
        feasible = [d for d in proj_details if d["npv"] > 0]
        r.analyze(
            "Metodologi Capital Budgeting (Nilai Waktu Uang)",
            f"Arus kas pada periode t = [{', '.join(f'{t:g}' for t in years)}] didiskontokan dengan tingkat bunga r = {rate * 100:.2f}% "
            "menggunakan rumus NPV = Σ CF_t / (1 + r)^t, PI = PV(Arus Masuk) / PV(Arus Keluar), serta IRR di mana NPV(IRR) = 0.",
            [
                f"Kelayakan Umum: {len(feasible)} dari {len(projs)} proyek memiliki NPV > 0 (menciptakan nilai tambah bersih di atas biaya modal {rate * 100:.2f}%).",
                f"Proyek terunggul menurut NPV: '{proj_details[best_i]['name']}' dengan NPV = {proj_details[best_i]['npv']:,.2f}"
                + (f" dan IRR = {proj_details[best_i]['irr'] * 100:.2f}% (spread +{(proj_details[best_i]['irr'] - rate) * 100:.2f}% di atas WACC/diskonto)."
                   if proj_details[best_i]["irr"] is not None else "."),
            ],
        )

        proj_bullets = []
        for d in proj_details:
            irr_s = f"{d['irr'] * 100:.2f}%" if d["irr"] is not None else "N/A"
            pi_s = f"{d['pi']:.3f}" if d["pi"] is not None else "N/A"
            pb_s = f"{d['pb']:.2f} thn" if d["pb"] is not None else "tidak kembali"
            dpb_s = f"{d['dpb']:.2f} thn" if d["dpb"] is not None else "tidak kembali"
            proj_bullets.append(
                f"'{d['name']}': PV Masuk = {d['pv_in']:,.2f} vs PV Keluar = {d['pv_out']:,.2f} → NPV = {d['npv']:+,.2f}, "
                f"IRR = {irr_s}, PI = {pi_s}, Payback = {pb_s} (Discounted = {dpb_s})."
            )
        # Cek konflik peringkat NPV vs IRR / PI
        if len(proj_details) > 1:
            irr_valid = [d for d in proj_details if d["irr"] is not None]
            pi_valid = [d for d in proj_details if d["pi"] is not None]
            if irr_valid:
                best_irr = max(irr_valid, key=lambda d: d["irr"])
                if best_irr["name"] != proj_details[best_i]["name"]:
                    proj_bullets.append(
                        f"KONFLIK PERINGKAT NPV vs IRR: '{proj_details[best_i]['name']}' unggul NPV ({proj_details[best_i]['npv']:,.2f}), "
                        f"tetapi '{best_irr['name']}' memiliki IRR lebih tinggi ({best_irr['irr'] * 100:.2f}%) akibat perbedaan skala/profil arus kas."
                    )
            if pi_valid:
                best_pi = max(pi_valid, key=lambda d: d["pi"])
                if best_pi["name"] != proj_details[best_i]["name"]:
                    proj_bullets.append(
                        f"Efisiensi per Rupiah Modal: '{best_pi['name']}' memiliki Profitability Index tertinggi ({best_pi['pi']:.3f})."
                    )
        r.analyze(
            "Bedah Kelayakan per Proyek & Konflik Peringkat",
            "Perbandingan NPV, IRR, Payback, dan Profitability Index menunjukkan nilai absolut versus efisiensi modal masing-masing proyek:",
            proj_bullets,
        )

        rec_bullets = []
        if not feasible:
            rec_bullets.append(f"TOLAK seluruh proyek pada tingkat diskonto {rate * 100:.2f}% karena tidak ada yang menghasilkan NPV positif.")
        else:
            rec_bullets.append(
                f"Jika proyek bersifat saling meniadakan (mutually exclusive): pilih '{proj_details[best_i]['name']}' karena NPV adalah ukuran paling akurat bagi penambahan kekayaan perusahaan."
            )
            if len(feasible) > 1:
                by_pi = sorted([d for d in feasible if d["pi"] is not None], key=lambda d: -d["pi"])
                if by_pi:
                    rec_bullets.append(
                        "Jika proyek bersifat independen dengan keterbatasan modal (capital rationing): prioritaskan alokasi modal berdasarkan PI tertinggi: "
                        + " → ".join(f"{d['name']} (PI={d['pi']:.2f})" for d in by_pi) + "."
                    )
        r.analyze("Rekomendasi Keputusan Investasi", "Panduan alokasi anggaran modal:", rec_bullets)
        return r
