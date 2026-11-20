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
        emv = eol = None
        best_i = None
        evwpi = evpi = None
        if probs is not None:
            if (probs < 0).any():
                raise InputError("Nilai probabilitas tidak boleh negatif.")
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
        if probs is not None and emv is not None and eol is not None:
            alt_cols.extend(["EMV", "EOL"])
            for i in range(len(alts)):
                alt_tbl[i].extend([float(emv[i]), float(eol[i])])
        r.table("Evaluasi per Alternatif", alt_cols, alt_tbl)
        r.table("Tabel Opportunity Loss (Regret)", ["Alternatif", *states, "Max Regret"],
                [[alts[i], *regret[i].tolist(), max_regret[i]] for i in range(len(alts))])
        if probs is not None and emv is not None:
            r.chart("Perbandingan EMV Alternatif", "bar", {
                "x": alts, "series": [{"name": "EMV", "data": emv.tolist()}],
                "x_label": "Alternatif", "y_label": "EMV",
            })
        r.interpretation = (f"Berdasarkan EMV, alternatif terbaik adalah '{alts[best_i]}' (EMV={float(emv[best_i]):,.2f})."
                            if probs is not None and emv is not None and best_i is not None
                            else f"Berdasarkan Minimax Regret, pilih '{alts[int(np.argmin(max_regret))]}'.")

        # Analisis mendalam
        # Cek dominansi
        dominated = []
        for i in range(len(alts)):
            for j in range(len(alts)):
                if i == j:
                    continue
                better_eq = (M[j] >= M[i]).all() if is_profit else (M[j] <= M[i]).all()
                strictly = (M[j] > M[i]).any() if is_profit else (M[j] < M[i]).any()
                if better_eq and strictly:
                    dominated.append(f"'{alts[i]}' terdominasi oleh '{alts[j]}'")
                    break

        votes: dict[str, int] = {}
        for row in crit_rows:
            votes[row[1]] = votes.get(row[1], 0) + 1
        top_vote_alt, top_votes = max(votes.items(), key=lambda x: x[1])
        r.analyze(
            "Metodologi Keputusan di Bawah Ketidakpastian & Risiko",
            f"Tabel mengevaluasi {len(alts)} alternatif terhadap {len(states)} kondisi alam ({', '.join(states)}) "
            f"dengan tipe nilai '{'Profit (maksimasi)' if is_profit else 'Cost (minimasi)'}' menggunakan {len(crit_rows)} kriteria keputusan.",
            [
                f"Konsensus Kriteria: '{top_vote_alt}' paling sering terpilih ({top_votes} dari {len(crit_rows)} kriteria).",
                f"Uji Dominansi: {'; '.join(dominated) if dominated else 'Tidak ada alternatif yang terdominasi ketat (semua alternatif efisien Pareto pada minimal satu kondisi).'}",
            ],
        )

        detail_bullets = [
            f"Profil Optimis (Maximax/Minimin) memilih '{crit_rows[0][1]}' ({crit_rows[0][2]:,.2f}), "
            f"sedangkan profil Konservatif/Pesimis (Maximin/Minimax) memilih '{crit_rows[1][1]}' ({crit_rows[1][2]:,.2f}).",
            f"Kriteria Minimax Regret memilih '{crit_rows[4][1]}' untuk membatasi penyesalan maksimum maksimal sebesar {crit_rows[4][2]:,.2f}.",
        ]
        if probs is not None and emv is not None and eol is not None and best_i is not None and evwpi is not None and evpi is not None:
            sorted_emv = sorted(range(len(alts)), key=lambda i: emv[i], reverse=is_profit)
            margin_txt = (
                f"unggul {abs(float(emv[sorted_emv[0]] - emv[sorted_emv[1]])):,.2f} dari runner-up '{alts[sorted_emv[1]]}'"
                if len(alts) > 1 else ""
            )
            detail_bullets.append(
                f"Dengan probabilitas kondisi ({', '.join(f'{s}:{pr:.2g}' for s, pr in zip(states, probs))}), "
                f"EMV terbaik adalah '{alts[best_i]}' = {float(emv[best_i]):,.2f} ({margin_txt})."
            )
            detail_bullets.append(
                f"Verifikasi EVPI = Min EOL: EVwPI ({evwpi:,.2f}) − EMV* ({float(emv[best_i]):,.2f}) = {evpi:,.2f} ≡ Min EOL ({float(eol.min()):,.2f})."
            )
        r.analyze(
            "Bedah Profil Risiko & Nilai Informasi Sempurna (EVPI)",
            "Perbedaan pilihan antar kriteria mencerminkan sensitivitas keputusan terhadap sikap risiko (risk-seeking vs risk-averse):",
            detail_bullets,
        )

        rec_bullets = []
        if probs is not None and best_i is not None and evpi is not None:
            rec_bullets.append(f"Untuk pengambil keputusan netral risiko (risk-neutral), pilih '{alts[best_i]}' karena memaksimalkan nilai ekspektasi jangka panjang (EMV).")
            rec_bullets.append(
                f"Batas atas anggaran riset/konsultasi pasar: JANGAN membayar lebih dari EVPI = {evpi:,.2f} untuk informasi tambahan "
                "karena bahkan ramalan sempurna tidak bisa menambah nilai ekspektasi melebihi angka tersebut."
            )
        else:
            rec_bullets.append(f"Tanpa probabilitas historis, gunakan '{crit_rows[2][1]}' (Hurwicz α={alpha:g}) atau '{crit_rows[4][1]}' (Minimax Regret) sesuai toleransi risiko manajemen.")
            rec_bullets.append("Kumpulkan estimasi probabilitas kondisi pasar dan tambahkan baris 'Probability' untuk membuka analisis EMV dan EVPI.")
        r.analyze("Rekomendasi Pengambilan Keputusan", "Panduan eksekusi keputusan berdasarkan profil risiko:", rec_bullets)
        return r
