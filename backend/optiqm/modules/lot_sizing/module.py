"""Modul Lot Sizing (perbandingan L4L, EOQ, POQ, PPB, Wagner-Whitin)."""

from __future__ import annotations

import pandas as pd

from optiqm.core import BaseModule, InputError, ModuleResult, ParamSpec, SheetData, register
from optiqm.core.parsing import clean_frame, find_column, require_rows, to_float

from .solver import fixed_eoq, lot_for_lot, part_period_balancing, periodic_order_qty, wagner_whitin

ALGORITHMS = {
    "wagner_whitin": ("Wagner-Whitin (Optimal)", wagner_whitin),
    "lot_for_lot": ("Lot-for-Lot", lot_for_lot),
    "eoq": ("EOQ", fixed_eoq),
    "poq": ("Periodic Order Quantity (POQ)", periodic_order_qty),
    "part_period_balancing": ("Part-Period Balancing (PPB)", part_period_balancing),
}


@register
class LotSizing(BaseModule):
    key = "lot_sizing"
    name = "Lot Sizing"
    category = "Perencanaan Produksi"
    description = "Membandingkan metode penentuan ukuran lot (L4L, EOQ, POQ, PPB, dan Wagner-Whitin optimal)."
    sheet_prefixes = ("LOT", "LOTSIZING")
    params = (
        ParamSpec("method", "Metode Utama", "choice", "wagner_whitin",
                  ("wagner_whitin", "lot_for_lot", "eoq", "poq", "part_period_balancing")),
        ParamSpec("setup_cost", "Biaya Setup / Pesan (S)", "number", 100.0),
        ParamSpec("holding_cost", "Biaya Simpan per Unit/Periode (H)", "number", 1.0),
    )
    table_hint = "Kolom: Period, Requirement (atau Net_Requirement)."

    def template(self) -> SheetData:
        # Contoh klasik Heizer & Render (10 minggu, S=100, H=1) -> L4L=1000, EOQ=?, PPB=510, WW=500
        reqs = [35, 30, 40, 0, 10, 40, 30, 0, 30, 55]
        df = pd.DataFrame([[f"W{i + 1}", r] for i, r in enumerate(reqs)], columns=["Period", "Requirement"])
        return SheetData(params={"method": "wagner_whitin", "setup_cost": 100, "holding_cost": 1}, tables={"main": df})

    def solve(self, data: SheetData) -> ModuleResult:
        p = self.resolved_params(data)
        S, H = float(p["setup_cost"]), float(p["holding_cost"])
        if S < 0 or H <= 0:
            raise InputError("Biaya setup harus >= 0 dan biaya simpan H harus > 0.")

        df = clean_frame(data.table("main"))
        require_rows(df, 1, "Tabel kebutuhan per periode")
        c_per = find_column(df, ["Period", "Periode", "Week", "Minggu"], required=False) or df.columns[0]
        c_req = find_column(df, ["Requirement", "Net_Requirement", "Demand", "Kebutuhan"])
        periods = [str(v).strip() for v in df[c_per]]
        demands = [to_float(df.at[i, c_req], f"Kebutuhan {periods[i]}") for i in range(len(df))]
        if any(d < 0 for d in demands):
            raise InputError("Kebutuhan (Requirement) pada setiap periode tidak boleh negatif.")

        all_res = {k: fn(demands, S, H) for k, (_, fn) in ALGORITHMS.items()}
        chosen = all_res[p["method"]]
        chosen_label = ALGORITHMS[p["method"]][0]

        r = ModuleResult()
        r.metric(f"Total Biaya ({chosen_label})", chosen["total_cost"], highlight=True)
        r.metric("Biaya Setup", chosen["setup_cost"])
        r.metric("Biaya Simpan", chosen["hold_cost"])
        r.metric("Jumlah Pemesanan", sum(1 for q in chosen["orders"] if q > 0))

        r.table(f"Jadwal Lot Sizing — {chosen_label}",
                ["Periode", "Kebutuhan", "Ukuran Pesan (Order)", "Stok Akhir"],
                [[periods[i], demands[i], chosen["orders"][i], chosen["ending"][i]] for i in range(len(periods))])
        r.table("Perbandingan Semua Metode",
                ["Metode", "Biaya Setup", "Biaya Simpan", "Total Biaya", "Jumlah Order"],
                [[lbl, all_res[k]["setup_cost"], all_res[k]["hold_cost"], all_res[k]["total_cost"],
                  sum(1 for q in all_res[k]["orders"] if q > 0)] for k, (lbl, _) in ALGORITHMS.items()])
        r.chart("Perbandingan Total Biaya", "bar", {
            "x": [lbl for lbl, _ in ALGORITHMS.values()],
            "series": [{"name": "Total Biaya", "data": [all_res[k]["total_cost"] for k in ALGORITHMS]}],
            "x_label": "Metode", "y_label": "Biaya",
        })
        best_k = min(ALGORITHMS, key=lambda k: all_res[k]["total_cost"])
        r.interpretation = (f"Metode {chosen_label} menghasilkan total biaya {chosen['total_cost']:,.2f}. "
                            f"Terbaik keseluruhan: {ALGORITHMS[best_k][0]} ({all_res[best_k]['total_cost']:,.2f}).")

        # Analisis mendalam
        ww_cost = all_res["wagner_whitin"]["total_cost"]
        l4l_cost = all_res["lot_for_lot"]["total_cost"]
        n_ord = sum(1 for q in chosen["orders"] if q > 0)
        avg_ord = (sum(chosen["orders"]) / n_ord) if n_ord > 0 else 0.0
        avg_end = sum(chosen["ending"]) / len(periods)
        r.analyze(
            "Metodologi Lot Sizing Dinamis & Garansi Optimalitas",
            f"Dari {len(periods)} periode kebutuhan (total {sum(demands):,.0f} unit, S={S:g}, H={H:g}, EPP = S/H = {S/H:,.2f} unit-periode), "
            "sistem mengevaluasi 5 metode sekaligus dengan Wagner-Whitin (Dynamic Programming) sebagai patokan biaya minimum global.",
            [
                f"Metode aktif '{chosen_label}': Total Biaya = {chosen['total_cost']:,.2f} (Setup = {chosen['setup_cost']:,.2f} untuk {n_ord} kali pesan; Simpan = {chosen['hold_cost']:,.2f}).",
                f"Rata-rata ukuran sekali pesan = {avg_ord:,.2f} unit; rata-rata stok akhir tersimpan = {avg_end:,.2f} unit/periode.",
            ],
        )

        ranked = sorted(ALGORITHMS.items(), key=lambda kv: all_res[kv[0]]["total_cost"])
        cmp_bullets = [
            f"#{idx} {lbl}: total {all_res[k]['total_cost']:,.2f} "
            f"(selisih {all_res[k]['total_cost'] - ww_cost:+,.2f} atau {((all_res[k]['total_cost'] - ww_cost)/ww_cost*100) if ww_cost > 0 else 0:+.1f}% di atas Wagner-Whitin)."
            for idx, (k, (lbl, _)) in enumerate(ranked, start=1)
        ]
        if l4l_cost > 0:
            sav_l4l = l4l_cost - chosen["total_cost"]
            cmp_bullets.append(
                f"Dibanding kebijakan Lot-for-Lot ({l4l_cost:,.2f}), metode '{chosen_label}' menghemat {sav_l4l:,.2f} ({sav_l4l / l4l_cost * 100:.1f}%)."
            )
        r.analyze(
            "Peringkat Efisiensi 5 Metode Lot Sizing",
            "Perbandingan biaya total mengungkap seberapa dekat metode heuristik (EOQ, POQ, PPB) terhadap batas optimal Wagner-Whitin:",
            cmp_bullets,
        )

        gap_ww = chosen["total_cost"] - ww_cost
        rec_bullets = []
        if gap_ww > 1e-6:
            rec_bullets.append(f"Metode '{chosen_label}' lebih mahal {gap_ww:,.2f} dibanding Wagner-Whitin; pertimbangkan beralih ke Wagner-Whitin atau '{ranked[0][1][0]}'.")
        else:
            rec_bullets.append(f"Metode '{chosen_label}' telah mencapai biaya minimum global ({ww_cost:,.2f}).")
        rec_bullets.append(
            "Dalam lingkungan MRP dengan jadwal berubah-ubah (rolling horizon), POQ atau Part-Period Balancing (PPB) sering menjadi kompromi praktis "
            "untuk mengurangi efek 'system nervousness' jika selisih biayanya tipis dari Wagner-Whitin."
        )
        r.analyze("Rekomendasi Kebijakan Lot Sizing", "Pertimbangan implementasi di sistem MRP/PPIC:", rec_bullets)
        return r
