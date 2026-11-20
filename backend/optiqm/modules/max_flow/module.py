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
                if G.has_edge(u, v):
                    G[u][v]["capacity"] += cap
                else:
                    G.add_edge(u, v, capacity=cap)
            if rev > 0:
                if G.has_edge(v, u):
                    G[v][u]["capacity"] += rev
                else:
                    G.add_edge(v, u, capacity=rev)
            raw_edges.append((u, v, cap))

        src, snk = str(p["source"]).strip(), str(p["sink"]).strip()
        if src not in G or snk not in G:
            raise InputError(f"Simpul '{src}' atau '{snk}' tidak ada di jaringan.")
        if src == snk:
            raise InputError("Simpul source dan sink tidak boleh sama.")

        flow_val, flow_dict = nx.maximum_flow(G, src, snk)
        cut_val, (reach, non_reach) = nx.minimum_cut(G, src, snk)
        min_cut_edges = [
            (u, v, float(G[u][v]["capacity"]))
            for u in reach
            for v in G.successors(u)
            if v in non_reach
        ]

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

        # Analisis mendalam
        out_cap_src = sum(float(G[src][v]["capacity"]) for v in G.successors(src))
        in_cap_snk = sum(float(G[u][snk]["capacity"]) for u in G.predecessors(snk))
        saturated = [row for row in rows_out if row[4] >= 99.999]
        slack_active = [row for row in rows_out if 0 < row[3] < row[2] - 1e-9]
        r.analyze(
            "Metodologi Edmonds-Karp & Teorema Max-Flow Min-Cut",
            f"Aliran maksimum dari simpul sumber '{src}' ke tujuan '{snk}' dihitung pada jaringan berarah ({G.number_of_nodes()} simpul, {G.number_of_edges()} segmen). "
            "Menurut Teorema Max-Flow Min-Cut, besar aliran maksimum selalu sama dengan kapasitas potongan minimum (Minimum Cut).",
            [
                f"Verifikasi Max-Flow = Min-Cut = {float(flow_val):g} unit (kapasitas potongan minimum = {float(cut_val):g}).",
                f"Kapasitas keluar dari sumber '{src}' = {out_cap_src:g} (terpakai {(flow_val / out_cap_src * 100.0) if out_cap_src > 0 else 0.0:.1f}%), "
                f"kapasitas masuk ke tujuan '{snk}' = {in_cap_snk:g} (terpakai {(flow_val / in_cap_snk * 100.0) if in_cap_snk > 0 else 0.0:.1f}%).",
                f"Terdapat {len(saturated)} segmen jenuh penuh (utilisasi 100%) dan {len(slack_active)} segmen aktif yang masih memiliki sisa kapasitas.",
            ],
        )

        cut_desc = ", ".join(f"{u}→{v} (kap={cap:g})" for u, v, cap in min_cut_edges) or "-"
        r.analyze(
            "Identifikasi Bottleneck Jaringan (Minimum Cut)",
            "Sisi-sisi yang memisahkan himpunan simpul terjangkau dari sumber (S) dan himpunan tujuan (T) merupakan pembatas utama throughput jaringan.",
            [
                f"Partisi Sumber S = {{{', '.join(sorted(reach))}}} | Partisi Tujuan T = {{{', '.join(sorted(non_reach))}}}.",
                f"Segmen Bottleneck (Minimum Cut): {cut_desc}. Seluruh segmen ini jenuh 100%.",
                f"Segmen aktif dengan sisa kapasitas terbesar: "
                + (
                    ", ".join(f"{row[0]}→{row[1]} (sisa {row[2] - row[3]:g})" for row in sorted(slack_active, key=lambda x: -(x[2] - x[3]))[:3])
                    if slack_active else "tidak ada segmen aktif yang tersisa."
                ),
            ],
        )

        r.analyze(
            "Rekomendasi Ekspansi Kapasitas",
            "Panduan investasi peningkatan throughput jaringan:",
            [
                f"Untuk menaikkan aliran maksimum melampaui {float(flow_val):g} unit, ekspansi kapasitas HARUS menyasar segmen pada Minimum Cut ({cut_desc}).",
                "Menambah kapasitas pada segmen di luar Minimum Cut tidak akan menaikkan throughput total selama bottleneck utama belum dibuka.",
                "Lakukan pemantauan rutin pada segmen jenuh 100% karena gangguan kecil di salah satu segmen tersebut akan langsung menurunkan aliran total jaringan.",
            ],
        )
        return r
