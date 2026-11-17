# -*- mode: python ; coding: utf-8 -*-
"""Konfigurasi PyInstaller untuk membungkus OptiQM Studio (API + UI statis) jadi 1 file/folder executable."""

from pathlib import Path

ROOT = Path(SPECPATH).parent
FRONTEND_DIST = ROOT / "frontend" / "dist"
BACKEND = ROOT / "backend"

datas = []
if FRONTEND_DIST.exists():
    datas.append((str(FRONTEND_DIST), "optiqm/static"))

a = Analysis(
    [str(ROOT / "desktop" / "launcher.py")],
    pathex=[str(BACKEND)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "optiqm.modules",
        "uvicorn.logging",
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.lifespan.on",
        "scipy.special._cdflib",
    ],
    collect_submodules=["optiqm.modules", "scipy.optimize", "scipy.stats"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="OptiQM-Studio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
