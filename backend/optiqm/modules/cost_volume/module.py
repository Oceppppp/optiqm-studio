"""Modul Cost-Volume Analysis (perbandingan beberapa alternatif proses/mesin)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from optiqm.core import BaseModule, InputError, ModuleResult, ParamSpec, SheetData, register
from optiqm.core.parsing import clean_frame, find_column, require_rows, to_float


def _optimal_intervals(alts: list[tuple[str, float, float]]) -> tuple[list[tuple[float, float | None, str]], list[str]]:
    """Hitung rentang volume [v_lo, v_hi] di mana setiap alternatif merupakan yang termurah (lower envelope)."""
    pts = {0.0}
    for i in range(len(alts)):
        for j in range(i + 1, len(alts)):
            _, f1, v1 = alts[i]
            _, f2, v2 = alts[j]
            if abs(v1 - v2) > 1e-12:
                xv = (f2 - f1) / (v1 - v2)
                if xv > 0:
                    pts.add(xv)
    xs = sorted(pts)
    intervals: list[tuple[float, float | None, str]] = []
    winners: set[str] = set()
    for idx, lo in enumerate(xs):
        hi = xs[idx + 1] if idx + 1 < len(xs) else None
        probe = (lo + hi) / 2.0 if hi is not None else (lo + max(1.0, lo * 0.5) + 10.0)
        win = min(alts, key=lambda a: (a[1] + a[2] * probe, a[2]))[0]
        winners.add(win)
        if intervals and intervals[-1][2] == win:
            intervals[-1] = (intervals[-1][0], hi, win)
        else:
            intervals.append((lo, hi, win))
    dominated = [nm for nm, _, _ in alts if nm not in winners]
    return intervals, dominated


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

    def solve(self, data: SheetData, entity_label: str = "alternatif") -> ModuleResult:
        p = self.resolved_params(data)
        vol = float(p["volume"])
        if vol < 0:
            raise InputError("Volume rencana tidak boleh negatif.")
        df = clean_frame(data.table("main"))
        require_rows(df, 2, "Tabel alternatif biaya")
        c_nm = df.columns[0]
        c_fc = find_column(df, ["Fixed_Cost", "Fixed", "FC", "BiayaTetap"])
        c_vc = find_column(df, ["Variable_Cost", "Variable", "VC", "BiayaVariabel"])

        alts = []
        for i in range(len(df)):
            nm = str(df.at[i, c_nm]).strip()
            fc = to_float(df.at[i, c_fc], f"FC {nm}")
            vc = to_float(df.at[i, c_vc], f"VC {nm}")
            if fc < 0 or vc < 0:
                raise InputError(f"Biaya tetap dan biaya variabel pada '{nm}' tidak boleh negatif.")
            alts.append((nm, fc, vc))

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
        ranked = sorted(costs_at_vol, key=lambda t: t[3])
        best = ranked[0]
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
        r.interpretation = f"Pada volume {vol:g}, {entity_label} termurah adalah '{best[0]}' (total biaya {best[3]:,.2f})."

        # Analisis mendalam
        intervals, dominated = _optimal_intervals(alts)
        runner_up = ranked[1]
        savings_vs_2nd = runner_up[3] - best[3]
        r.analyze(
            "Metodologi Analisis Cost-Volume & Titik Crossover",
            f"Setiap {entity_label} dievaluasi dengan fungsi biaya linear TC(V) = FC + VC × V. "
            f"Titik impas antar dua {entity_label} terjadi pada V* = (FC₂ − FC₁) / (VC₁ − VC₂).",
            [
                f"Pada volume rencana V = {vol:,.2f}: '{best[0]}' menghasilkan biaya terendah = {best[1]:,.2f} + {best[2]:,.2f}×{vol:g} = {best[3]:,.2f} "
                f"(rata-rata {(best[3] / vol) if vol > 0 else 0:,.3f}/unit).",
                f"Keunggulan terhadap peringkat ke-2 ('{runner_up[0]}', biaya {runner_up[3]:,.2f}): hemat {savings_vs_2nd:,.2f} "
                f"({(savings_vs_2nd / runner_up[3] * 100.0) if runner_up[3] > 0 else 0:.2f}%).",
            ],
        )

        env_bullets = [
            f"Volume {lo:,.1f} s.d. {'∞' if hi is None else f'{hi:,.1f}'} unit → pilih '{win}'."
            for lo, hi, win in intervals
        ]
        if dominated:
            env_bullets.append(
                f"{entity_label.capitalize()} terdominasi (tidak pernah termurah pada volume berapa pun): {', '.join(dominated)}."
            )
        r.analyze(
            f"Peta Rentang Volume Optimal ({entity_label.capitalize()} Terbaik)",
            f"Berdasarkan amplop biaya minimum (lower envelope) seluruh {entity_label}:",
            env_bullets,
        )

        # Jarak volume rencana ke batas transisi terdekat
        boundaries = [hi for _, hi, _ in intervals if hi is not None]
        rec_bullets = [f"Gunakan '{best[0]}' selama proyeksi volume berada dalam rentang optimalnya."]
        if boundaries:
            nearest = min(boundaries, key=lambda b: abs(b - vol))
            dist_pct = (abs(nearest - vol) / vol * 100.0) if vol > 0 else 0.0
            direction = "naik" if nearest > vol else "turun"
            rec_bullets.append(
                f"Titik transisi (crossover) terdekat berada pada volume {nearest:,.1f} unit (selisih {abs(nearest - vol):,.1f} unit atau {dist_pct:.1f}% dari rencana). "
                f"Jika permintaan {direction} melewati angka ini, segera tinjau perpindahan ke {entity_label} berikutnya."
            )
        r.analyze("Rekomendasi Pemilihan Kapasitas", "Implikasi strategis bila volume permintaan berubah:", rec_bullets)
        return r
