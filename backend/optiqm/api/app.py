"""FastAPI app factory (API + static frontend untuk mode produksi/desktop)."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from optiqm import __version__
from optiqm.core import all_modules, discover

from .routers.batch_report import router as batch_router
from .routers.modules import router as modules_router
from .routers.workspace import router as workspace_router


def _find_static_dir() -> Path | None:
    here = Path(__file__).resolve()
    candidates = [
        here.parents[3] / "frontend" / "dist",
        here.parents[2] / "static",
    ]
    for p in candidates:
        if (p / "index.html").is_file():
            return p
    return None


def create_app() -> FastAPI:
    discover()
    app = FastAPI(title="OptiQM Studio API", version=__version__)
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
    )
    app.include_router(modules_router)
    app.include_router(workspace_router)
    app.include_router(batch_router)

    @app.exception_handler(Exception)
    async def _unhandled_exc(_request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=500, content={"detail": f"{type(exc).__name__}: {exc}"})

    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": __version__, "modules": len(all_modules())}

    static_dir = None if os.environ.get("VERCEL") else _find_static_dir()
    if static_dir is not None:
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="ui")
    return app


app = create_app()
