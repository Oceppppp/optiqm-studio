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
            if G.has_edge(u, v):
                if w < G[u][v]["weight"]:
                    G[u][v]["weight"] = w
            else:
                G.add_edge(u, v, weight=w)
            edges.append((u, v, w))

        start, end = str(p["start"]).strip(), str(p["end"]).strip()
        if start not in G or end not in G:
            raise InputError(f"Simpul '{start}' atau '{end}' tidak ada di jaringan ({sorted(G.nodes)}).")
        try:
            path = nx.shortest_path(G, start, end, weight="weight")
            dist = float(nx.shortest_path_length(G, start, end, weight="weight"))
        except nx.NetworkXNoPath as exc:
            raise SolverError(f"Tidak ada lintasan dari '{start}' ke '{end}'.") from exc

        path_edges = set(zip(path, path[1:]))
        if not p["directed"]:
            path_edges |= {(v, u) for u, v in path_edges}
        path_nodes = set(path)

        r = ModuleResult()
        r.metric("Total Jarak Terpendek", dist, highlight=True)
        r.metric("Rute Terpendek", " → ".join(path))
        r.metric("Jumlah Segmen", len(path) - 1)

        cum = 0.0
        rows_out = []
        for u, v in zip(path, path[1:]):
            w = float(G[u][v]["weight"])
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

        # Analisis mendalam
        seg_expr = " + ".join(f"{row[2]:g}" for row in rows_out) or "0"
        alt_info = None
        try:
            gen = nx.shortest_simple_paths(G, start, end, weight="weight")
            next(gen)
            second = next(gen, None)
            if second is not None:
                d2 = float(sum(G[a][b]["weight"] for a, b in zip(second, second[1:])))
                alt_info = (second, d2)
        except Exception:
            alt_info = None

        r.analyze(
            "Metodologi Algoritma Dijkstra & Verifikasi Rute",
            f"Jaringan {'berarah (directed)' if p['directed'] else 'tak berarah (undirected)'} terdiri dari {G.number_of_nodes()} simpul "
            f"dan {G.number_of_edges()} sisi dengan bobot non-negatif. Algoritma Dijkstra menjamin lintasan global terpendek dari '{start}' ke '{end}'.",
            [
                f"Lintasan Optimal: {' → '.join(path)} ({len(rows_out)} segmen).",
                f"Verifikasi Jarak Total: {seg_expr} = {dist:,.4g}.",
                f"Cakupan Jaringan: rute melewati {len(path)} dari {G.number_of_nodes()} simpul ({len(path) / G.number_of_nodes() * 100:.1f}%).",
            ],
        )

        seg_bullets: list[str] = []
        if rows_out:
            longest = max(rows_out, key=lambda x: x[2])
            shortest_s = min(rows_out, key=lambda x: x[2])
            share = (longest[2] / dist * 100.0) if dist > 0 else 0.0
            seg_bullets.append(
                f"Segmen terberat (dominan): {longest[0]} → {longest[1]} sebesar {longest[2]:g} ({share:.1f}% dari total jarak)."
            )
            if len(rows_out) > 1:
                seg_bullets.append(f"Segmen terpendek: {shortest_s[0]} → {shortest_s[1]} sebesar {shortest_s[2]:g}.")
        if alt_info:
            p2, d2 = alt_info
            gap = d2 - dist
            pct = (gap / dist * 100.0) if dist > 0 else 0.0
            if gap <= 1e-9:
                seg_bullets.append(f"Terdapat RUTE OPTIMAL ALTERNATIF dengan jarak identik ({d2:g}): {' → '.join(p2)}.")
            else:
                seg_bullets.append(
                    f"Rute cadangan terbaik ke-2: {' → '.join(p2)} dengan jarak {d2:g} (lebih jauh {gap:g} atau +{pct:.1f}% dari rute utama)."
                )
        else:
            seg_bullets.append("Tidak ditemukan jalur alternatif sederhana lain antara asal dan tujuan — rute utama bersifat titik kegagalan tunggal (single point of failure).")
        r.analyze(
            "Bedah Segmen Kritis & Jalur Alternatif",
            "Analisis kontribusi segmen dan rute terbaik kedua mengukur ketahanan (resilience) rute terpilih terhadap gangguan.",
            seg_bullets,
        )

        rec_bullets = [
            f"Gunakan lintasan {' → '.join(path)} sebagai rute standar pengiriman/perjalanan."
        ]
        if alt_info:
            p2, d2 = alt_info
            rec_bullets.append(f"Tetapkan {' → '.join(p2)} sebagai rute kontingensi apabila salah satu segmen utama mengalami kemacetan/gangguan (penalti {d2 - dist:g}).")
        if rows_out:
            longest = max(rows_out, key=lambda x: x[2])
            rec_bullets.append(f"Fokuskan perbaikan infrastruktur/efisiensi waktu pada segmen {longest[0]} → {longest[1]} karena berkontribusi paling besar pada total jarak.")
        r.analyze("Rekomendasi Operasional", "Langkah mitigasi dan pengelolaan rute:", rec_bullets)
        return r
