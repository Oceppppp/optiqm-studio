"""Solver Material Requirements Planning (MRP) multi-level BOM."""

from __future__ import annotations

from dataclasses import dataclass

from optiqm.core import InputError


@dataclass
class BOMEdge:
    parent: str
    child: str
    qty: float


@dataclass
class ItemInfo:
    name: str
    lead_time: int = 1
    on_hand: float = 0.0
    lot_size: float = 0.0         # 0 = Lot-for-Lot; >0 = Fixed Order Quantity


def explode_mrp(items: dict[str, ItemInfo], edges: list[BOMEdge], mps: dict[str, dict[int, float]],
                sched: dict[str, dict[int, float]], horizon: int) -> list[dict]:
    # Hitung level BOM (0 = produk akhir / tidak punya parent)
    parents_of: dict[str, list[str]] = {k: [] for k in items}
    children_of: dict[str, list[BOMEdge]] = {k: [] for k in items}
    for e in edges:
        if e.parent == e.child:
            raise InputError(f"BOM mengandung siklus pada item '{e.parent}'.")
        children_of.setdefault(e.parent, []).append(e)
        parents_of.setdefault(e.child, []).append(e.parent)
        items.setdefault(e.parent, ItemInfo(e.parent))
        items.setdefault(e.child, ItemInfo(e.child))

    levels: dict[str, int] = {k: 0 for k in items}
    for _ in range(len(items) + 1):
        changed = False
        for e in edges:
            if levels[e.child] <= levels[e.parent]:
                levels[e.child] = levels[e.parent] + 1
                changed = True
        if not changed:
            break
    else:
        raise InputError("Struktur BOM mengandung siklus (circular dependency).")

    gross: dict[str, list[float]] = {k: [0.0] * (horizon + 1) for k in items}
    for item, per_map in mps.items():
        items.setdefault(item, ItemInfo(item))
        gross.setdefault(item, [0.0] * (horizon + 1))
        for t, q in per_map.items():
            if 1 <= t <= horizon:
                gross[item][t] += q

    order = sorted(items.keys(), key=lambda k: (levels.get(k, 0), k))
    results = []
    for name in order:
        info = items[name]
        gr = gross[name]
        sr = [sched.get(name, {}).get(t, 0.0) for t in range(horizon + 1)]
        poh = [0.0] * (horizon + 1)
        nr = [0.0] * (horizon + 1)
        por = [0.0] * (horizon + 1)
        porel = [0.0] * (horizon + 1)

        poh[0] = info.on_hand
        for t in range(1, horizon + 1):
            avail = poh[t - 1] + sr[t]
            if avail < gr[t]:
                nr[t] = gr[t] - avail
                if info.lot_size > 0:
                    lots = int(-(-nr[t] // info.lot_size))
                    por[t] = lots * info.lot_size
                else:
                    por[t] = nr[t]
                poh[t] = avail + por[t] - gr[t]
                rel_t = t - info.lead_time
                if rel_t >= 1:
                    porel[rel_t] += por[t]
                elif rel_t >= 0:
                    porel[0] += por[t]
            else:
                poh[t] = avail - gr[t]

        # Ledakkan ke komponen anak
        for e in children_of.get(name, []):
            for t in range(1, horizon + 1):
                if porel[t] > 0:
                    gross[e.child][t] += porel[t] * e.qty

        results.append({
            "item": name, "level": levels.get(name, 0), "lead_time": info.lead_time,
            "on_hand": info.on_hand, "lot_size": info.lot_size,
            "gr": gr, "sr": sr, "poh": poh, "nr": nr, "por": por, "porel": porel,
        })
    return results
