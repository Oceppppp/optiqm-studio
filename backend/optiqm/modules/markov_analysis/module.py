"""Modul Markov Analysis (multi-periode, steady-state, absorbing chain)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from optiqm.core import BaseModule, InputError, ModuleResult, ParamSpec, SheetData, register
from optiqm.core.parsing import clean_frame, require_rows, to_float


@register
class MarkovAnalysis(BaseModule):
    key = "markov_analysis"
    name = "Markov Analysis"
    category = "Statistik & Simulasi"
    description = "Memprediksi distribusi probabilitas state ke depan, probabilitas steady-state, dan matriks fundamental absorbing."
    sheet_prefixes = ("MARKOV",)
    params = (ParamSpec("periods", "Jumlah Periode Prediksi", "integer", 6),)
    table_hint = ("Matriks transisi persegi: kolom pertama nama state, kolom berikutnya probabilitas transisi. "
                  "Opsional baris terakhir bernama 'Initial' untuk distribusi awal.")

    def template(self) -> SheetData:
        # Contoh klasik loyalitas pelanggan / mesin (Render-Stair): A, B -> steady state 0.75, 0.25
        df = pd.DataFrame(
            [["Toko A", 0.8, 0.2],
             ["Toko B", 0.6, 0.4],
             ["Initial", 0.5, 0.5]],
            columns=["State", "Toko A", "Toko B"],
        )
        return SheetData(params={"periods": 6}, tables={"main": df})

    def solve(self, data: SheetData) -> ModuleResult:
        p = self.resolved_params(data)
        T_per = max(1, int(p["periods"]))
        df = clean_frame(data.table("main"))
        require_rows(df, 2, "Matriks transisi Markov")
        states = list(df.columns[1:])
        n = len(states)

        init_vec = None
        rows = []
        for i in range(len(df)):
            nm = str(df.iloc[i, 0]).strip()
            vals = [to_float(df.at[i, s], f"{nm}->{s}") for s in states]
            if nm.lower() in {"initial", "awal", "init", "pi0"}:
                init_vec = np.array(vals)
            else:
                rows.append((nm, vals))
        if len(rows) != n:
            raise InputError(f"Matriks transisi harus persegi ({n} baris × {n} kolom).")
        P = np.array([r[1] for r in rows], dtype=float)
        if np.any(P < -1e-9) or np.any(np.abs(P.sum(axis=1) - 1.0) > 1e-3):
            raise InputError("Setiap baris matriks transisi harus non-negatif dan berjumlah 1.")
        r = ModuleResult()
        if init_vec is None:
            init_vec = np.zeros(n); init_vec[0] = 1.0
        else:
            if (init_vec < -1e-9).any() or init_vec.sum() <= 0:
                raise InputError("Distribusi awal (Initial) harus non-negatif dan total > 0.")
            if abs(init_vec.sum() - 1.0) > 1e-3:
                r.warnings.append(f"Total vektor Initial = {init_vec.sum():.4f} (bukan 1); dinormalisasi otomatis.")
                init_vec = init_vec / init_vec.sum()

        # Evolusi multi-periode
        traj = [init_vec.copy()]
        cur = init_vec.copy()
        for _ in range(T_per):
            cur = cur @ P
            traj.append(cur.copy())

        # Cek absorbing states (P_ii = 1)
        abs_idx = [i for i in range(n) if abs(P[i, i] - 1.0) < 1e-7]
        trans_idx = [i for i in range(n) if i not in abs_idx]

        ss = None
        N_mat = B_mat = None
        # Steady state: pi * P = pi, sum(pi) = 1
        if not abs_idx:
            A = (P.T - np.eye(n))
            A[-1, :] = 1.0
            rhs = np.zeros(n); rhs[-1] = 1.0
            try:
                ss = np.linalg.solve(A, rhs)
                for s_name, val in zip(states, ss):
                    r.metric(f"Steady State ({s_name})", f"{val * 100:.2f}%", highlight=True)
                r.table("Probabilitas Steady-State", ["State", "Probabilitas", "Persen"],
                        [[s_name, val, f"{val * 100:.2f}%"] for s_name, val in zip(states, ss)])
            except np.linalg.LinAlgError:
                r.warnings.append("Steady-state unik tidak ditemukan (rantai periodik atau reduksibel).")
        elif trans_idx:
            Q = P[np.ix_(trans_idx, trans_idx)]
            R = P[np.ix_(trans_idx, abs_idx)]
            try:
                N_mat = np.linalg.inv(np.eye(len(trans_idx)) - Q)
                B_mat = N_mat @ R
                r.metric("Jenis Rantai", f"Absorbing ({len(abs_idx)} state serap)", highlight=True)
                r.table("Matriks Fundamental N = (I - Q)⁻¹",
                        ["Dari \\ Di", *[states[j] for j in trans_idx]],
                        [[states[trans_idx[i]], *N_mat[i].tolist()] for i in range(len(trans_idx))])
                r.table("Probabilitas Penyerapan Akhir (N · R)",
                        ["State Transien", *[states[j] for j in abs_idx]],
                        [[states[trans_idx[i]], *B_mat[i].tolist()] for i in range(len(trans_idx))])
            except np.linalg.LinAlgError:
                r.warnings.append("Matriks (I - Q) singular.")

        r.table("Distribusi State per Periode", ["Periode", *states],
                [[f"t={t}", *vec.tolist()] for t, vec in enumerate(traj)])
        r.chart("Evolusi Probabilitas State", "line", {
            "x": [f"t={t}" for t in range(len(traj))],
            "series": [{"name": s, "data": [float(vec[j]) for vec in traj]} for j, s in enumerate(states)],
            "x_label": "Periode", "y_label": "Probabilitas",
        })
        r.interpretation = f"Analisis Markov selesai untuk {n} state sepanjang {T_per} periode."

        # Analisis mendalam
        chain_kind = "Absorbing Markov Chain" if abs_idx else "Regular / Ergodic Markov Chain"
        diag_ret = [(float(P[i, i]), states[i]) for i in range(n)]
        sticky = max(diag_ret, key=lambda x: x[0])
        r.analyze(
            "Metodologi Rantai Markov & Klasifikasi State",
            f"Sistem dimodelkan sebagai {chain_kind} dengan {n} state ({', '.join(states)}) memakai hukum transisi π(t+1) = π(t)·P selama {T_per} periode.",
            [
                f"State dengan tingkat retensi/ketahanan tertinggi (P_ii): '{sticky[1]}' ({sticky[0] * 100:.1f}% tetap berada di state yang sama per periode).",
                f"Distribusi akhir t={T_per}: " + ", ".join(f"{s} = {traj[-1][j] * 100:.2f}%" for j, s in enumerate(states)) + ".",
            ],
        )

        if ss is not None:
            dom_i = int(np.argmax(ss))
            conv_err = float(np.max(np.abs(traj[-1] - ss)))
            r.analyze(
                "Analisis Keseimbangan Jangka Panjang (Steady-State) & Konvergensi",
                "Pada rantai ergodik, distribusi jangka panjang π* bersifat independen terhadap distribusi awal π(0) dan memenuhi π*·P = π*:",
                [
                    f"State dominan jangka panjang: '{states[dom_i]}' dengan pangsa keseimbangan {ss[dom_i] * 100:.2f}% "
                    f"(berubah {(ss[dom_i] - init_vec[dom_i]) * 100:+.2f} poin persentase dari kondisi awal {init_vec[dom_i] * 100:.1f}%).",
                    f"Jarak konvergensi pada t={T_per}: deviasi maks |π({T_per}) − π*| = {conv_err * 100:.3f} poin persentase "
                    f"({'sudah sangat dekat steady-state' if conv_err < 0.01 else 'masih dalam fase transisi menuju keseimbangan'}).",
                ],
            )
            weak_ret = min(diag_ret, key=lambda x: x[0])
            r.analyze(
                "Rekomendasi Strategis (Retensi & Pergeseran Pangsa)",
                "Implikasi terhadap manajemen loyalitas / keandalan status:",
                [
                    f"State '{weak_ret[1]}' memiliki retensi terendah ({weak_ret[0] * 100:.1f}%): tingkatkan retensi atau kurangi laju perpindahan keluar (churn) bila ingin menaikkan pangsa jangka panjangnya.",
                    "Perlu diingat bahwa dalam rantai ergodik, promosi satu kali (mengubah distribusi awal) efeknya hanya sementara; perubahan pangsa permanen harus dilakukan dengan mengubah matriks probabilitas transisi P.",
                ],
            )
        elif N_mat is not None and B_mat is not None:
            exp_steps = N_mat.sum(axis=1)
            abs_bullets = [
                f"Dari state transien '{states[trans_idx[i]]}': rata-rata bertahan {exp_steps[i]:.2f} periode sebelum terserap; "
                "peluang akhir → " + ", ".join(f"{states[abs_idx[j]]}: {B_mat[i, j] * 100:.1f}%" for j in range(len(abs_idx))) + "."
                for i in range(len(trans_idx))
            ]
            r.analyze(
                "Analisis Matriks Fundamental & Peluang Penyerapan Akhir",
                "Setiap entri N_ij = (I − Q)⁻¹ menyatakan ekspektasi jumlah kunjungan ke state transien j sebelum akhirnya masuk ke state serap (absorbing):",
                abs_bullets,
            )
            r.analyze(
                "Rekomendasi Pengendalian Rantai Absorbing",
                "Panduan intervensi sebelum sistem mencapai state serap (mis. gagal bayar/macet/rusak total):",
                [
                    "Fokuskan tindakan pencegahan pada state transien yang memiliki probabilitas penyerapan tertinggi menuju state serap yang tidak diinginkan.",
                    "Memperbesar peluang transisi kembali ke state sehat (atau memperpendek waktu tinggal di state berisiko) akan langsung memperbaiki probabilitas penyerapan akhir N·R.",
                ],
            )
        else:
            r.analyze(
                "Analisis Dinamika Transisi",
                "Rantai tidak memiliki steady-state tunggal atau seluruh state bersifat serap; pantau langsung evolusi distribusi dari t=0 hingga t=" + str(T_per) + ".",
                ["Evaluasi apakah struktur transisi memiliki kelas tertutup terpisah atau siklus periodik."],
            )
        return r
