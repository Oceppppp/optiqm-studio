"""Modul Assembly Line Balancing (Heizer & Render)."""

from __future__ import annotations

import math

import networkx as nx
import pandas as pd

from optiqm.core import BaseModule, InputError, ModuleResult, ParamSpec, SheetData, register
from optiqm.core.parsing import clean_frame, find_column, require_rows, to_float
from optiqm.modules.project_management.solver import parse_preds

RULES = ("longest_task_time", "most_following_tasks", "ranked_positional_weight",
         "shortest_task_time", "fewest_following_tasks")


@register
class LineBalancing(BaseModule):
    key = "line_balancing"
    name = "Assembly Line Balancing"
    category = "Penjadwalan"
    description = "Penyeimbangan lini perakitan (Cycle Time, jumlah stasiun kerja minimum, dan penugasan tugas)."
    sheet_prefixes = ("LINE", "BALANCING")
    params = (
        ParamSpec("rule", "Aturan Heuristik", "choice", "longest_task_time", RULES),
        ParamSpec("production_time", "Waktu Produksi Tersedia / Hari (menit/detik)", "number", 480.0),
        ParamSpec("demand", "Target Output / Hari (unit)", "number", 40.0),
        ParamSpec("cycle_time", "Atau Cycle Time Manual (0 = hitung otomatis)", "number", 0.0),
    )
    table_hint = "Kolom: Task, Time, Predecessors."

    def template(self) -> SheetData:
        # Boeing / Wing Manufacturing contoh klasik Heizer & Render: total time=65, cycle=12 -> min 6 stasiun
        df = pd.DataFrame(
            [["A", 10, "-"], ["B", 11, "A"], ["C", 5, "B"], ["D", 4, "B"],
             ["E", 12, "A"], ["F", 3, "C, D"], ["G", 7, "F"], ["H", 11, "E"], ["I", 3, "G, H"]],
            columns=["Task", "Time", "Predecessors"],
        )
        return SheetData(params={"rule": "longest_task_time", "production_time": 480, "demand": 40, "cycle_time": 0},
                         tables={"main": df})

    def solve(self, data: SheetData) -> ModuleResult:
        p = self.resolved_params(data)
        ct = float(p["cycle_time"])
        if ct <= 0:
            if float(p["demand"]) <= 0 or float(p["production_time"]) <= 0:
                raise InputError("Waktu produksi dan target demand harus > 0.")
            ct = float(p["production_time"]) / float(p["demand"])

        df = clean_frame(data.table("main"))
        require_rows(df, 1, "Tabel tugas perakitan")
        c_tsk = find_column(df, ["Task", "Tugas", "Activity", "ID"])
        c_t = find_column(df, ["Time", "Waktu", "Duration"])
        c_pred = find_column(df, ["Predecessors", "Predecessor", "Pendahulu"], required=False)

        tasks: dict[str, dict] = {}
        G = nx.DiGraph()
        for i in range(len(df)):
            nm = str(df.at[i, c_tsk]).strip()
            if nm in tasks:
                raise InputError(f"Nama tugas duplikat ditemukan: '{nm}'.")
            t = to_float(df.at[i, c_t], f"Time {nm}")
            if t <= 0:
                raise InputError(f"Waktu tugas '{nm}' harus > 0.")
            if t > ct + 1e-9:
                raise InputError(f"Waktu tugas '{nm}' ({t:g}) melebihi Cycle Time ({ct:g}).")
            preds = parse_preds(df.at[i, c_pred]) if c_pred else []
            tasks[nm] = {"time": t, "preds": preds}
            G.add_node(nm)
        for nm, info in tasks.items():
            for pr in info["preds"]:
                if pr not in tasks:
                    raise InputError(f"Pendahulu '{pr}' pada tugas '{nm}' tidak ditemukan.")
                G.add_edge(pr, nm)
        if not nx.is_directed_acyclic_graph(G):
            raise InputError("Graf tugas mengandung siklus.")

        desc_count = {n: len(nx.descendants(G, n)) for n in G}
        rpw = {n: tasks[n]["time"] + sum(tasks[d]["time"] for d in nx.descendants(G, n)) for n in G}

        def run_rule(rule_name: str) -> list[list[str]]:
            def score(n: str):
                if rule_name == "longest_task_time":
                    return (-tasks[n]["time"], -desc_count[n], n)
                if rule_name == "shortest_task_time":
                    return (tasks[n]["time"], -desc_count[n], n)
                if rule_name == "most_following_tasks":
                    return (-desc_count[n], -tasks[n]["time"], n)
                if rule_name == "fewest_following_tasks":
                    return (desc_count[n], -tasks[n]["time"], n)
                return (-rpw[n], -tasks[n]["time"], n)

            unassigned = set(tasks.keys())
            assigned: set[str] = set()
            sts: list[list[str]] = []
            while unassigned:
                rem = ct
                st_tasks = []
                while True:
                    elig = [n for n in unassigned if all(pr in assigned for pr in tasks[n]["preds"]) and tasks[n]["time"] <= rem + 1e-9]
                    if not elig:
                        break
                    pick = min(elig, key=score)
                    st_tasks.append(pick)
                    unassigned.remove(pick)
                    assigned.add(pick)
                    rem -= tasks[pick]["time"]
                if not st_tasks:
                    raise InputError("Tidak dapat menjadwalkan tugas ke stasiun dalam batas cycle time.")
                sts.append(st_tasks)
            return sts

        stations = run_rule(p["rule"])
        all_rules_res = {rl: run_rule(rl) for rl in RULES}

        total_t = sum(info["time"] for info in tasks.values())
        min_theo = math.ceil(total_t / ct - 1e-9)
        actual_st = len(stations)
        eff = total_t / (actual_st * ct) * 100.0
        balance_delay = 100.0 - eff
        idle_total = actual_st * ct - total_t

        r = ModuleResult()
        r.metric("Cycle Time", ct, highlight=True)
        r.metric("Jumlah Stasiun Kerja", actual_st, highlight=True)
        r.metric("Minimum Teoritis Stasiun", min_theo)
        r.metric("Efisiensi Lini", f"{eff:.2f}%", highlight=True)
        r.metric("Total Idle Time / Siklus", idle_total)

        st_rows = []
        for idx, st in enumerate(stations, start=1):
            used = sum(tasks[n]["time"] for n in st)
            st_rows.append([f"Stasiun {idx}", ", ".join(st), used, ct - used, used / ct * 100.0])
        r.table("Penugasan Stasiun Kerja", ["Stasiun", "Tugas", "Waktu Terpakai", "Idle Time", "Utilisasi (%)"], st_rows)
        r.chart("Diagram Preseden Tugas", "network", {
            "directed": True,
            "nodes": [{"id": n, "label": f"{n} ({tasks[n]['time']:g})", "highlight": False} for n in G.nodes],
            "edges": [{"source": u, "target": v, "label": "", "highlight": False} for u, v in G.edges],
        })
        r.interpretation = f"Dengan cycle time {ct:g}, terbentuk {actual_st} stasiun kerja (minimum teoritis {min_theo}) dengan efisiensi {eff:.2f}%."

        # Analisis mendalam
        max_st = max(st_rows, key=lambda row: row[2])
        min_st = min(st_rows, key=lambda row: row[2])
        eff_ct = max_st[2]
        prod_t = float(p["production_time"])
        cap_actual = (prod_t / eff_ct) if (prod_t > 0 and eff_ct > 0) else 0.0
        r.analyze(
            "Metodologi Penyeimbangan Lini Perakitan",
            f"Total waktu seluruh {len(tasks)} elemen kerja = {total_t:g} dengan Cycle Time (CT) = {ct:g}. "
            f"Batas minimum teoritis = ⌈{total_t:g} / {ct:g}⌉ = {min_theo} stasiun kerja.",
            [
                f"Efisiensi Lini = Σt / (N × CT) = {total_t:g} / ({actual_st} × {ct:g}) = {eff:.2f}% (Balance Delay = {balance_delay:.2f}%).",
                f"Total waktu menganggur (idle time) = {idle_total:g} satuan waktu per siklus di seluruh {actual_st} stasiun.",
                f"Stasiun terpadat (bottleneck): {max_st[0]} ({max_st[2]:g}/{ct:g}, utilisasi {max_st[4]:.1f}%); "
                f"stasiun paling longgar: {min_st[0]} ({min_st[2]:g}/{ct:g}, idle {min_st[3]:g}).",
            ],
        )

        best_rule_k = min(RULES, key=lambda rl: (len(all_rules_res[rl]), rl != p["rule"]))
        rule_bullets = [
            f"Aturan '{rl}': {len(all_rules_res[rl])} stasiun kerja (efisiensi {total_t / (len(all_rules_res[rl]) * ct) * 100.0:.2f}%)"
            + (" ← aturan aktif" if rl == p["rule"] else "")
            for rl in RULES
        ]
        if cap_actual > 0:
            rule_bullets.append(
                f"Kapasitas Output Maksimal Aktual berdasarkan bottleneck ({eff_ct:g}): {cap_actual:,.1f} unit/hari (waktu tersedia {prod_t:g})."
            )
        r.analyze(
            "Perbandingan 5 Aturan Heuristik & Kapasitas Bottleneck",
            "Perbandingan lintas aturan heuristik memastikan Anda memperoleh jumlah stasiun kerja paling ramping:",
            rule_bullets,
        )

        rec_bullets = []
        if actual_st == min_theo:
            rec_bullets.append(f"Solusi saat ini SUDAH OPTIMAL secara teoritis ({actual_st} stasiun = batas bawah teoritis {min_theo}).")
        elif len(all_rules_res[best_rule_k]) < actual_st:
            rec_bullets.append(
                f"Ganti aturan heuristik ke '{best_rule_k}' untuk memangkas jumlah stasiun dari {actual_st} menjadi {len(all_rules_res[best_rule_k])} stasiun!"
            )
        else:
            rec_bullets.append(
                f"Belum mencapai batas teoritis ({min_theo} stasiun) karena kendala urutan preseden; pertimbangkan memecah tugas besar atau sedikit menaikkan Cycle Time."
            )
        rec_bullets.append(f"Fokuskan perbaikan metode kerja (kaizen) pada {max_st[0]} (tugas: {max_st[1]}) karena stasiun ini menentukan laju throughput seluruh lini.")
        r.analyze("Rekomendasi Peningkatan Efisiensi Lini", "Langkah praktis bagi insinyur industri:", rec_bullets)
        return r
