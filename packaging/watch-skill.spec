# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
    copy_metadata,
)

block_cipher = None

ROOT_DIR = Path(SPECPATH).parent.resolve()
SRC_DIR = ROOT_DIR / "src"
ENTRY_POINT = str(SRC_DIR / "watch_skill" / "surfaces" / "cli" / "main.py")

datas = [
    (str(SRC_DIR / "watch_skill" / "vision" / "prices.json"), "watch_skill/vision"),
    (str(SRC_DIR / "watch_skill" / "surfaces" / "mcp" / "static" / "workspace.html"), "watch_skill/surfaces/mcp/static"),
]

# Targeted data files
for _pkg in ("watch-skill", "fastmcp", "mcp"):
    try:
        datas += copy_metadata(_pkg)
    except Exception:
        pass

datas += collect_data_files("rapidocr")
datas += collect_data_files("fastembed")
datas += collect_data_files("onnxruntime")
datas += collect_data_files("fastmcp")
datas += collect_data_files("jsonschema")
datas += collect_data_files("jsonschema_specifications")

# Targeted dynamic libraries
binaries = []
binaries += collect_dynamic_libs("onnxruntime")

# Targeted hidden imports (explicitly excluding tensorrt and unused frameworks)
hiddenimports = [
    "watch_skill",
    "watch_skill.surfaces.cli.envelope",
    "watch_skill.surfaces.cli.main",
    "watch_skill.config",
    "watch_skill.errors",
    "watch_skill.policy",
    "watch_skill.report",
    "watch_skill.sqlite_util",
    "watch_skill.update",
    "watch_skill.update_check",
    "watch_skill.update_engine",
    "watch_skill.watch",
    "watch_skill.perceive",
    "watch_skill.index",
    "watch_skill.index.store",
    "watch_skill.index.embeddings",
    "watch_skill.perceive.budget",
    "watch_skill.perceive.ocr",
    "watch_skill.perceive.scenes",
    "watch_skill.transcribe",
    "watch_skill.transcribe.audio",
    "watch_skill.transcribe.ladder",
    "watch_skill.transcribe.types",
    "watch_skill.transcribe.vtt",
    "watch_skill.health.agents_setup",
    "watch_skill.health.binaries",
    "watch_skill.health.clean",
    "watch_skill.health.doctor",
    "watch_skill.health.log",
    "watch_skill.health.vision_setup",
    "watch_skill.vision",
    "watch_skill.vision.registry",
    "watch_skill.batch",
    "watch_skill.viewer",
    "watch_skill.workspace",
    "watch_skill.workspace_root",
    "certifi",
    "packaging",
    "packaging.version",
    "sqlite3",
    "PIL",
    "cv2",
    "pydantic",
    "pydantic_settings",
    "rich",
    "typer",
    "uvicorn",
    "starlette",
    "sse_starlette",
    "jsonschema",
    "websockets",
]

# Add targeted submodules (engine + MCP server + runtime deps)
for _pkg in (
    "watch_skill.acquire",
    "watch_skill.actions",
    "watch_skill.answer",
    "watch_skill.entities",
    "watch_skill.extract",
    "watch_skill.index",
    "watch_skill.jobs",
    "watch_skill.lessons",
    "watch_skill.library",
    "watch_skill.live",
    "watch_skill.loop",
    "watch_skill.models",
    "watch_skill.observer",
    "watch_skill.operate",
    "watch_skill.perceive",
    "watch_skill.surfaces.mcp",
    "watch_skill.triggers",
    "watch_skill.update_engine",
    "watch_skill.verify",
    "fastmcp",
    "mcp",
    "anyio",
):
    hiddenimports += collect_submodules(_pkg)
hiddenimports += [m for m in collect_submodules("rapidocr") if "tensorrt" not in m]
hiddenimports += collect_submodules("fastembed")
hiddenimports += collect_submodules("scenedetect")
hiddenimports += ["onnxruntime", "onnxruntime.capi._pybind_state"]

a = Analysis(
    [ENTRY_POINT],
    pathex=[str(SRC_DIR), str(ROOT_DIR)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "tensorrt", "torch", "torchvision"],
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
    name="watch-skill",
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
    icon=str(ROOT_DIR / "packaging" / "windows" / "watch-skill.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="watch-skill",
)
