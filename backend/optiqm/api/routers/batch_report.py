"""Router API untuk eksekusi batch multi-modul & ekspor laporan."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel

from optiqm.services import export_excel, export_pdf, run_batch

router = APIRouter(prefix="/api", tags=["batch-report"])


class BatchRequest(BaseModel):
    cases: list[dict[str, Any]]


class ReportRequest(BaseModel):
    workspace_name: str = "Workspace OptiQM"
    items: list[dict[str, Any]]


@router.post("/batch/run")
def batch_run(req: BatchRequest):
    return run_batch(req.cases)


@router.post("/report/xlsx")
def report_xlsx(req: ReportRequest):
    data = export_excel(req.workspace_name, req.items)
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="OptiQM_Laporan.xlsx"'})


@router.post("/report/pdf")
def report_pdf(req: ReportRequest):
    data = export_pdf(req.workspace_name, req.items)
    return Response(data, media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="OptiQM_Laporan.pdf"'})
