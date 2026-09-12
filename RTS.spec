# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build spec for the RTS game (one-folder, windowed).

Build:   python -m PyInstaller --noconfirm RTS.spec
Output:  dist/RTS/RTS.exe  (+ its _internal/ payload folder)

Usually invoked indirectly by build_installer.bat, which also runs Inno Setup
to wrap dist/RTS/ into an installer. The one-folder layout is deliberate:
faster startup than one-file (no per-launch self-extract) and it drops
straight into the Inno [Files] section.
"""
import os
import runpy

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable,
    VarFileInfo, VarStruct, VSVersionInfo,
)

game_version = runpy.run_path(os.path.join(SPECPATH, "core", "version.py"))["GAME_VERSION"]
numeric_version = tuple(int(part) for part in game_version.split("-")[0].split(".")) + (0,)
version_info = VSVersionInfo(
    ffi=FixedFileInfo(
        filevers=numeric_version, prodvers=numeric_version,
        mask=0x3f, flags=0x2 if "-" in game_version else 0,
        OS=0x40004, fileType=0x1, subtype=0, date=(0, 0),
    ),
    kids=[
        StringFileInfo([StringTable("040904B0", [
            StringStruct("CompanyName", "Ilan Kachler"),
            StringStruct("FileDescription", "RTS Game"),
            StringStruct("FileVersion", game_version),
            StringStruct("InternalName", "RTS"),
            StringStruct("OriginalFilename", "RTS.exe"),
            StringStruct("ProductName", "RTS"),
            StringStruct("ProductVersion", game_version),
        ])]),
        VarFileInfo([VarStruct("Translation", [1033, 1200])]),
    ],
)

# App icon is optional. Drop a .ico at installer/app.ico to brand the exe.
_icon = os.path.join("installer", "app.ico")
icon = _icon if os.path.exists(_icon) else None

_SKIP_DIRS = {"_gen", ".pytest_cache", "__pycache__"}


def _asset_datas():
    """Bundle assets/ file-by-file, skipping local-only sprite-pipeline
    scratch (_gen/) and stray caches — a plain ("assets", "assets") tuple
    ships whatever happens to be on disk, not just the game's art."""
    out = []
    for root, dirs, files in os.walk("assets"):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        out.extend((os.path.join(root, f), root) for f in files)
    return out


a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=_asset_datas() + [
        ("data", "data"),       # units.json, buildings.json, techs.json, ...
        ("help", "help"),       # the Field Manual the Help button opens
        ("CREDITS.md", "."),
        ("CHANGELOG.md", "."),
        ("DOWNLOAD.md", "."),
    ],
    hiddenimports=["perlin_noise"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter"],       # unused; trims a few MB. numpy/PIL left in
    noarchive=False,            # (pygame may pull numpy lazily) to stay safe.
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="RTS",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                  # off: UPX-packed exes often trip antivirus,
    console=False,              # bad for handing beta builds to testers.
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon,
    version=version_info,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="RTS",
)
