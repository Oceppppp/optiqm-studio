"""Modul Waiting Lines (Teori Antrian)."""

from __future__ import annotations

import pandas as pd

from optiqm.core import BaseModule, InputError, ModuleResult, ParamSpec, SheetData, register

from .solver import md1, mm1, mm1_finite, mms


@register
class WaitingLines(BaseModule):
    key = "waiting_lines"
    name = "Waiting Lines (Antrian)"
    category = "Antrian"
    description = "Analisis kinerja sistem antrian (M/M/1, M/M/s, M/D/1, M/M/1 Populasi Terbatas) + analisis biaya."
    sheet_prefixes = ("QUEUE", "ANTRIAN", "WAIT")
    params = (
        ParamSpec("model", "Model Antrian", "choice", "mm1", ("mm1", "mms", "md1", "mm1_finite_population")),
        ParamSpec("arrival_rate", "Laju Kedatangan (λ)", "number", 2.0),
        ParamSpec("service_rate", "Laju Layanan per Server (μ)", "number", 3.0),
        ParamSpec("servers", "Jumlah Server (s, untuk M/M/s)", "integer", 1),
        ParamSpec("population", "Ukuran Populasi (N, untuk Finite)", "integer", 10),
        ParamSpec("waiting_cost", "Biaya Menunggu / Unit / Waktu (Cw)", "number", 0.0),
        ParamSpec("server_cost", "Biaya Server / Waktu (Cs)", "number", 0.0),
    )
    table_hint = "Atur parameter λ, μ, jumlah server s, atau isi tabel [main] dengan kolom Parameter | Value."

    def template(self) -> SheetData:
        # Arnold's Muffler Shop (Heizer & Render): λ=2/jam, μ=3/jam -> L=2, Lq=4/3, W=1, Wq=2/3
        return SheetData(
            params={"model": "mm1", "arrival_rate": 2, "service_rate": 3, "servers": 1,
                    "population": 10, "waiting_cost": 15, "server_cost": 10},
        )

    def solve(self, data: SheetData) -> ModuleResult:
        p = self.resolved_params_with_table(data)
        lam, mu = float(p["arrival_rate"]), float(p["service_rate"])
        s, N = int(p["servers"]), int(p["population"])
        cw, cs = float(p["waiting_cost"]), float(p["server_cost"])
        if lam <= 0 or mu <= 0:
            raise InputError("Laju kedatangan (λ) dan laju layanan (μ) harus > 0.")
        if cw < 0 or cs < 0:
            raise InputError("Biaya menunggu (Cw) dan biaya server (Cs) tidak boleh negatif.")

        mdl = p["model"]
        if mdl == "mm1":
            res = mm1(lam, mu); eff_s = 1
        elif mdl == "mms":
            res = mms(lam, mu, s); eff_s = s
        elif mdl == "md1":
            res = md1(lam, mu); eff_s = 1
        else:
            res = mm1_finite(lam, mu, N); eff_s = 1

        total_cost = res["l"] * cw + eff_s * cs

        r = ModuleResult()
        r.metric("Utilisasi Server (ρ)", f"{res['rho'] * 100:.2f}%", highlight=True)
        r.metric("Rata-rata dalam Sistem (L)", res["l"])
        r.metric("Rata-rata Antri (Lq)", res["lq"])
        r.metric("Waktu dalam Sistem (W)", res["w"])
        r.metric("Waktu Tunggu Antri (Wq)", res["wq"], highlight=True)
        if cw > 0 or cs > 0:
            r.metric("Total Biaya / Satuan Waktu", total_cost)

        r.table("Metrik Kinerja Antrian", ["Parameter", "Nilai"], [
            ["Utilisasi Sistem (ρ)", res["rho"]],
            ["P(0) — Sistem Kosong", res["p0"]],
            ["P(w) — Pelanggan Harus Menunggu", res["pw"]],
            ["Rata-rata Pelanggan dalam Antrian (Lq)", res["lq"]],
            ["Rata-rata Pelanggan dalam Sistem (L)", res["l"]],
            ["Rata-rata Waktu Tunggu di Antrian (Wq)", res["wq"]],
            ["Rata-rata Waktu di Sistem (W)", res["w"]],
            ["Total Biaya (L·Cw + s·Cs)", total_cost],
        ])

        if res["pn"]:
            cum = 0.0
            p_rows = []
            for n, pn in enumerate(res["pn"]):
                cum += pn
                p_rows.append([n, pn, cum])
            r.table("Distribusi Probabilitas P(n)", ["n Pelanggan", "P(n)", "Kumulatif P(≤ n)"], p_rows)
            r.chart("Distribusi Probabilitas Jumlah Pelanggan P(n)", "bar", {
                "x": [str(n) for n in range(len(res["pn"]))],
                "series": [{"name": "P(n)", "data": res["pn"]}],
                "x_label": "Jumlah Pelanggan (n)", "y_label": "Probabilitas",
            })
        r.interpretation = (f"Model {mdl.upper()}: utilisasi server {res['rho']*100:.1f}%, "
                            f"rata-rata antrean Lq = {res['lq']:.3f} unit dengan waktu tunggu Wq = {res['wq']:.4f}.")

        # Analisis mendalam
        eff_lam = res.get("eff_lam", lam)
        svc_time = 1.0 / mu
        wait_share = (res["wq"] / res["w"] * 100.0) if res["w"] > 1e-12 else 0.0
        r.analyze(
            "Metodologi Teori Antrian & Verifikasi Hukum Little",
            f"Sistem dimodelkan sebagai antrian {mdl.upper()} (λ = {lam:g}, μ = {mu:g}, s = {eff_s}"
            + (f", populasi N = {N}" if mdl == "mm1_finite_population" else "") + ").",
            [
                f"Verifikasi Hukum Little: L = λ_eff × W = {eff_lam:.4g} × {res['w']:.4f} = {eff_lam * res['w']:.4f} (L = {res['l']:.4f}); "
                f"Lq = λ_eff × Wq = {eff_lam * res['wq']:.4f} (Lq = {res['lq']:.4f}).",
                f"Dekomposisi Waktu Sistem (W = {res['w']:.4f}): waktu tunggu antre Wq = {res['wq']:.4f} ({wait_share:.1f}%) + waktu layanan murni 1/μ = {svc_time:.4f} ({100.0 - wait_share:.1f}%).",
                f"Peluang sistem benar-benar kosong P(0) = {res['p0']*100:.2f}%; peluang pelanggan yang datang harus antre P(w) = {res['pw']*100:.2f}%.",
            ],
        )

        rho_pct = res["rho"] * 100.0
        cong_tier = (
            "longgar (<60%): antrean pendek, namun kapasitas server masih banyak menganggur" if rho_pct < 60 else
            "sehat / seimbang (60%–80%): pemanfaatan server baik dengan antrean terkendali" if rho_pct < 80 else
            "padat (80%–90%): antrean mulai sensitif terhadap lonjakan kedatangan sesaat" if rho_pct < 90 else
            "KRITIS (>90%): antrean meledak secara eksponensial akibat faktor 1/(1 − ρ)"
        )
        diag_bullets = [f"Diagnosis Utilisasi (ρ = {rho_pct:.1f}%): kondisi {cong_tier}."]
        if mdl == "mm1":
            md1_wq = (lam / (2.0 * mu * (mu - lam)))
            diag_bullets.append(
                f"Dampak Variabilitas Layanan: jika waktu layanan dibuat konstan/terstandar (M/D/1), waktu antre Wq langsung turun tepat 50% dari {res['wq']:.4f} menjadi {md1_wq:.4f}."
            )
        if cw > 0 or cs > 0:
            w_cost = res["l"] * cw
            s_cost = eff_s * cs
            diag_bullets.append(
                f"Struktur Biaya ({total_cost:,.2f}/satuan waktu): Biaya Tunggu Pelanggan (L·Cw) = {w_cost:,.2f} "
                f"({(w_cost/total_cost*100) if total_cost > 0 else 0:.1f}%) vs Biaya Operasional Server (s·Cs) = {s_cost:,.2f} "
                f"({(s_cost/total_cost*100) if total_cost > 0 else 0:.1f}%)."
            )
        r.analyze(
            "Diagnosis Kemacetan & Analisis Biaya Layanan",
            "Hubungan non-linear antara utilisasi server (ρ) dan panjang antrean (Lq) menentukan tingkat kenyamanan pelanggan dan efisiensi biaya:",
            diag_bullets,
        )

        rec_bullets = []
        if mdl in {"mm1", "mms"} and cw > 0 and cs > 0:
            min_s = int(lam // mu) + 1
            cands = []
            for sk in range(min_s, min_s + 5):
                rk = mms(lam, mu, sk)
                cands.append((rk["l"] * cw + sk * cs, sk, rk["wq"], rk["rho"]))
            best_c, best_s, best_wq, best_rho = min(cands, key=lambda x: x[0])
            if best_s != eff_s:
                rec_bullets.append(
                    f"Optimasi Ekonomi Jumlah Server: menambah/mengubah menjadi s = {best_s} server menurunkan total biaya dari {total_cost:,.2f} menjadi {best_c:,.2f} "
                    f"(hemat {total_cost - best_c:,.2f}/satuan waktu, Wq turun menjadi {best_wq:.4f}, ρ = {best_rho*100:.1f}%)."
                )
            else:
                rec_bullets.append(
                    f"Jumlah server saat ini (s = {eff_s}) sudah OPTIMAL secara biaya (total {total_cost:,.2f}) dibandingkan konfigurasi s = {min_s}..{min_s + 4}."
                )
        if rho_pct >= 85.0:
            rec_bullets.append("Utilisasi ≥ 85%: prioritaskan penambahan kapasitas server, percepatan layanan (μ), atau sistem penjadwalan kedatangan untuk mencegah antrean panjang.")
        elif rho_pct < 50.0:
            rec_bullets.append("Utilisasi < 50%: pertimbangkan penugasan silang (cross-utilization) staf layanan pada jam sepi agar tidak terjadi pemborosan kapasitas.")
        else:
            rec_bullets.append("Pertahankan standar kecepatan layanan saat ini dan pantau pola kedatangan jam puncak (peak-hour arrival rate).")
        r.analyze("Rekomendasi Kapasitas & Jumlah Server", "Saran optimasi operasional antrian:", rec_bullets)
        return r
