"""Modul Transportation Problem (NWC, Least Cost, VAM + optimasi MODI)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from optiqm.core import BaseModule, InputError, ModuleResult, ParamSpec, SheetData, SolverError, Table, register
from optiqm.core.parsing import clean_frame, find_column, require_rows, to_float

from .solver import TOL, TransportProblem, balance, initial_solution, modi, total

METHOD_LABEL = {"northwest": "Northwest Corner", "least_cost": "Least Cost", "vogel": "Vogel's Approximation (VAM)"}


@register
class Transportation(BaseModule):
    key = "transportation"
    name = "Transportation"
    category = "Distribusi & Jaringan"
    description = "Optimasi biaya pengiriman dari beberapa sumber ke beberapa tujuan (NWC/LC/VAM + MODI)."
    sheet_prefixes = ("TRANS", "TRANSPORT")
    params = (
        ParamSpec("objective", "Tujuan", "choice", "min", ("min", "max")),
        ParamSpec("initial_method", "Metode Solusi Awal", "choice", "vogel", ("northwest", "least_cost", "vogel")),
    )
    table_hint = ("Kolom pertama: nama sumber. Kolom tengah: tujuan (biaya/unit, isi 'X' atau '-' untuk rute terlarang). "
                  "Kolom terakhir: 'Supply'. Baris terakhir: 'Demand'.")

    def template(self) -> SheetData:
        # Contoh klasik Sunray Transport / Heizer-Render (biaya optimal = 1650? atau total = 165)
        df = pd.DataFrame(
            [["Pabrik A", 5, 4, 3, 100],
             ["Pabrik B", 8, 4, 3, 300],
             ["Pabrik C", 9, 7, 5, 300],
             ["Demand", 300, 200, 200, None]],
            columns=["Source", "Gudang 1", "Gudang 2", "Gudang 3", "Supply"],
        )
        return SheetData(params={"objective": "min", "initial_method": "vogel"}, tables={"main": df})

    def build_problem(self, data: SheetData) -> tuple[TransportProblem, bool]:
        p = self.resolved_params(data)
        df = clean_frame(data.table("main"))
        require_rows(df, 2, "Tabel transportasi")
        sup_col = find_column(df, ["Supply", "Kapasitas", "Pasokan"])
        name_col = df.columns[0]
        dest_cols = [c for c in df.columns if c not in (name_col, sup_col)]
        if not dest_cols:
            raise InputError("Tidak ada kolom tujuan.")

        # Cari baris Demand (baris terakhir atau yang bernama Demand/Permintaan)
        dem_idx = None
        for idx in range(len(df) - 1, -1, -1):
            label = str(df.at[idx, name_col]).strip().lower()
            if label in {"demand", "permintaan", "kebutuhan"}:
                dem_idx = idx
                break
        if dem_idx is None:
            dem_idx = len(df) - 1

        src_rows = [i for i in range(len(df)) if i != dem_idx]
        if not src_rows:
            raise InputError("Minimal harus ada 1 baris sumber.")

        sources = [str(df.at[i, name_col]).strip() for i in src_rows]
        supply = np.array([to_float(df.at[i, sup_col], f"Supply {sources[k]}") for k, i in enumerate(src_rows)])
        demand = np.array([to_float(df.at[dem_idx, c], f"Demand {c}") for c in dest_cols])
        if (supply < 0).any() or (demand < 0).any():
            raise InputError("Nilai Supply dan Demand tidak boleh negatif.")

        cost = np.zeros((len(src_rows), len(dest_cols)))
        prohibited = np.zeros_like(cost, dtype=bool)
        for r, i in enumerate(src_rows):
            for c_idx, col in enumerate(dest_cols):
                v = df.at[i, col]
                if isinstance(v, str) and v.strip().upper() in {"X", "M", "-", "NA"}:
                    prohibited[r, c_idx] = True
                else:
                    cost[r, c_idx] = to_float(v, f"Biaya {sources[r]}->{col}")

        cost_b, sup_b, dem_b, srcs, dests, proh_b, d_row, d_col = balance(
            cost, supply, demand, sources, list(dest_cols), prohibited
        )
        prob = TransportProblem(cost_b, sup_b, dem_b, srcs, dests,
                                maximize=(p["objective"] == "max"), prohibited=proh_b,
                                dummy_row=d_row, dummy_col=d_col)
        return prob, (p["initial_method"], d_row, d_col)

    def solve(self, data: SheetData) -> ModuleResult:
        p = self.resolved_params(data)
        prob, (_, d_row, d_col) = self.build_problem(data)
        alloc0, basis0, init_log = initial_solution(prob, p["initial_method"])
        cost0 = total(prob, alloc0)
        iters = modi(prob, alloc0, basis0)
        opt = iters[-1]
        if prob.prohibited is not None and (prob.prohibited & (opt.alloc > TOL)).any():
            raise SolverError("Tidak ada pengiriman layak tanpa melewati rute terlarang.")
        opt_cost = total(prob, opt.alloc)

        r = ModuleResult()
        label = "Total Keuntungan Optimal" if prob.maximize else "Total Biaya Optimal"
        r.metric(label, opt_cost, highlight=True)
        r.metric(f"Biaya Awal ({METHOD_LABEL[p['initial_method']]})", cost0)
        r.metric("Iterasi MODI", max(0, len(iters) - 1))
        r.metric("Total Unit Dikirim", float(opt.alloc.sum()))
        if d_row:
            r.warnings.append("Total Demand > Supply: ditambahkan baris 'Dummy' (biaya 0).")
        if d_col:
            r.warnings.append("Total Supply > Demand: ditambahkan kolom 'Dummy' (biaya 0).")

        cols = ["Sumber \\ Tujuan", *prob.destinations, "Supply"]
        opt_rows = [[prob.sources[i], *[opt.alloc[i, j] for j in range(len(prob.destinations))], prob.supply[i]]
                    for i in range(len(prob.sources))]
        opt_rows.append(["Demand", *prob.demand.tolist(), float(prob.demand.sum())])
        r.table("Alokasi Pengiriman Optimal", cols, opt_rows)

        # Daftar rute aktif
        routes = []
        for i in range(len(prob.sources)):
            for j in range(len(prob.destinations)):
                if opt.alloc[i, j] > TOL:
                    routes.append([prob.sources[i], prob.destinations[j], opt.alloc[i, j],
                                   prob.cost[i, j], opt.alloc[i, j] * prob.cost[i, j]])
        r.table("Rincian Rute Pengiriman", ["Dari", "Ke", "Jumlah", "Biaya/Unit", "Subtotal"], routes)

        # Langkah: solusi awal + iterasi MODI
        r.steps.append(Table(f"Solusi Awal ({METHOD_LABEL[p['initial_method']]}) — Total: {cost0:,.2f}",
                             ["Langkah", "Sumber", "Tujuan", "Biaya", "Alokasi", "Catatan"], init_log))
        for k, it in enumerate(iters, start=1):
            rows_it = []
            for i, sname in enumerate(prob.sources):
                vals = [f"B ({it.alloc[i, j]:g})" if (i, j) in it.basis else f"Δ={it.index[i, j]:g}"
                        for j in range(len(prob.destinations))]
                rows_it.append([sname, round(float(it.u[i]), 4), *vals])
            note = (f"Masuk {prob.sources[it.entering[0]]}->{prob.destinations[it.entering[1]]}, "
                    f"θ={it.theta:g}, Keluar {prob.sources[it.leaving[0]]}->{prob.destinations[it.leaving[1]]}"
                    if it.entering else "Optimal (semua indeks perbaikan Δ ≥ 0 pada biaya kerja)")
            r.steps.append(Table(f"Iterasi MODI #{k}", ["Sumber", "u_i", *prob.destinations], rows_it, note=note))

        r.chart("Pengiriman per Sumber", "bar", {
            "x": prob.sources,
            "series": [{"name": d, "data": [float(opt.alloc[i, j]) for i in range(len(prob.sources))]}
                       for j, d in enumerate(prob.destinations)],
            "x_label": "Sumber", "y_label": "Unit",
        })
        r.interpretation = (f"Pengiriman optimal menghasilkan {'keuntungan' if prob.maximize else 'biaya'} "
                            f"total {opt_cost:,.2f} dengan {len(routes)} rute aktif.")

        # Analisis mendalam
        real_units = sum(
            float(opt.alloc[i, j])
            for i in range(len(prob.sources))
            for j in range(len(prob.destinations))
            if prob.sources[i] != "Dummy" and prob.destinations[j] != "Dummy"
        )
        avg_unit = opt_cost / real_units if real_units > 0 else 0.0
        diff_init = (opt_cost - cost0) if prob.maximize else (cost0 - opt_cost)
        pct_imp = (abs(diff_init) / abs(cost0) * 100.0) if abs(cost0) > 1e-12 else 0.0
        r.analyze(
            "Metodologi Solusi Awal & Optimasi MODI",
            f"Solusi awal dibangun menggunakan metode {METHOD_LABEL[p['initial_method']]} (nilai awal {cost0:,.2f}), "
            f"kemudian dioptimalkan dengan Metode Distribusi Termodifikasi (MODI / u_i + v_j = c_ij) selama {max(0, len(iters) - 1)} iterasi.",
            [
                f"Perbaikan MODI: {'kenaikan laba' if prob.maximize else 'penghematan biaya'} sebesar {diff_init:,.2f} ({pct_imp:.2f}%) dibandingkan solusi awal.",
                f"Total pengiriman riil: {real_units:,.2f} unit pada {len(routes)} rute aktif dengan rata-rata {'keuntungan' if prob.maximize else 'biaya'} {avg_unit:,.3f}/unit.",
                f"Kondisi keseimbangan: {'Seimbang (Total Supply = Total Demand).' if not (d_row or d_col) else ('Defisit pasokan — baris Dummy menampung kekurangan.' if d_row else 'Surplus kapasitas — kolom Dummy menampung sisa kapasitas tidak terpakai.')}",
            ],
        )

        # Analisis opportunity cost non-basis
        non_basic_deltas = []
        alt_opt = []
        for i in range(len(prob.sources)):
            for j in range(len(prob.destinations)):
                if (i, j) not in opt.basis and not (prob.prohibited is not None and prob.prohibited[i, j]):
                    d_val = float(opt.index[i, j])
                    if abs(d_val) < 1e-7:
                        alt_opt.append(f"{prob.sources[i]} → {prob.destinations[j]}")
                    else:
                        non_basic_deltas.append((d_val, prob.sources[i], prob.destinations[j]))
        non_basic_deltas.sort(key=lambda x: x[0])
        top_route = max(routes, key=lambda x: abs(x[4])) if routes else None
        route_bullets: list[str] = []
        if top_route:
            share = (abs(top_route[4]) / abs(opt_cost) * 100.0) if abs(opt_cost) > 1e-12 else 0.0
            route_bullets.append(
                f"Rute dominan: {top_route[0]} → {top_route[1]} mengirim {top_route[2]:,.2f} unit (tarif {top_route[3]:,.2f}, subtotal {top_route[4]:,.2f} atau {share:.1f}% total)."
            )
        if alt_opt:
            route_bullets.append(
                f"Terdeteksi SOLUSI OPTIMAL ALTERNATIF (Δ = 0) pada rute: {', '.join(alt_opt[:4])}. "
                "Perusahaan memiliki fleksibilitas mengalihkan sebagian aliran ke rute ini tanpa memperburuk nilai total."
            )
        if non_basic_deltas:
            best_d, s_nb, d_nb = non_basic_deltas[0]
            route_bullets.append(
                f"Rute non-aktif paling kompetitif: {s_nb} → {d_nb} (biaya peluang Δ = {best_d:,.3f}/unit). "
                f"Tarif rute ini perlu membaik minimal {best_d:,.3f}/unit agar layak menggantikan rute aktif."
            )
        r.analyze(
            "Bedah Rute Dominan & Biaya Peluang (Opportunity Cost)",
            "Indeks perbaikan Δ pada iterasi MODI terakhir menunjukkan penalti marjinal per unit bila rute non-aktif dipaksa digunakan.",
            route_bullets,
        )

        rec_bullets = [
            f"Prioritaskan kontrak dan penjadwalan armada pada {len(routes)} rute aktif sesuai matriks alokasi optimal.",
        ]
        if d_row:
            rec_bullets.append("Karena Total Demand > Supply, pertimbangkan penambahan kapasitas sumber atau alokasi prioritas ke tujuan dengan tarif termurah.")
        elif d_col:
            rec_bullets.append("Terdapat kapasitas pasokan berlebih (mengalir ke Dummy); evaluasi efisiensi produksi atau ekspansi pasar pada sumber yang tersisa di Dummy.")
        if non_basic_deltas:
            rec_bullets.append(f"Negosiasikan penurunan tarif minimal {non_basic_deltas[0][0]:,.2f}/unit pada rute {non_basic_deltas[0][1]} → {non_basic_deltas[0][2]} bila ingin menjadikannya jalur cadangan tanpa tambahan biaya.")
        r.analyze("Rekomendasi Distribusi & Logistik", "Saran implementasi jaringan distribusi:", rec_bullets)
        return r
