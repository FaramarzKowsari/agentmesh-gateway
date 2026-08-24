# -*- mode: python ; coding: utf-8 -*-

from __future__ import annotations

import os

from PyInstaller.utils.hooks import collect_all, copy_metadata

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
SCRIPT = os.path.join(ROOT, "src", "agentmesh", "portable.py")
SRC = os.path.join(ROOT, "src")


datas = []
binaries = []
hiddenimports = []

for package in (
    "uvicorn",
    "fastapi",
    "starlette",
    "pydantic",
    "pydantic_core",
    "typer",
    "click",
    "httpx",
    "httpcore",
    "anyio",
    "websockets",
    "httptools",
    "watchfiles",
):
    try:
        package_datas, package_binaries, package_hiddenimports = collect_all(package)
    except Exception:
        continue
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports

for distribution in (
    "uvicorn",
    "fastapi",
    "starlette",
    "pydantic",
    "typer",
    "click",
    "httpx",
    "httpcore",
    "anyio",
):
    try:
        datas += copy_metadata(distribution)
    except Exception:
        continue

analysis = Analysis(
    [SCRIPT],
    pathex=[SRC],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name="AgentMesh-Gateway",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
