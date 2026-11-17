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
        root = None
        for i in range(len(df)):
            nid = str(df.at[i, c_node]).strip()
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
                root = nid
            else:
                children.setdefault(par, []).append(nid)
        if not root:
            raise InputError("Simpul akar (Parent='-') tidak ditemukan.")

        emv: dict[str, float] = {}
        best_child: dict[str, str] = {}

        def rollback(u: str) -> float:
            nd = nodes[u]
            ch = children.get(u, [])
            if nd["type"] == "terminal" or not ch:
                emv[u] = nd["pay"]
                return emv[u]
            vals = [(c, rollback(c) + nodes[c]["pay"] if nodes[c]["type"] != "terminal" else rollback(c)) for c in ch]
            if nd["type"] == "chance":
                s_p = sum(nodes[c]["prob"] for c in ch)
                if abs(s_p - 1.0) > 1e-3:
                    raise InputError(f"Jumlah probabilitas cabang simpul chance '{u}' harus = 1 (saat ini {s_p:.3f}).")
                emv[u] = sum(nodes[c]["prob"] * v for c, v in vals)
            else:
                pick_fn = max if is_profit else min
                b_c, b_v = pick_fn(vals, key=lambda x: x[1])
                emv[u] = b_v
                best_child[u] = b_c
            return emv[u]

        root_val = rollback(root)
        opt_edges = set()
        stack = [root]
        while stack:
            cur = stack.pop()
            if cur in best_child:
                bc = best_child[cur]
                opt_edges.add((cur, bc))
                stack.append(bc)
            elif nodes[cur]["type"] == "chance":
                for c in children.get(cur, []):
                    opt_edges.add((cur, c))
                    stack.append(c)

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
        return r
