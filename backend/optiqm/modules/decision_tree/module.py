"""Modul Decision Tree (Roll-back EMV)."""

from __future__ import annotations

import pandas as pd

from optiqm.core import BaseModule, InputError, ModuleResult, ParamSpec, SheetData, register
from optiqm.core.parsing import clean_frame, find_column, require_rows, to_float


@register
class DecisionTree(BaseModule):
    key = "decision_tree"
    name = "Decision Tree"
    category = "Analisis Keputusan"
    description = "Pohon keputusan bertahap dengan perhitungan Expected Monetary Value (roll-back)."
    sheet_prefixes = ("TREE", "DTREE", "POHON")
    params = (ParamSpec("payoff_type", "Tujuan", "choice", "profit", ("profit", "cost")),)
    table_hint = ("Kolom: Node, Parent ('-' untuk akar), Type (decision/chance/terminal), "
                  "Branch (label cabang), Probability (utk anak simpul chance), Payoff (biaya cabang / hasil terminal).")

    def template(self) -> SheetData:
        # Thompson Lumber Decision Tree
        df = pd.DataFrame(
            [["N1", "-", "decision", "Mulai", None, 0],
             ["N2", "N1", "chance", "Bangun Pabrik Besar", None, 0],
             ["N3", "N1", "chance", "Bangun Pabrik Kecil", None, 0],
             ["N4", "N1", "terminal", "Tidak Membangun", None, 0],
             ["T1", "N2", "terminal", "Pasar Baik", 0.5, 200000],
             ["T2", "N2", "terminal", "Pasar Buruk", 0.5, -180000],
             ["T3", "N3", "terminal", "Pasar Baik", 0.5, 100000],
             ["T4", "N3", "terminal", "Pasar Buruk", 0.5, -20000]],
            columns=["Node", "Parent", "Type", "Branch", "Probability", "Payoff"],
        )
        return SheetData(params={"payoff_type": "profit"}, tables={"main": df})

    def solve(self, data: SheetData) -> ModuleResult:
        p = self.resolved_params(data)
        is_profit = p["payoff_type"] == "profit"
        df = clean_frame(data.table("main"))
        require_rows(df, 2, "Tabel node pohon keputusan")
        c_node = find_column(df, ["Node", "ID"])
        c_par = find_column(df, ["Parent", "Induk"])
        c_type = find_column(df, ["Type", "Tipe", "Jenis"])
        c_br = find_column(df, ["Branch", "Cabang", "Label"], required=False)
        c_prob = find_column(df, ["Probability", "Prob", "P"], required=False)
        c_pay = find_column(df, ["Payoff", "Value", "Nilai", "Cost"])

        nodes = {}
        children: dict[str, list[str]] = {}
        roots = []
        for i in range(len(df)):
            nid = str(df.at[i, c_node]).strip()
            if nid in nodes:
                raise InputError(f"ID simpul duplikat ditemukan: '{nid}'.")
            par_raw = df.at[i, c_par]
            par = "" if pd.isna(par_raw) or str(par_raw).strip() in {"-", "", "root"} else str(par_raw).strip()
            ntype = str(df.at[i, c_type]).strip().lower()
            if ntype not in {"decision", "chance", "terminal"}:
                raise InputError(f"Type simpul '{nid}' harus decision, chance, atau terminal.")
            br = str(df.at[i, c_br]).strip() if c_br and not pd.isna(df.at[i, c_br]) else nid
            prob = to_float(df.at[i, c_prob], f"Prob {nid}") if c_prob and not pd.isna(df.at[i, c_prob]) else 1.0
            pay = to_float(df.at[i, c_pay], f"Payoff {nid}") if not pd.isna(df.at[i, c_pay]) else 0.0
            nodes[nid] = {"id": nid, "parent": par, "type": ntype, "branch": br, "prob": prob, "pay": pay}
            if not par:
                roots.append(nid)
            else:
                children.setdefault(par, []).append(nid)
        if not roots:
            raise InputError("Simpul akar (Parent='-') tidak ditemukan.")
        if len(roots) > 1:
            raise InputError(f"Pohon keputusan hanya boleh memiliki 1 simpul akar (ditemukan: {', '.join(roots)}).")
        root = roots[0]
        for nid, nd in nodes.items():
            if nd["parent"] and nd["parent"] not in nodes:
                raise InputError(f"Induk '{nd['parent']}' dari simpul '{nid}' tidak ditemukan.")
            if nd["type"] == "terminal" and children.get(nid):
                raise InputError(f"Simpul terminal '{nid}' tidak boleh memiliki cabang anak.")

        emv: dict[str, float] = {}
        best_child: dict[str, str] = {}
        branch_vals: dict[str, list[tuple[str, float]]] = {}
        visiting: set[str] = set()

        def rollback(u: str) -> float:
            if u in visiting:
                raise InputError(f"Pohon keputusan mengandung siklus pada simpul '{u}'.")
            visiting.add(u)
            nd = nodes[u]
            ch = children.get(u, [])
            if nd["type"] == "terminal" or not ch:
                emv[u] = nd["pay"]
                visiting.remove(u)
                return emv[u]
            vals = []
            for c in ch:
                c_is_leaf = nodes[c]["type"] == "terminal" or not children.get(c)
                c_val = rollback(c) if c_is_leaf else (rollback(c) + nodes[c]["pay"])
                vals.append((c, c_val))
            branch_vals[u] = vals
            if nd["type"] == "chance":
                if any(nodes[c]["prob"] < 0 for c in ch):
                    raise InputError(f"Probabilitas cabang pada simpul chance '{u}' tidak boleh negatif.")
                s_p = sum(nodes[c]["prob"] for c in ch)
                if abs(s_p - 1.0) > 1e-3:
                    raise InputError(f"Jumlah probabilitas cabang simpul chance '{u}' harus = 1 (saat ini {s_p:.3f}).")
                emv[u] = sum(nodes[c]["prob"] * v for c, v in vals)
            else:
                pick_fn = max if is_profit else min
                b_c, b_v = pick_fn(vals, key=lambda x: x[1])
                emv[u] = b_v
                best_child[u] = b_c
            visiting.remove(u)
            return emv[u]

        root_sub = rollback(root)
        root_val = root_sub + (nodes[root]["pay"] if children.get(root) else 0.0)
        if children.get(root) and abs(nodes[root]["pay"]) > 1e-12:
            emv[root] = root_val
        if len(emv) < len(nodes):
            unreachable = [nid for nid in nodes if nid not in emv]
            raise InputError(f"Simpul tidak terhubung ke akar '{root}': {', '.join(unreachable)}.")

        opt_edges = set()
        opt_terminals: list[float] = []
        stack = [(root, nodes[root]["pay"] if children.get(root) else 0.0)]
        while stack:
            cur, acc = stack.pop()
            ch = children.get(cur, [])
            if cur in best_child:
                bc = best_child[cur]
                opt_edges.add((cur, bc))
                bc_leaf = nodes[bc]["type"] == "terminal" or not children.get(bc)
                stack.append((bc, acc + (0.0 if bc_leaf else nodes[bc]["pay"])))
            elif nodes[cur]["type"] == "chance" and ch:
                for c in ch:
                    opt_edges.add((cur, c))
                    c_leaf = nodes[c]["type"] == "terminal" or not children.get(c)
                    stack.append((c, acc + (0.0 if c_leaf else nodes[c]["pay"])))
            else:
                opt_terminals.append(acc + nodes[cur]["pay"])

        r = ModuleResult()
        r.metric("EMV Optimal", root_val, highlight=True)
        if root in best_child:
            r.metric("Keputusan Awal Terbaik", nodes[best_child[root]]["branch"], highlight=True)
        r.table("Evaluasi Simpul Pohon Keputusan",
                ["Node", "Induk", "Tipe", "Cabang", "Probabilitas", "Payoff", "EMV", "Cabang Terpilih"],
                [[n["id"], n["parent"] or "-", n["type"], n["branch"], n["prob"] if n["parent"] else "-",
                  n["pay"], emv[n["id"]], nodes[best_child[n["id"]]]["branch"] if n["id"] in best_child else "-"]
                 for n in nodes.values()])
        r.chart("Diagram Pohon Keputusan", "network", {
            "directed": True,
            "nodes": [{"id": nid, "label": f"{nid}: {emv[nid]:,.2g}", "highlight": nid == root or any(e[1] == nid for e in opt_edges)}
                      for nid in nodes],
            "edges": [{"source": n["parent"], "target": nid,
                       "label": f"{n['branch']}" + (f" ({n['prob']:g})" if nodes[n["parent"]]["type"] == "chance" else ""),
                       "highlight": (n["parent"], nid) in opt_edges}
                      for nid, n in nodes.items() if n["parent"]],
        })
        r.interpretation = f"EMV optimal pohon keputusan = {root_val:,.2f}" + (
            f" dengan memilih '{nodes[best_child[root]]['branch']}'." if root in best_child else "."
        )

        # Analisis mendalam
        n_dec = sum(1 for n in nodes.values() if n["type"] == "decision")
        n_ch = sum(1 for n in nodes.values() if n["type"] == "chance")
        n_term = sum(1 for n in nodes.values() if n["type"] == "terminal")
        r.analyze(
            "Metodologi Induksi Mundur (Roll-Back EMV)",
            f"Pohon keputusan terdiri dari {len(nodes)} simpul ({n_dec} keputusan, {n_ch} peluang/chance, {n_term} terminal) "
            f"dengan tujuan {'Maksimasi Profit' if is_profit else 'Minimasi Biaya'}. Evaluasi dilakukan mundur dari daun ke akar: "
            "simpul chance menghitung rata-rata tertimbang Σ(p_i × V_i), sedangkan simpul decision memilih cabang terbaik.",
            [
                f"EMV Optimal di simpul akar '{root}' = {root_val:,.2f}.",
                f"Pada kebijakan optimal, rentang hasil akhir (terminal) yang mungkin terjadi berkisar dari {min(opt_terminals):,.2f} hingga {max(opt_terminals):,.2f}.",
            ],
        )

        branch_bullets = []
        if root in branch_vals:
            sorted_root = sorted(branch_vals[root], key=lambda x: x[1], reverse=is_profit)
            for idx, (cid, cval) in enumerate(sorted_root, start=1):
                tag = " (TERPILIH)" if cid == best_child.get(root) else f" (selisih {cval - sorted_root[0][1]:+,.2f})"
                branch_bullets.append(f"#{idx} Cabang '{nodes[cid]['branch']}' ({cid}): EMV = {cval:,.2f}{tag}.")
        for uid, bc in best_child.items():
            if uid != root:
                branch_bullets.append(f"Keputusan lanjutan di simpul '{uid}' ({nodes[uid]['branch']}): pilih '{nodes[bc]['branch']}' (EMV = {emv[uid]:,.2f}).")
        r.analyze(
            "Bedah Perbandingan Cabang & Rencana Keputusan Bertahap",
            "Perbandingan EMV antar cabang keputusan memperlihatkan margin keunggulan strategi optimal atas alternatif lain:",
            branch_bullets or ["Simpul akar bukan simpul keputusan; EMV merepresentasikan nilai ekspektasi murni seluruh cabang peluang."],
        )

        rec_bullets = []
        if root in best_child:
            rec_bullets.append(f"Langkah awal optimal: eksekusi cabang '{nodes[best_child[root]]['branch']}' untuk memperoleh ekspektasi nilai tertinggi ({root_val:,.2f}).")
        if opt_terminals and min(opt_terminals) < 0 and is_profit:
            rec_bullets.append(
                f"Perhatikan risiko downside: meski EMV positif/tertinggi, skenario terburuk pada jalur optimal masih berpotensi rugi sebesar {min(opt_terminals):,.2f} — "
                "pastikan cadangan likuiditas memadai atau pertimbangkan opsi dengan risiko lebih kecil jika perusahaan sangat menghindari kerugian."
            )
        rec_bullets.append("Lakukan uji sensitivitas dengan mengubah probabilitas pada simpul peluang utama untuk mengetahui ambang batas probabilitas di mana keputusan berubah.")
        r.analyze("Rekomendasi Strategis & Mitigasi Risiko", "Implikasi keputusan bertahap:", rec_bullets)
        return r
