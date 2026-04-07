# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for PnLClaw local-api sidecar."""

import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH).resolve().parent.parent
SVC = ROOT / "services" / "local-api"

block_cipher = None

# ---------------------------------------------------------------------------
# Data files: strategy templates, skills, demo strategies
# ---------------------------------------------------------------------------
datas = []

templates_dir = ROOT / "packages" / "strategy-engine" / "pnlclaw_strategy" / "templates"
if templates_dir.is_dir():
    for f in templates_dir.glob("*.yaml"):
        datas.append((str(f), "pnlclaw_strategy/templates"))

skills_dir = ROOT / "skills"
if skills_dir.is_dir():
    for f in skills_dir.rglob("*.md"):
        rel = f.relative_to(ROOT)
        datas.append((str(f), str(rel.parent)))

demo_dir = ROOT / "demo" / "strategies"
if demo_dir.is_dir():
    for f in demo_dir.glob("*.yaml"):
        datas.append((str(f), "demo/strategies"))

# ---------------------------------------------------------------------------
# Hidden imports: all community packages + uvicorn internals
# ---------------------------------------------------------------------------
hiddenimports = [
    "uvicorn.logging",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.wsproto_impl",
    "websockets",
    "pnlclaw_types",
    "pnlclaw_core",
    "pnlclaw_exchange",
    "pnlclaw_market",
    "pnlclaw_security",
    "pnlclaw_strategy",
    "pnlclaw_backtest",
    "pnlclaw_paper",
    "pnlclaw_risk",
    "pnlclaw_agent",
    "pnlclaw_llm",
    "pnlclaw_storage",
    "pnlclaw_compat",
    "dotenv",
    "yaml",
    "orjson",
    "httpx",
    "anyio",
    "sniffio",
    "h11",
    "httpcore",
    "certifi",
    "idna",
    "starlette",
    "pydantic",
    "pydantic_core",
    "annotated_types",
]

hiddenimports += collect_submodules("pnlclaw_types")
hiddenimports += collect_submodules("pnlclaw_core")
hiddenimports += collect_submodules("pnlclaw_exchange")
hiddenimports += collect_submodules("pnlclaw_market")
hiddenimports += collect_submodules("pnlclaw_security")
hiddenimports += collect_submodules("pnlclaw_strategy")
hiddenimports += collect_submodules("pnlclaw_backtest")
hiddenimports += collect_submodules("pnlclaw_paper")
hiddenimports += collect_submodules("pnlclaw_risk")
hiddenimports += collect_submodules("pnlclaw_agent")
hiddenimports += collect_submodules("pnlclaw_llm")
hiddenimports += collect_submodules("pnlclaw_storage")
hiddenimports += collect_submodules("pnlclaw_compat")
hiddenimports += collect_submodules("app")

# ---------------------------------------------------------------------------
# collect_all for binary-heavy packages
# ---------------------------------------------------------------------------
binaries = []
tmp_ret = collect_all("pydantic_core")
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

tmp_ret = collect_all("orjson")
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

tmp_ret = collect_all("cryptography")
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

from PyInstaller.utils.hooks import collect_data_files
datas += collect_data_files("tiktoken")
datas += collect_data_files("tiktoken_ext")
hiddenimports += collect_submodules("tiktoken")
hiddenimports += collect_submodules("tiktoken_ext")

hiddenimports += ["numpy", "numpy.core", "numpy.fft", "numpy.linalg", "numpy.random"]
hiddenimports += ["pandas", "pandas.core", "pandas.io", "pandas.tseries"]

# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
a = Analysis(
    [str(ROOT / "scripts" / "pyinstaller" / "pnlclaw_server_entry.py")],
    pathex=[str(SVC)],
    binaries=binaries,
    datas=datas,
    hiddenimports=list(set(hiddenimports)),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter", "unittest", "test", "tests",
        "pnlclaw_pro_auth", "pnlclaw_pro_storage",
        "matplotlib", "scipy", "sklearn", "torch", "tensorflow",
        "onnxruntime", "cupy", "pygame", "IPython", "notebook",
        "jupyter", "PIL", "cv2", "gevent",
        "pandas.tests", "numpy.tests", "numpy.testing",
        "psycopg2", "psycopg", "psycopg_binary", "alembic",
        "nltk", "spacy", "transformers",
        "llvmlite", "numba",
        "pyarrow",
        "Pythonwin", "win32com", "win32ui", "pythoncom",
        "lxml",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="pnlclaw-server",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="pnlclaw-server",
)
