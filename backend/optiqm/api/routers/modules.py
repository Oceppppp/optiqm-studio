"""Router API untuk katalog modul & unduh template Excel/CSV."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from optiqm.core import ModuleNotFound, all_modules, get
from optiqm.io import sheet_to_csv, sheets_to_xlsx
from optiqm.services import sample_workbook_items

router = APIRouter(prefix="/api", tags=["modules"])


@router.get("/modules")
def list_modules():
    mods = all_modules()
    return {"count": len(mods), "modules": [m.metadata() for m in mods]}


@router.get("/modules/{key}/template")
def download_template(key: str, format: str = Query("xlsx", pattern="^(xlsx|csv)$")):
    try:
        mod = get(key)
    except ModuleNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    tpl = mod.template()
    tpl.params["module"] = mod.key
    prefix = mod.sheet_prefixes[0] if mod.sheet_prefixes else mod.key.upper()
    if format == "csv":
        data = sheet_to_csv(tpl)
        return Response(data, media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="{prefix}_{mod.key}.csv"'})
    data = sheets_to_xlsx([(f"{prefix}_Contoh", tpl)])
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{prefix}_{mod.key}.xlsx"'})


@router.get("/templates/sample-workbook.xlsx")
def download_sample_workbook():
    data = sheets_to_xlsx(sample_workbook_items())
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="OptiQM_Sample_10_Modul.xlsx"'})
