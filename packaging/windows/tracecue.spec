# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


ROOT = Path(SPECPATH).resolve().parents[1]
hiddenimports = (
    collect_submodules("tracecue_desktop")
    + collect_submodules("tracecue_engine")
    + collect_submodules("tracecue_hikvision")
)

analysis = Analysis(
    [str(ROOT / "desktop" / "backend" / "src" / "tracecue_desktop" / "main.py")],
    pathex=[
        str(ROOT / "desktop" / "backend" / "src"),
        str(ROOT / "engine" / "src"),
        str(ROOT / "integrations" / "hikvision" / "src"),
    ],
    binaries=[
        (str(ROOT / "packaging" / "windows" / "tools" / "ffmpeg.exe"), "tools"),
        (str(ROOT / "packaging" / "windows" / "tools" / "ffprobe.exe"), "tools"),
    ],
    datas=[
        (str(ROOT / "desktop" / "frontend" / "dist"), "frontend"),
        (str(ROOT / "release" / "THIRD_PARTY_NOTICES.txt"), "."),
        (str(ROOT / "packaging" / "windows" / "tools" / "COPYING.GPLv3"), "licenses"),
        (str(ROOT / "packaging" / "windows" / "tools" / "COPYING.LGPLv3"), "licenses"),
    ],
    hiddenimports=hiddenimports,
    noarchive=False,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="TraceCue",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=None,
)
collection = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="TraceCue",
)
