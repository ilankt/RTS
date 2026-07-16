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

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("assets", "assets"),   # sprites, ui art, background music (.ogg)
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
