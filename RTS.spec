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
