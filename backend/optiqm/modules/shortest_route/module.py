"""Modul Shortest Route (Algoritma Dijkstra)."""

from __future__ import annotations

import networkx as nx
import pandas as pd

from optiqm.core import BaseModule, InputError, ModuleResult, ParamSpec, SheetData, SolverError, register
from optiqm.core.parsing import clean_frame, find_column, require_rows, to_float


@register
class ShortestRoute(BaseModule):
    key = "shortest_route"
    name = "Shortest Route"
    category = "Distribusi & Jaringan"
    description = "Menentukan rute terpendek dari titik asal ke tujuan pada jaringan (Dijkstra)."
    sheet_prefixes = ("SR", "SHORTEST")
    params = (
        ParamSpec("start", "Simpul Asal", "text", "1"),
        ParamSpec("end", "Simpul Tujuan", "text", "6"),
        ParamSpec("directed", "Graf Berarah", "boolean", False),
    )
    table_hint = "Kolom: From (Asal), To (Tujuan), Distance (Jarak/Biaya >= 0)."

    def template(self) -> SheetData:
        # Contoh klasik jaringan 6 simpul (Render-Stair: 1->2:100, 1->3:200, dst.)
        df = pd.DataFrame(
            [[1, 2, 100], [1, 3, 200], [2, 3, 50], [2, 4, 200], [2, 5, 100],
             [3, 5, 40], [4, 5, 150], [4, 6, 100], [5, 6, 100]],
            columns=["From", "To", "Distance"],
        )
        return SheetData(params={"start": "1", "end": "6", "directed": False}, tables={"main": df})

    def solve(self, data: SheetData) -> ModuleResult:
        p = self.resolved_params(data)
        df = clean_frame(data.table("main"))
        require_rows(df, 1, "Tabel sisi jaringan")
        c_from = find_column(df, ["From", "Asal", "Start", "Source"])
        c_to = find_column(df, ["To", "Tujuan", "End", "Target"])
        c_dist = find_column(df, ["Distance", "Jarak", "Weight", "Bobot", "Cost", "Biaya"])

        G = nx.DiGraph() if p["directed"] else nx.Graph()
        edges = []
        for i in range(len(df)):
            u = str(df.at[i, c_from]).strip()
            v = str(df.at[i, c_to]).strip()
            w = to_float(df.at[i, c_dist], f"Jarak {u}->{v}")
            if w < 0:
                raise InputError(f"Jarak {u}->{v} tidak boleh negatif ({w}).")
            G.add_edge(u, v, weight=w)
            edges.append((u, v, w))

        start, end = str(p["start"]).strip(), str(p["end"]).strip()
        if start not in G or end not in G:
            raise InputError(f"Simpul '{start}' atau '{end}' tidak ada di jaringan ({sorted(G.nodes)}).")
        try:
            path = nx.shortest_path(G, start, end, weight="weight")
            dist = nx.shortest_path_length(G, start, end, weight="weight")
        except nx.NetworkXNoPath as exc:
            raise SolverError(f"Tidak ada lintasan dari '{start}' ke '{end}'.") from exc

        path_edges = set(zip(path, path[1:]))
        if not p["directed"]:
            path_edges |= {(v, u) for u, v in path_edges}
        path_nodes = set(path)

        r = ModuleResult()
        r.metric("Total Jarak Terpendek", float(dist), highlight=True)
        r.metric("Rute Terpendek", " → ".join(path))
        r.metric("Jumlah Segmen", len(path) - 1)

        cum = 0.0
        rows_out = []
        for u, v in zip(path, path[1:]):
            w = G[u][v]["weight"]
            cum += w
            rows_out.append([u, v, w, cum])
        r.table("Segmen Rute Terpendek", ["Dari", "Ke", "Jarak", "Jarak Kumulatif"], rows_out)

        r.chart("Diagram Jaringan — Rute Terpendek", "network", {
            "directed": p["directed"],
            "nodes": [{"id": n, "label": n, "highlight": n in path_nodes} for n in G.nodes],
            "edges": [{"source": u, "target": v, "label": f"{w:g}", "highlight": (u, v) in path_edges}
                      for u, v, w in edges],
        })
        r.interpretation = f"Rute terpendek dari {start} ke {end}: {' → '.join(path)} dengan total jarak {dist:g}."
        return r
