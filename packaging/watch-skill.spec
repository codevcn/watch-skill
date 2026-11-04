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
try:
    datas += copy_metadata("watch-skill")
except Exception:
    pass

datas += collect_data_files("rapidocr")
datas += collect_data_files("fastembed")
datas += collect_data_files("onnxruntime")

# Targeted dynamic libraries
binaries = []
binaries += collect_dynamic_libs("onnxruntime")

# Targeted hidden imports (explicitly excluding tensorrt and unused frameworks)
hiddenimports = [
    "watch_skill",
    "watch_skill.surfaces.cli.envelope",
    "watch_skill.surfaces.cli.main",
    "watch_skill.config",
    "watch_skill.watch",
    "watch_skill.perceive",
    "watch_skill.index",
    "watch_skill.index.store",
    "watch_skill.index.embeddings",
    "watch_skill.perceive.budget",
    "watch_skill.perceive.ocr",
    "watch_skill.perceive.scenes",
    "watch_skill.perceive.transcribe",
    "watch_skill.health.binaries",
    "watch_skill.health.vision_setup",
    "watch_skill.vision",
    "watch_skill.vision.registry",
    "sqlite3",
    "PIL",
    "cv2",
    "pydantic",
    "pydantic_settings",
    "rich",
    "typer",
]

# Add targeted submodules
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="watch-skill-windows-x86_64",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
