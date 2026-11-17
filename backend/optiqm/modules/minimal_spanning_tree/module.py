"""Modul Minimal Spanning Tree (Kruskal)."""

from __future__ import annotations

import networkx as nx
import pandas as pd

from optiqm.core import BaseModule, InputError, ModuleResult, SheetData, SolverError, register
from optiqm.core.parsing import clean_frame, find_column, require_rows, to_float


@register
class MinimalSpanningTree(BaseModule):
    key = "minimal_spanning_tree"
    name = "Minimal Spanning Tree"
    category = "Distribusi & Jaringan"
    description = "Menghubungkan seluruh simpul jaringan dengan total jarak/biaya kabel minimum."
    sheet_prefixes = ("MST", "SPANNING")
    table_hint = "Kolom: From (Simpul 1), To (Simpul 2), Distance (Jarak/Biaya)."

    def template(self) -> SheetData:
        # Lauderdale Construction / Render-Stair: total MST = 16
        df = pd.DataFrame(
            [[1, 2, 2], [1, 3, 2], [1, 4, 4], [2, 3, 5], [2, 5, 3],
             [3, 4, 1], [3, 6, 4], [4, 6, 6], [5, 7, 7], [6, 7, 5], [7, 8, 3], [6, 8, 9]],
            columns=["From", "To", "Distance"],
        )
        return SheetData(tables={"main": df})

    def solve(self, data: SheetData) -> ModuleResult:
        df = clean_frame(data.table("main"))
        require_rows(df, 1, "Tabel sisi jaringan")
        c_from = find_column(df, ["From", "Asal", "Node1"])
        c_to = find_column(df, ["To", "Tujuan", "Node2"])
        c_dist = find_column(df, ["Distance", "Jarak", "Weight", "Bobot", "Cost", "Biaya"])

        G = nx.Graph()
        edges = []
        for i in range(len(df)):
            u, v = str(df.at[i, c_from]).strip(), str(df.at[i, c_to]).strip()
            w = to_float(df.at[i, c_dist], f"Jarak {u}-{v}")
            if w < 0:
                raise InputError(f"Jarak {u}-{v} tidak boleh negatif.")
            G.add_edge(u, v, weight=w)
            edges.append((u, v, w))

        if not nx.is_connected(G):
            raise SolverError("Graf tidak terhubung; beberapa simpul terpisah.")

        T = nx.minimum_spanning_tree(G, algorithm="kruskal")
        chosen = {(u, v) for u, v in T.edges()} | {(v, u) for u, v in T.edges()}
        total_w = float(sum(d["weight"] for _, _, d in T.edges(data=True)))

        r = ModuleResult()
        r.metric("Total Panjang / Biaya Minimum", total_w, highlight=True)
        r.metric("Jumlah Koneksi Terpilih", T.number_of_edges())
        r.metric("Jumlah Simpul", G.number_of_nodes())

        r.table("Sisi Terpilih (MST)", ["Simpul 1", "Simpul 2", "Jarak/Biaya"],
                sorted([[u, v, d["weight"]] for u, v, d in T.edges(data=True)], key=lambda x: x[2]))
        r.chart("Diagram Minimal Spanning Tree", "network", {
            "directed": False,
            "nodes": [{"id": n, "label": n, "highlight": True} for n in G.nodes],
            "edges": [{"source": u, "target": v, "label": f"{w:g}", "highlight": (u, v) in chosen}
                      for u, v, w in edges],
        })
        r.interpretation = f"Minimal Spanning Tree menghubungkan {G.number_of_nodes()} simpul dengan total {total_w:g}."
        return r
