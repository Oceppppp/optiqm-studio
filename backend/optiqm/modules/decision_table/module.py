"""Modul Decision Table (Maximax, Maximin, Hurwicz, Laplace, Minimax Regret, EMV, EVPI)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from optiqm.core import BaseModule, InputError, ModuleResult, ParamSpec, SheetData, register
from optiqm.core.parsing import clean_frame, require_rows, to_float


@register
class DecisionTable(BaseModule):
    key = "decision_table"
    name = "Decision Table"
    category = "Analisis Keputusan"
    description = "Pengambilan keputusan di bawah ketidakpastian & risiko (Maximax, Maximin, Hurwicz, Laplace, Minimax Regret, EMV, EVPI)."
    sheet_prefixes = ("DT", "DECISION", "KEPUTUSAN")
    params = (
        ParamSpec("payoff_type", "Tipe Nilai", "choice", "profit", ("profit", "cost")),
        ParamSpec("hurwicz_alpha", "Koefisien Optimisme Hurwicz (α, 0..1)", "number", 0.7),
    )
    table_hint = ("Kolom pertama: nama alternatif. Kolom lainnya: state of nature (kondisi). "
                  "Tambahkan baris opsional bernama 'Probability' di bawah untuk menghitung EMV & EVPI.")

    def template(self) -> SheetData:
        # Thompson Lumber (Heizer & Render): Favorable 0.5, Unfavorable 0.5 -> EMV Large=10k, Small=40k, DoNothing=0
        df = pd.DataFrame(
            [["Pabrik Besar", 200000, -180000],
             ["Pabrik Kecil", 100000, -20000],
             ["Tidak Membangun", 0, 0],
             ["Probability", 0.5, 0.5]],
            columns=["Alternative", "Pasar Baik", "Pasar Buruk"],
        )
        return SheetData(params={"payoff_type": "profit", "hurwicz_alpha": 0.7}, tables={"main": df})

    def solve(self, data: SheetData) -> ModuleResult:
        p = self.resolved_params(data)
        is_profit = p["payoff_type"] == "profit"
        alpha = float(p["hurwicz_alpha"])
        if not (0.0 <= alpha <= 1.0):
            raise InputError("Koefisien Hurwicz α harus antara 0 dan 1.")

        df = clean_frame(data.table("main"))
        require_rows(df, 1, "Tabel keputusan")
        name_col = df.columns[0]
        states = list(df.columns[1:])
        if not states:
            raise InputError("Minimal harus ada 1 kolom state of nature.")

        probs = None
        alt_rows = []
        for i in range(len(df)):
            nm = str(df.at[i, name_col]).strip()
            vals = [to_float(df.at[i, s], f"{nm}/{s}") for s in states]
            if nm.lower() in {"probability", "probabilitas", "prob", "p"}:
                probs = np.array(vals)
            else:
                alt_rows.append((nm, vals))
        if not alt_rows:
            raise InputError("Minimal harus ada 1 alternatif keputusan.")

        alts = [a[0] for a in alt_rows]
        M = np.array([a[1] for a in alt_rows], dtype=float)
        pick = (lambda arr: int(np.argmax(arr))) if is_profit else (lambda arr: int(np.argmin(arr)))

        row_max = M.max(axis=1)
        row_min = M.min(axis=1)
        best_each_state = M.max(axis=0) if is_profit else M.min(axis=0)
        regret = (best_each_state - M) if is_profit else (M - best_each_state)
        max_regret = regret.max(axis=1)
        laplace = M.mean(axis=1)
        hurwicz = alpha * (row_max if is_profit else row_min) + (1.0 - alpha) * (row_min if is_profit else row_max)

        crit_rows = [
            ["Optimis (Maximax / Minimin)", alts[pick(row_max if is_profit else row_min)],
             float((row_max if is_profit else row_min)[pick(row_max if is_profit else row_min)])],
            ["Pesimis (Maximin / Minimax)", alts[pick(row_min if is_profit else row_max)],
             float((row_min if is_profit else row_max)[pick(row_min if is_profit else row_max)])],
            [f"Hurwicz (α={alpha:g})", alts[pick(hurwicz)], float(hurwicz[pick(hurwicz)])],
            ["Equally Likely (Laplace)", alts[pick(laplace)], float(laplace[pick(laplace)])],
            ["Minimax Regret", alts[int(np.argmin(max_regret))], float(max_regret.min())],
        ]

        r = ModuleResult()
        if probs is not None:
            if abs(probs.sum() - 1.0) > 1e-3:
                raise InputError(f"Jumlah probabilitas harus = 1 (saat ini {probs.sum():.4f}).")
            emv = M @ probs
            eol = regret @ probs
            best_i = pick(emv)
            evwpi = float(best_each_state @ probs)
            evpi = abs(evwpi - float(emv[best_i]))
            crit_rows.append(["Expected Monetary Value (EMV)", alts[best_i], float(emv[best_i])])
            crit_rows.append(["Min Expected Opportunity Loss (EOL)", alts[int(np.argmin(eol))], float(eol.min())])
            r.metric("Keputusan Terbaik (EMV)", alts[best_i], highlight=True)
            r.metric("EMV Terbaik", float(emv[best_i]), highlight=True)
            r.metric("EV with Perfect Info", evwpi)
            r.metric("EVPI (Nilai Informasi Sempurna)", evpi)
        else:
            r.metric("Rekomendasi Hurwicz", alts[pick(hurwicz)], highlight=True)
            r.metric("Rekomendasi Minimax Regret", alts[int(np.argmin(max_regret))])

        r.table("Ringkasan Kriteria Keputusan", ["Kriteria", "Alternatif Terbaik", "Nilai"], crit_rows)
        alt_cols = ["Alternatif", "Min", "Max", "Laplace", f"Hurwicz ({alpha:g})", "Max Regret"]
        alt_tbl = [[alts[i], row_min[i], row_max[i], laplace[i], hurwicz[i], max_regret[i]] for i in range(len(alts))]
        if probs is not None:
            alt_cols.extend(["EMV", "EOL"])
            for i in range(len(alts)):
                alt_tbl[i].extend([float((M @ probs)[i]), float((regret @ probs)[i])])
        r.table("Evaluasi per Alternatif", alt_cols, alt_tbl)
        r.table("Tabel Opportunity Loss (Regret)", ["Alternatif", *states, "Max Regret"],
                [[alts[i], *regret[i].tolist(), max_regret[i]] for i in range(len(alts))])
        if probs is not None:
            r.chart("Perbandingan EMV Alternatif", "bar", {
                "x": alts, "series": [{"name": "EMV", "data": (M @ probs).tolist()}],
                "x_label": "Alternatif", "y_label": "EMV",
            })
        r.interpretation = (f"Berdasarkan EMV, alternatif terbaik adalah '{alts[pick(M @ probs)]}' (EMV={float((M @ probs).max() if is_profit else (M @ probs).min()):,.2f})."
                            if probs is not None else f"Berdasarkan Minimax Regret, pilih '{alts[int(np.argmin(max_regret))]}'.")
        return r
