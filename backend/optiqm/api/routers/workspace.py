"""Router API untuk upload file, import Google Sheets, dan validasi kasus."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from optiqm.core import OptiQMError
from optiqm.services import import_bytes, import_google_sheet, validate_case

router = APIRouter(prefix="/api/workspace", tags=["workspace"])


class GSheetRequest(BaseModel):
    url: str


class ValidateRequest(BaseModel):
    module: str | None
    sheet: dict[str, Any]


@router.post("/import")
async def import_files(files: list[UploadFile] = File(...)):
    cases = []
    for f in files:
        content = await f.read()
        try:
            cases.extend(import_bytes(content, f.filename or "upload.xlsx"))
        except OptiQMError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"count": len(cases), "cases": cases}


@router.post("/import-gsheet")
def import_gsheet(req: GSheetRequest):
    try:
        cases = import_google_sheet(req.url)
    except OptiQMError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"count": len(cases), "cases": cases}


@router.post("/validate")
def validate(req: ValidateRequest):
    status, err = validate_case(req.module, req.sheet)
    return {"status": status, "error": err}
