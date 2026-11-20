"""Modul Locational Break-Even Analysis."""

from __future__ import annotations

import pandas as pd

from optiqm.core import BaseModule, ModuleResult, ParamSpec, SheetData, register
from optiqm.modules.cost_volume.module import CostVolume


@register
class LocationBreakeven(BaseModule):
    key = "location_breakeven"
    name = "Location Break-Even"
    category = "Lokasi & Tata Letak"
    description = "Analisis titik impas pemilihan lokasi berdasarkan biaya tetap dan biaya variabel per unit."
    sheet_prefixes = ("LBE", "LOCBEP")
    params = (ParamSpec("volume", "Volume Produksi Rencana", "number", 2000.0),)
    table_hint = "Kolom: Location (atau Alternative), Fixed_Cost, Variable_Cost."

    def template(self) -> SheetData:
        # Akron / Bowling Green / Chicago (Heizer & Render)
        df = pd.DataFrame(
            [["Akron", 30000, 75], ["Bowling Green", 60000, 45], ["Chicago", 110000, 25]],
            columns=["Location", "Fixed_Cost", "Variable_Cost"],
        )
        return SheetData(params={"volume": 2000}, tables={"main": df})

    def solve(self, data: SheetData) -> ModuleResult:
        p = self.resolved_params(data)
        merged = SheetData(params={**data.params, "volume": p["volume"]}, tables=data.tables)
        return CostVolume().solve(merged, entity_label="lokasi")
