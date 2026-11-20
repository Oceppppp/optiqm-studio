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
            if u == v:
                continue
            if G.has_edge(u, v):
                if w < G[u][v]["weight"]:
                    G[u][v]["weight"] = w
            else:
                G.add_edge(u, v, weight=w)
            edges.append((u, v, w))

        if G.number_of_nodes() == 0:
            raise InputError("Tidak ada sisi antar simpul yang valid.")
        if not nx.is_connected(G):
            raise SolverError("Graf tidak terhubung; beberapa simpul terpisah.")

        T = nx.minimum_spanning_tree(G, algorithm="kruskal")
        chosen = {(u, v) for u, v in T.edges()} | {(v, u) for u, v in T.edges()}
        total_w = float(sum(d["weight"] for _, _, d in T.edges(data=True)))

        r = ModuleResult()
        r.metric("Total Panjang / Biaya Minimum", total_w, highlight=True)
        r.metric("Jumlah Koneksi Terpilih", T.number_of_edges())
        r.metric("Jumlah Simpul", G.number_of_nodes())

        mst_rows = sorted([[u, v, float(d["weight"])] for u, v, d in T.edges(data=True)], key=lambda x: x[2])
        r.table("Sisi Terpilih (MST)", ["Simpul 1", "Simpul 2", "Jarak/Biaya"], mst_rows)
        r.chart("Diagram Minimal Spanning Tree", "network", {
            "directed": False,
            "nodes": [{"id": n, "label": n, "highlight": True} for n in G.nodes],
            "edges": [{"source": u, "target": v, "label": f"{w:g}", "highlight": (u, v) in chosen}
                      for u, v, w in edges],
        })
        r.interpretation = f"Minimal Spanning Tree menghubungkan {G.number_of_nodes()} simpul dengan total {total_w:g}."

        # Analisis mendalam
        full_w = float(sum(d["weight"] for _, _, d in G.edges(data=True)))
        saved_w = full_w - total_w
        saved_pct = (saved_w / full_w * 100.0) if full_w > 0 else 0.0
        unused = sorted(
            [(float(d["weight"]), u, v) for u, v, d in G.edges(data=True) if (u, v) not in chosen],
            key=lambda x: x[0],
        )
        r.analyze(
            "Metodologi Algoritma Kruskal & Efisiensi Jaringan",
            f"Algoritma Kruskal memilih {T.number_of_edges()} sisi termurah (tepat V−1 = {G.number_of_nodes() - 1} koneksi) "
            "yang menghubungkan seluruh simpul tanpa membentuk siklus.",
            [
                f"Total bobot MST = {' + '.join(f'{row[2]:g}' for row in mst_rows)} = {total_w:,.4g}.",
                f"Penghematan dibanding membangun seluruh {G.number_of_edges()} sisi kandidat (total {full_w:,.4g}): "
                f"hemat {saved_w:,.4g} ({saved_pct:.1f}%) dan mengeleminasi {len(unused)} koneksi redundan.",
            ],
        )

        degrees = sorted(T.degree(), key=lambda x: (-x[1], str(x[0])))
        hub_node, hub_deg = degrees[0]
        leaves = [n for n, deg in degrees if deg == 1]
        heaviest = mst_rows[-1] if mst_rows else None
        struct_bullets = [
            f"Simpul pusat (hub) utama: '{hub_node}' terhubung ke {hub_deg} cabang sekaligus — jaga keandalan simpul ini agar tidak memecah jaringan.",
            f"Jumlah simpul ujung (leaf, derajat 1): {len(leaves)} simpul ({', '.join(str(x) for x in leaves[:6])}{'...' if len(leaves) > 6 else ''}).",
        ]
        if heaviest:
            struct_bullets.append(
                f"Sisi termahal yang wajib dipertahankan: {heaviest[0]} — {heaviest[1]} (bobot {heaviest[2]:g}, "
                f"{(heaviest[2] / total_w * 100.0) if total_w > 0 else 0.0:.1f}% dari total MST)."
            )
        r.analyze(
            "Bedah Topologi & Titik Kritis Konektivitas",
            "Struktur pohon rentang minimum memiliki efisiensi biaya maksimal tetapi tanpa jalur cadangan (zero redundancy).",
            struct_bullets,
        )

        rec_bullets = [
            "Bangun tepat koneksi pada tabel 'Sisi Terpilih (MST)' untuk mencapai biaya instalasi kabel/pipa/jaringan paling rendah."
        ]
        if unused:
            w_b, u_b, v_b = unused[0]
            rec_bullets.append(
                f"Jika dibutuhkan redundansi (backup ring) agar jaringan tahan terhadap 1 kegagalan jalur, tambahan sisi termurah berikutnya adalah "
                f"{u_b} — {v_b} (tambahan biaya {w_b:g} atau +{(w_b / total_w * 100.0) if total_w > 0 else 0.0:.1f}%)."
            )
        r.analyze("Rekomendasi Desain Jaringan", "Pertimbangan antara biaya minimum dan ketahanan jaringan:", rec_bullets)
        return r
