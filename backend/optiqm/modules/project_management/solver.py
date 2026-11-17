"""Solver CPM & PERT (ES, EF, LS, LF, Slack, jalur kritis, varians & probabilitas)."""

from __future__ import annotations

from dataclasses import dataclass
import math

import networkx as nx
from scipy.stats import norm

from optiqm.core import InputError


@dataclass
class Activity:
    name: str
    preds: list[str]
    time: float
    variance: float = 0.0


def parse_preds(raw: object) -> list[str]:
    if raw is None:
        return []
    s = str(raw).strip()
    if not s or s.lower() in {"-", "none", "nan", "null"}:
        return []
    return [x.strip() for x in s.replace(";", ",").split(",") if x.strip() and x.strip() != "-"]


def solve_cpm_pert(activities: list[Activity], target_time: float | None = None) -> dict:
    by_name = {a.name: a for a in activities}
    G = nx.DiGraph()
    for a in activities:
        G.add_node(a.name)
    for a in activities:
        for pr in a.preds:
            if pr not in by_name:
                raise InputError(f"Aktivitas pendahulu '{pr}' pada '{a.name}' tidak ditemukan.")
            G.add_edge(pr, a.name)

    if not nx.is_directed_acyclic_graph(G):
        raise InputError("Jaringan proyek mengandung siklus (circular dependency).")

    order = list(nx.topological_sort(G))
    es, ef = {}, {}
    for u in order:
        preds = list(G.predecessors(u))
        es[u] = max((ef[p] for p in preds), default=0.0)
        ef[u] = es[u] + by_name[u].time

    duration = max(ef.values(), default=0.0)
    ls, lf, slack = {}, {}, {}
    for u in reversed(order):
        succs = list(G.successors(u))
        lf[u] = min((ls[s] for s in succs), default=duration)
        ls[u] = lf[u] - by_name[u].time
        slack[u] = max(0.0, ls[u] - es[u])

    critical = {u for u in order if slack[u] < 1e-7}
    # Cari satu jalur kritis dari simpul awal kritis ke simpul akhir kritis
    crit_sub = G.subgraph(critical)
    starts = [u for u in crit_sub if crit_sub.in_degree(u) == 0]
    ends = [u for u in crit_sub if crit_sub.out_degree(u) == 0 and abs(ef[u] - duration) < 1e-7]
    crit_paths = []
    for st in starts:
        for en in ends:
            for path in nx.all_simple_paths(crit_sub, st, en):
                if abs(sum(by_name[n].time for n in path) - duration) < 1e-6:
                    crit_paths.append(path)
    if not crit_paths and critical:
        crit_paths = [[u for u in order if u in critical]]

    var_total = sum(by_name[u].variance for u in crit_paths[0]) if crit_paths else 0.0
    std_total = math.sqrt(var_total)
    prob = None
    z = None
    if target_time is not None and std_total > 1e-9:
        z = (target_time - duration) / std_total
        prob = float(norm.cdf(z))
    elif target_time is not None:
        prob = 1.0 if target_time >= duration else 0.0

    return {
        "order": order, "G": G, "by_name": by_name, "es": es, "ef": ef, "ls": ls, "lf": lf,
        "slack": slack, "critical": critical, "crit_paths": crit_paths,
        "duration": duration, "variance": var_total, "std": std_total, "z": z, "prob": prob,
    }
