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
            items[nm] = ItemInfo(nm, lt, oh, ls)

        edges: list[BOMEdge] = []
        if bom_df is not None and len(bom_df) > 0:
            c_par = find_column(bom_df, ["Parent", "Induk"])
            c_chi = find_column(bom_df, ["Child", "Anak", "Component"])
            c_qty = find_column(bom_df, ["Qty", "Jumlah", "Usage"])
            for i in range(len(bom_df)):
                edges.append(BOMEdge(str(bom_df.at[i, c_par]).strip(),
                                     str(bom_df.at[i, c_chi]).strip(),
                                     to_float(bom_df.at[i, c_qty], f"BOM Qty baris {i + 1}")))

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
            mps.setdefault(nm, {})[per] = mps.get(nm, {}).get(per, 0.0) + gr
            if c_ms and not pd.isna(mps_df.at[i, c_ms]):
                sr = to_float(mps_df.at[i, c_ms])
                sched.setdefault(nm, {})[per] = sched.get(nm, {}).get(per, 0.0) + sr

        res = explode_mrp(items, edges, mps, sched, horizon)
        r = ModuleResult()
        r.metric("Jumlah Item", len(res), highlight=True)
        r.metric("Horizon", horizon, unit="periode")
        r.metric("Total Planned Releases", sum(sum(it["porel"]) for it in res), highlight=True)

        summary_rows = []
        cols = ["Item / Baris", *[f"P{t}" for t in range(1, horizon + 1)]]
        for it in res:
            summary_rows.append([it["item"], it["level"], it["lead_time"], it["on_hand"],
                                 "L4L" if it["lot_size"] == 0 else f"FOQ={it['lot_size']:g}",
                                 sum(it["gr"]), sum(it["porel"])])
            r.table(f"Jadwal MRP — {it['item']} (Level {it['level']}, LT={it['lead_time']})", cols, [
                ["Gross Requirements", *it["gr"][1:]],
                ["Scheduled Receipts", *it["sr"][1:]],
                ["Projected On Hand", *it["poh"][1:]],
                ["Net Requirements", *it["nr"][1:]],
                ["Planned Order Receipts", *it["por"][1:]],
                ["Planned Order Releases", *it["porel"][1:]],
            ])
        r.table("Ringkasan Item MRP",
                ["Item", "Level", "LT", "Stok Awal", "Lot Sizing", "Total Gross Req.", "Total Planned Release"],
                summary_rows)
        r.interpretation = f"MRP selesai untuk {len(res)} item sepanjang {horizon} periode."
        return r
