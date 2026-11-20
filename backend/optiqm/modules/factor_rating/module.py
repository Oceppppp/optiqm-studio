"""Modul Factor Rating (Pemilihan Lokasi berbasis bobot)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from optiqm.core import BaseModule, InputError, ModuleResult, SheetData, register
from optiqm.core.parsing import clean_frame, find_column, require_rows, to_float


@register
class FactorRating(BaseModule):
    key = "factor_rating"
    name = "Factor Rating (Pemilihan Lokasi)"
    category = "Lokasi & Tata Letak"
    description = "Mengevaluasi alternatif lokasi menggunakan skor terbobot untuk beberapa faktor penilaian."
    sheet_prefixes = ("FR", "FACTOR", "LOKASI")
    table_hint = "Kolom: Factor, Weight, diikuti kolom skor untuk masing-masing kandidat lokasi."

    def template(self) -> SheetData:
        # Five Flags Florida (Heizer & Render): France 70.4, Denmark 68.0
        df = pd.DataFrame(
            [["Ketersediaan Tenaga Kerja", 0.25, 70, 60],
             ["Rasio Populasi/Kendaraan", 0.05, 50, 60],
             ["Pendapatan per Kapita", 0.10, 85, 80],
             ["Struktur Pajak", 0.39, 75, 70],
             ["Pendidikan & Kesehatan", 0.21, 60, 70]],
            columns=["Factor", "Weight", "Prancis", "Denmark"],
        )
        return SheetData(tables={"main": df})

    def solve(self, data: SheetData) -> ModuleResult:
        df = clean_frame(data.table("main"))
        require_rows(df, 1, "Tabel Factor Rating")
        c_fac = find_column(df, ["Factor", "Faktor", "Criteria", "Kriteria"], required=False) or df.columns[0]
        c_wt = find_column(df, ["Weight", "Bobot", "W"])
        locs = [c for c in df.columns if c not in (c_fac, c_wt)]
        if not locs:
            raise InputError("Minimal harus ada 1 kolom kandidat lokasi.")

        factors = [str(x).strip() for x in df[c_fac]]
        weights = np.array([to_float(df.at[i, c_wt], f"Weight {factors[i]}") for i in range(len(df))], dtype=float)
        if (weights < 0).any() or weights.sum() <= 0:
            raise InputError("Bobot harus non-negatif dan total > 0.")
        norm_w = weights / weights.sum() if abs(weights.sum() - 1.0) > 1e-4 else weights

        scores = np.array([[to_float(df.at[i, l], f"{factors[i]}/{l}") for l in locs] for i in range(len(df))])
        weighted = scores * norm_w[:, None]
        totals = weighted.sum(axis=0)
        best_idx = int(np.argmax(totals))

        r = ModuleResult()
        if abs(weights.sum() - 1.0) > 1e-4:
            r.warnings.append(f"Total bobot = {weights.sum():g} (bukan 1); bobot dinormalisasi otomatis.")
        r.metric("Lokasi Terbaik", locs[best_idx], highlight=True)
        r.metric("Skor Terbobot Tertinggi", float(totals[best_idx]), highlight=True)

        rows_out = [[factors[i], float(norm_w[i]), *[float(weighted[i, j]) for j in range(len(locs))]]
                    for i in range(len(factors))]
        rows_out.append(["TOTAL SKOR TERBOBOT", float(norm_w.sum()), *[float(t) for t in totals]])
        r.table("Skor Terbobot per Faktor", ["Faktor", "Bobot", *locs], rows_out)
        r.chart("Perbandingan Skor Total Lokasi", "bar", {
            "x": locs, "series": [{"name": "Skor Terbobot", "data": totals.tolist()}],
            "x_label": "Lokasi", "y_label": "Skor Total",
        })
        r.interpretation = f"Lokasi terbaik adalah '{locs[best_idx]}' dengan skor terbobot {totals[best_idx]:,.2f}."

        # Analisis mendalam
        ranked = sorted(range(len(locs)), key=lambda j: totals[j], reverse=True)
        top_w_idx = int(np.argmax(norm_w))
        r.analyze(
            "Metodologi Factor Rating (Weighted Scoring)",
            f"Sebanyak {len(locs)} kandidat lokasi dinilai pada {len(factors)} faktor dengan rumus Skor_j = Σ(w_i × skor_ij) "
            f"(total bobot = {float(norm_w.sum()):.4f}).",
            [
                f"Faktor dengan bobot terbesar: '{factors[top_w_idx]}' ({norm_w[top_w_idx] * 100:.1f}% dari keputusan).",
                "Peringkat lokasi: " + " > ".join(f"{locs[j]} ({totals[j]:,.2f})" for j in ranked) + ".",
            ],
        )

        driver_bullets = []
        if len(locs) > 1:
            second_idx = ranked[1]
            margin = float(totals[best_idx] - totals[second_idx])
            margin_pct = (margin / totals[second_idx] * 100.0) if abs(totals[second_idx]) > 1e-12 else 0.0
            diffs = [float(weighted[i, best_idx] - weighted[i, second_idx]) for i in range(len(factors))]
            best_f_i = int(np.argmax(diffs))
            worst_f_i = int(np.argmin(diffs))
            driver_bullets.append(
                f"Margin keunggulan '{locs[best_idx]}' atas peringkat ke-2 ('{locs[second_idx]}') = +{margin:,.2f} poin ({margin_pct:+.2f}%)."
            )
            driver_bullets.append(
                f"Faktor pendorong utama kemenangan: '{factors[best_f_i]}' (bobot {norm_w[best_f_i]*100:.1f}%, menyumbang keunggulan +{diffs[best_f_i]:,.2f} poin terbobot)."
            )
            if diffs[worst_f_i] < -1e-9:
                driver_bullets.append(
                    f"Titik kelemahan relatif: pada faktor '{factors[worst_f_i]}', '{locs[best_idx]}' tertinggal {diffs[worst_f_i]:,.2f} poin terbobot dari '{locs[second_idx]}'."
                )
        else:
            top_contrib = int(np.argmax(weighted[:, 0]))
            driver_bullets.append(f"Penyumbang skor terbesar adalah faktor '{factors[top_contrib]}' ({weighted[top_contrib, 0]:,.2f} poin).")
        r.analyze("Bedah Faktor Penentu & Keunggulan Kompetitif", "Analisis kontribusi skor terbobot antar kandidat lokasi teratas:", driver_bullets)

        rec_bullets = [f"Pilih '{locs[best_idx]}' sebagai lokasi utama karena meraih skor komposit tertinggi ({totals[best_idx]:,.2f})."]
        if len(locs) > 1 and totals[ranked[1]] > 0 and (totals[best_idx] - totals[ranked[1]]) / totals[ranked[1]] < 0.05:
            rec_bullets.append(
                f"Selisih terhadap '{locs[ranked[1]]}' relatif tipis (<5%): lakukan uji sensitivitas bobot dan lengkapi dengan evaluasi kuantitatif biaya (Location Break-Even) sebelum keputusan final."
            )
        else:
            rec_bullets.append("Keunggulan skor cukup jelas; pastikan data survei pada faktor berbobot terbesar telah terverifikasi secara objektif.")
        r.analyze("Rekomendasi Keputusan Lokasi", "Tindak lanjut validasi pemilihan lokasi:", rec_bullets)
        return r
