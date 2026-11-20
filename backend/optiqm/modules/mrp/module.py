"""Modul Material Requirements Planning (MRP)."""

from __future__ import annotations

import pandas as pd

from optiqm.core import BaseModule, InputError, ModuleResult, ParamSpec, SheetData, register
from optiqm.core.parsing import clean_frame, find_column, require_rows, to_float

from .solver import BOMEdge, ItemInfo, explode_mrp


@register
class MRP(BaseModule):
    key = "mrp"
    name = "MRP (Material Requirements Planning)"
    category = "Perencanaan Produksi"
    description = "Perhitungan kebutuhan material bertingkat (BOM explosion, net requirements, planned order releases)."
    sheet_prefixes = ("MRP",)
    params = (ParamSpec("horizon", "Horizon Periode", "integer", 8),)
    table_hint = ("Gunakan 3 blok tabel: [main] (atau [bom]) kolom Parent, Child, Qty; "
                  "[items] kolom Item, Lead_Time, On_Hand, Lot_Size (0=L4L); "
                  "[mps] kolom Item, Period, Gross_Requirement (dan opsional Scheduled_Receipt).")

    def template(self) -> SheetData:
        # Speaker Kit A (Heizer & Render): A -> 2B + 3C; B -> 2D + 2E
        bom = pd.DataFrame(
            [["A", "B", 2], ["A", "C", 3], ["B", "D", 2], ["B", "E", 2]],
            columns=["Parent", "Child", "Qty"],
        )
        items = pd.DataFrame(
            [["A", 1, 10, 0], ["B", 2, 15, 0], ["C", 1, 20, 0], ["D", 1, 10, 0], ["E", 2, 5, 0]],
            columns=["Item", "Lead_Time", "On_Hand", "Lot_Size"],
        )
        mps = pd.DataFrame(
            [["A", 8, 50, 0], ["A", 6, 20, 0]],
            columns=["Item", "Period", "Gross_Requirement", "Scheduled_Receipt"],
        )
        return SheetData(params={"horizon": 8}, tables={"main": bom, "items": items, "mps": mps})

    def solve(self, data: SheetData) -> ModuleResult:
        p = self.resolved_params(data)
        horizon = int(p["horizon"])
        if horizon < 1:
            raise InputError("Horizon periode harus >= 1.")

        bom_df = clean_frame(data.table("bom", required=False) if "bom" in data.tables else data.table("main"))
        items_df = clean_frame(data.table("items"))
        mps_df = clean_frame(data.table("mps"))
        require_rows(items_df, 1, "Tabel [items]")
        require_rows(mps_df, 1, "Tabel [mps]")

        c_item = find_column(items_df, ["Item", "Komponen", "Part"])
        c_lt = find_column(items_df, ["Lead_Time", "LT", "LeadTime"])
        c_oh = find_column(items_df, ["On_Hand", "OnHand", "StokAwal", "Inventory"], required=False)
        c_ls = find_column(items_df, ["Lot_Size", "LotSize", "Lot"], required=False)

        items: dict[str, ItemInfo] = {}
        for i in range(len(items_df)):
            nm = str(items_df.at[i, c_item]).strip()
            lt = int(round(to_float(items_df.at[i, c_lt], f"LT {nm}")))
            oh = to_float(items_df.at[i, c_oh]) if c_oh and not pd.isna(items_df.at[i, c_oh]) else 0.0
            ls = to_float(items_df.at[i, c_ls]) if c_ls and not pd.isna(items_df.at[i, c_ls]) else 0.0
            if lt < 0 or oh < 0 or ls < 0:
                raise InputError(f"Lead_Time, On_Hand, dan Lot_Size pada '{nm}' tidak boleh negatif.")
            items[nm] = ItemInfo(nm, lt, oh, ls)

        edges: list[BOMEdge] = []
        if bom_df is not None and len(bom_df) > 0:
            c_par = find_column(bom_df, ["Parent", "Induk"])
            c_chi = find_column(bom_df, ["Child", "Anak", "Component"])
            c_qty = find_column(bom_df, ["Qty", "Jumlah", "Usage"])
            for i in range(len(bom_df)):
                qty_v = to_float(bom_df.at[i, c_qty], f"BOM Qty baris {i + 1}")
                if qty_v <= 0:
                    raise InputError(f"BOM Qty baris {i + 1} harus > 0.")
                edges.append(BOMEdge(str(bom_df.at[i, c_par]).strip(),
                                     str(bom_df.at[i, c_chi]).strip(), qty_v))

        c_mi = find_column(mps_df, ["Item", "Produk"])
        c_mp = find_column(mps_df, ["Period", "Periode"])
        c_mg = find_column(mps_df, ["Gross_Requirement", "Demand", "Qty", "Gross"])
        c_ms = find_column(mps_df, ["Scheduled_Receipt", "SR", "Receipt"], required=False)
        mps: dict[str, dict[int, float]] = {}
        sched: dict[str, dict[int, float]] = {}
        for i in range(len(mps_df)):
            nm = str(mps_df.at[i, c_mi]).strip()
            per = int(round(to_float(mps_df.at[i, c_mp], "Period MPS")))
            gr = to_float(mps_df.at[i, c_mg], "Gross MPS")
            if gr < 0:
                raise InputError(f"Gross_Requirement MPS baris {i + 1} tidak boleh negatif.")
            mps.setdefault(nm, {})[per] = mps.get(nm, {}).get(per, 0.0) + gr
            if c_ms and not pd.isna(mps_df.at[i, c_ms]):
                sr = to_float(mps_df.at[i, c_ms])
                if sr < 0:
                    raise InputError(f"Scheduled_Receipt MPS baris {i + 1} tidak boleh negatif.")
                sched.setdefault(nm, {})[per] = sched.get(nm, {}).get(per, 0.0) + sr

        res = explode_mrp(items, edges, mps, sched, horizon)
        r = ModuleResult()
        r.metric("Jumlah Item", len(res), highlight=True)
        r.metric("Horizon", horizon, unit="periode")
        r.metric("Total Planned Releases", sum(sum(it["porel"]) for it in res), highlight=True)

        has_past_due = any(it["past_due"] > 1e-9 for it in res)
        summary_rows = []
        cols = (["Item / Baris", "Past Due (≤P0)", *[f"P{t}" for t in range(1, horizon + 1)]]
                if has_past_due else ["Item / Baris", *[f"P{t}" for t in range(1, horizon + 1)]])
        for it in res:
            if it["past_due"] > 1e-9:
                r.warnings.append(
                    f"Item '{it['item']}' memiliki Planned Order Release melewati batas awal (Past Due = {it['past_due']:g} unit) "
                    f"karena lead time kumulatif melebihi periode jatuh tempo — perlu percepatan atau stok darurat!"
                )
            summary_rows.append([it["item"], it["level"], it["lead_time"], it["on_hand"],
                                 "L4L" if it["lot_size"] == 0 else f"FOQ={it['lot_size']:g}",
                                 sum(it["gr"]), sum(it["porel"])])
            sl = slice(0, None) if has_past_due else slice(1, None)
            r.table(f"Jadwal MRP — {it['item']} (Level {it['level']}, LT={it['lead_time']})", cols, [
                ["Gross Requirements", *it["gr"][sl]],
                ["Scheduled Receipts", *it["sr"][sl]],
                ["Projected On Hand", *it["poh"][sl]],
                ["Net Requirements", *it["nr"][sl]],
                ["Planned Order Receipts", *it["por"][sl]],
                ["Planned Order Releases", *it["porel"][sl]],
            ])
        r.table("Ringkasan Item MRP",
                ["Item", "Level", "LT", "Stok Awal", "Lot Sizing", "Total Gross Req.", "Total Planned Release"],
                summary_rows)
        r.interpretation = f"MRP selesai untuk {len(res)} item sepanjang {horizon} periode."

        # Analisis mendalam
        max_level = max((it["level"] for it in res), default=0)
        cum_lt_map: dict[str, int] = {}
        parent_edges: dict[str, list[BOMEdge]] = {}
        for e in edges:
            parent_edges.setdefault(e.child, []).append(e)
        for it in res:
            nm = it["item"]
            par_lt = max((cum_lt_map.get(e.parent, 0) for e in parent_edges.get(nm, [])), default=0)
            cum_lt_map[nm] = par_lt + it["lead_time"]
        longest_item, longest_cum_lt = max(cum_lt_map.items(), key=lambda x: x[1])
        r.analyze(
            "Metodologi Ledakan BOM (Low-Level Coding) & Netting MRP",
            f"Struktur produk memiliki {max_level + 1} tingkat BOM (Level 0 s.d. Level {max_level}) dengan {len(res)} item. "
            "MRP menghitung kebutuhan bersih (NR = GR − POH − SR) lalu menggeser rilis pesanan mundur sesuai Lead Time (time-phasing) "
            "dan meledakkan rilis induk ke kebutuhan kotor komponen anak.",
            [
                f"Lead time kumulatif terpanjang mencapai {longest_cum_lt} periode pada komponen '{longest_item}' — menjadi pembatas kecepatan respons pesanan baru.",
                f"Total kebutuhan kotor kumulatif seluruh level = {sum(sum(it['gr']) for it in res):,.0f} unit; total rilis pesanan terencana = {sum(sum(it['porel']) for it in res):,.0f} unit.",
            ],
        )

        # Jadwal rilis paling mendesak
        urgent = []
        for it in res:
            if it["past_due"] > 1e-9:
                urgent.append((0, it["item"], it["past_due"]))
            for t in range(1, horizon + 1):
                if it["porel"][t] > 1e-9:
                    urgent.append((t, it["item"], it["porel"][t]))
                    break
        urgent.sort(key=lambda x: (x[0], x[1]))
        rel_bullets = [
            f"Item '{nm}': rilis pertama {'SEGERA (Past Due)' if t == 0 else f'pada Periode P{t}'} sebanyak {q:g} unit."
            for t, nm, q in urgent[:6]
        ] or ["Tidak ada pesanan baru yang perlu dirilis sepanjang horizon karena seluruh kebutuhan tertutup stok awal/SR."]
        r.analyze(
            "Bedah Jadwal Rilis Kritis & Keterkaitan Komponen",
            "Urutan rilis paling awal menentukan komponen mana yang harus segera diterbitkan Purchase Order / Work Order-nya:",
            rel_bullets,
        )

        rec_bullets = []
        if has_past_due:
            rec_bullets.append("PRIORITAS TINGGI: Segera expediting pemasok atau gunakan stok pengaman untuk item yang berstatus Past Due agar MPS produk akhir tidak meleset.")
        else:
            rec_bullets.append("Seluruh rilis pesanan masih berada di dalam horizon perencanaan (P1..P" + str(horizon) + "), jadwal MPS layak dieksekusi.")
        rec_bullets.append(
            f"Perhatikan komponen '{longest_item}' (lead time kumulatif {longest_cum_lt} periode): pemangkasan lead time pada jalur BOM ini paling efektif mempercepat siklus manufaktur."
        )
        r.analyze("Rekomendasi Eksekusi MRP", "Tindak lanjut bagi bagian PPIC dan pengadaan:", rec_bullets)
        return r
