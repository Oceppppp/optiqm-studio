"""Modul Productivity (Single & Multifactor Productivity)."""

from __future__ import annotations

import pandas as pd

from optiqm.core import BaseModule, InputError, ModuleResult, SheetData, register
from optiqm.core.parsing import clean_frame, require_rows, to_float


@register
class Productivity(BaseModule):
    key = "productivity"
    name = "Productivity"
    category = "Produktivitas & Kerja"
    description = "Menghitung produktivitas tunggal (single-factor) dan multifaktor serta perubahan antar-periode."
    sheet_prefixes = ("PROD", "PRODUKTIVITAS")
    table_hint = ("Kolom pertama: nama komponen ('Output' untuk baris keluaran, selain itu dianggap input). "
                  "Kolom berikutnya: satu kolom per periode (atau faktor biaya), mis. Periode_1, Periode_2.")

    def template(self) -> SheetData:
        # Collins Title (Heizer & Render)
        df = pd.DataFrame(
            [["Output (Unit)", 1000, 1100],
             ["Tenaga Kerja ($)", 400, 450],
             ["Material ($)", 300, 310],
             ["Energi & Overhead ($)", 100, 105]],
            columns=["Komponen", "Periode 1", "Periode 2"],
        )
        return SheetData(tables={"main": df})

    def solve(self, data: SheetData) -> ModuleResult:
        df = clean_frame(data.table("main"))
        require_rows(df, 2, "Tabel produktivitas (minimal 1 baris Output + 1 baris Input)")
        periods = list(df.columns[1:])
        if not periods:
            raise InputError("Minimal harus ada 1 kolom periode.")

        out_vals = None
        inputs = []
        for i in range(len(df)):
            nm = str(df.iloc[i, 0]).strip()
            vals = [to_float(df.at[i, p], f"{nm}/{p}") for p in periods]
            if any(v < 0 for v in vals):
                raise InputError(f"Nilai pada baris '{nm}' tidak boleh negatif.")
            is_out = ("output" in nm.lower() or "keluaran" in nm.lower())
            if (is_out or i == 0) and out_vals is None:
                out_vals = vals
            else:
                inputs.append((nm, vals))
        if not inputs or out_vals is None:
            raise InputError("Harus ada baris Output dan minimal satu baris Input.")

        tot_in = [sum(vals[j] for _, vals in inputs) for j in range(len(periods))]
        mfp = [out_vals[j] / tot_in[j] if tot_in[j] > 0 else 0.0 for j in range(len(periods))]

        rows_out = []
        sfp_changes = []
        for nm, vals in inputs:
            sfp = [out_vals[j] / vals[j] if vals[j] > 0 else 0.0 for j in range(len(periods))]
            chg = ((sfp[-1] - sfp[0]) / sfp[0] * 100.0) if len(periods) > 1 and sfp[0] > 0 else 0.0
            sfp_changes.append((nm, sfp, chg, vals))
            rows_out.append([f"Single-Factor ({nm})", *sfp, f"{chg:+.2f}%" if len(periods) > 1 else "-"])
        mfp_chg = ((mfp[-1] - mfp[0]) / mfp[0] * 100.0) if len(periods) > 1 and mfp[0] > 0 else 0.0
        rows_out.append(["Multifactor Productivity", *mfp, f"{mfp_chg:+.2f}%" if len(periods) > 1 else "-"])

        r = ModuleResult()
        for per, val in zip(periods, mfp):
            r.metric(f"MFP ({per})", val, highlight=True)
        if len(periods) > 1:
            r.metric("Perubahan MFP", f"{mfp_chg:+.2f}%", highlight=True)
        r.table("Analisis Produktivitas", ["Indikator", *periods, "Perubahan (%)"], rows_out)
        r.chart("Produktivitas Multifaktor per Periode", "bar", {
            "x": periods, "series": [{"name": "MFP", "data": mfp}],
            "x_label": "Periode", "y_label": "Output / Total Input",
        })
        r.interpretation = f"Produktivitas multifaktor: {', '.join(f'{p}={v:.4f}' for p, v in zip(periods, mfp))}."

        # Analisis mendalam
        r.analyze(
            "Metodologi Produktivitas Tunggal (SFP) & Multifaktor (MFP)",
            "Single-Factor Productivity mengukur output per 1 jenis input (Output / Input_i), sedangkan Multifactor Productivity (MFP) "
            "mengukur efisiensi gabungan seluruh sumber daya (Output / ΣInput).",
            [
                f"Periode '{per}': Output = {out_vals[j]:,.2f}, Total Input = {tot_in[j]:,.2f} → MFP = {mfp[j]:.4f} unit output per satuan input."
                for j, per in enumerate(periods)
            ],
        )

        dom_in = max(sfp_changes, key=lambda x: x[3][-1])
        dom_share = (dom_in[3][-1] / tot_in[-1] * 100.0) if tot_in[-1] > 0 else 0.0
        drv_bullets = [
            f"Komponen biaya input terbesar pada '{periods[-1]}': '{dom_in[0]}' ({dom_in[3][-1]:,.2f} atau {dom_share:.1f}% dari total input)."
        ]
        if len(periods) > 1:
            out_g = ((out_vals[-1] - out_vals[0]) / out_vals[0] * 100.0) if out_vals[0] > 0 else 0.0
            in_g = ((tot_in[-1] - tot_in[0]) / tot_in[0] * 100.0) if tot_in[0] > 0 else 0.0
            best_f = max(sfp_changes, key=lambda x: x[2])
            worst_f = min(sfp_changes, key=lambda x: x[2])
            drv_bullets.append(
                f"Pertumbuhan Output ({out_g:+.2f}%) vs Total Input ({in_g:+.2f}%) menghasilkan perubahan MFP = {mfp_chg:+.2f}% "
                f"({'MENINGKAT' if mfp_chg > 0 else ('MENURUN' if mfp_chg < 0 else 'STAGNAN')})."
            )
            drv_bullets.append(f"Pendorong efisiensi terbaik: '{best_f[0]}' (SFP berubah {best_f[2]:+.2f}%); faktor paling tertinggal: '{worst_f[0]}' ({worst_f[2]:+.2f}%).")
        r.analyze("Bedah Struktur Input & Penggerak Produktivitas", "Menguraikan sumber peningkatan atau penurunan efisiensi antar-periode:", drv_bullets)

        rec_bullets = []
        if len(periods) > 1 and mfp_chg < 0:
            rec_bullets.append(f"Produktivitas multifaktor menurun ({mfp_chg:.2f}%) karena pertumbuhan biaya input melampaui pertumbuhan output — audit pemborosan pada '{min(sfp_changes, key=lambda x: x[2])[0]}'.")
        elif len(periods) > 1:
            rec_bullets.append(f"Produktivitas multifaktor tumbuh positif ({mfp_chg:+.2f}%); pertahankan praktik efisiensi pada '{max(sfp_changes, key=lambda x: x[2])[0]}'.")
        rec_bullets.append(f"Karena '{dom_in[0]}' menyerap {dom_share:.1f}% total input, perbaikan efisiensi sekecil 5% di faktor ini akan berdampak paling besar terhadap kenaikan MFP keseluruhan.")
        r.analyze("Rekomendasi Peningkatan Produktivitas", "Prioritas program efisiensi operasional:", rec_bullets)
        return r
