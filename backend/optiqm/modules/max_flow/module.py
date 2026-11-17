"""Modul Maximal Flow (Edmonds-Karp)."""

from __future__ import annotations

import networkx as nx
import pandas as pd

from optiqm.core import BaseModule, InputError, ModuleResult, ParamSpec, SheetData, register
from optiqm.core.parsing import clean_frame, find_column, require_rows, to_float


@register
class MaxFlow(BaseModule):
    key = "max_flow"
    name = "Maximal Flow"
    category = "Distribusi & Jaringan"
    description = "Menghitung aliran maksimum dari sumber (source) ke tujuan (sink) pada jaringan berkapasitas."
    sheet_prefixes = ("MAXF", "MAXFLOW", "FLOW")
    params = (
        ParamSpec("source", "Simpul Sumber (Source)", "text", "1"),
        ParamSpec("sink", "Simpul Tujuan (Sink)", "text", "6"),
    )
    table_hint = ("Kolom: From, To, Capacity (kapasitas dari From ke To), dan opsional Reverse_Capacity "
                  "(kapasitas balik, default 0 untuk sisi berarah).")

    def template(self) -> SheetData:
        # Contoh klasik jaringan 6 simpul (Waukesha / Render-Stair)
        df = pd.DataFrame(
            [[1, 2, 3, 1], [1, 3, 10, 0], [1, 4, 2, 0],
             [2, 4, 1, 1], [2, 6, 2, 0],
             [3, 4, 3, 0], [3, 5, 2, 0],
             [4, 5, 1, 0], [4, 6, 6, 0],
             [5, 6, 2, 0]],
            columns=["From", "To", "Capacity", "Reverse_Capacity"],
        )
        return SheetData(params={"source": "1", "sink": "6"}, tables={"main": df})

    def solve(self, data: SheetData) -> ModuleResult:
        p = self.resolved_params(data)
        df = clean_frame(data.table("main"))
        require_rows(df, 1, "Tabel aliran jaringan")
        c_from = find_column(df, ["From", "Asal", "Source"])
        c_to = find_column(df, ["To", "Tujuan", "Target", "Sink"])
        c_cap = find_column(df, ["Capacity", "Kapasitas", "Cap"])
        c_rev = find_column(df, ["Reverse_Capacity", "Reverse", "Kapasitas Balik"], required=False)

        G = nx.DiGraph()
        raw_edges = []
        for i in range(len(df)):
            u, v = str(df.at[i, c_from]).strip(), str(df.at[i, c_to]).strip()
            cap = to_float(df.at[i, c_cap], f"Capacity {u}->{v}")
            rev = to_float(df.at[i, c_rev], f"Reverse {v}->{u}") if c_rev and not pd.isna(df.at[i, c_rev]) else 0.0
            if cap < 0 or rev < 0:
                raise InputError("Kapasitas tidak boleh negatif.")
            if cap > 0:
                G.add_edge(u, v, capacity=cap)
            if rev > 0:
                G.add_edge(v, u, capacity=rev)
            raw_edges.append((u, v, cap))

        src, snk = str(p["source"]).strip(), str(p["sink"]).strip()
        if src not in G or snk not in G:
            raise InputError(f"Simpul '{src}' atau '{snk}' tidak ada di jaringan.")
        if src == snk:
            raise InputError("Simpul source dan sink tidak boleh sama.")

        flow_val, flow_dict = nx.maximum_flow(G, src, snk)
        rows_out = []
        edges_vis = []
        for u, v, d in G.edges(data=True):
            f = float(flow_dict.get(u, {}).get(v, 0.0))
            cap = float(d["capacity"])
            pct = (f / cap * 100) if cap > 0 else 0.0
            rows_out.append([u, v, cap, f, pct])
            edges_vis.append({"source": u, "target": v, "label": f"{f:g}/{cap:g}", "highlight": f > 0})

        r = ModuleResult()
        r.metric("Aliran Maksimum", float(flow_val), highlight=True)
        r.metric("Jalur Aktif", sum(1 for row in rows_out if row[3] > 0))
        r.table("Rincian Aliran per Segmen", ["Dari", "Ke", "Kapasitas", "Aliran", "Utilisasi (%)"], rows_out)
        r.chart("Diagram Aliran Maksimum", "network", {
            "directed": True,
            "nodes": [{"id": n, "label": n, "highlight": n in (src, snk)} for n in G.nodes],
            "edges": edges_vis,
        })
        r.interpretation = f"Aliran maksimum dari {src} ke {snk} adalah {flow_val:g} unit."
        return r
