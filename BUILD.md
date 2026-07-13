# Building a Windows installer

Packs the game into a standalone Windows build — no Python needed on the
tester's machine.

## TL;DR

```bat
build_installer.bat
```

Double-click it (or run from a terminal). Two artifacts come out:

| Artifact | Path | What it is |
|----------|------|------------|
| Portable build | `dist\RTS\RTS.exe` | Run-in-place. Zip the whole `dist\RTS\` folder and share. |
| Installer | `installer_output\RTS_Setup_<ver>.exe` | Familiar setup wizard, Start-menu shortcut, uninstaller. |

Both are git-ignored.

## Prerequisites

1. **Python** on `PATH` with the game's deps (`pip install -r requirements.txt`).
   Use the same interpreter that runs `python main.py`. PyInstaller is installed
   automatically into it on first run.
2. **Inno Setup 6** (for the installer step only) —
   <https://jrsoftware.org/isdl.php>. Without it, the script still produces the
   portable `dist\RTS\` build and just skips the wizard.

## How it works

- `RTS.spec` — PyInstaller config. One-folder, windowed (no console), bundles
  `assets/` and `data/` into the build.
- `installer.iss` — Inno Setup script. Wraps `dist\RTS\` into a per-user
  installer (no UAC prompt; installs to `%LOCALAPPDATA%\Programs\RTS`).
- `core/app_paths.py` — when frozen, the game reads bundled assets from the
  unpacked bundle and writes **saves, settings, keybindings, profile, and the
  debug log to `%LOCALAPPDATA%\RTS`** so an installed copy never writes into its
  own (possibly read-only) folder. Running from source is unchanged.

## Adjusting

- **Version / publisher**: edit the `#define` lines at the top of
  `installer.iss` (`MyAppVersion`, `MyAppPublisher`). Keep `AppId` stable so
  upgrades replace instead of duplicate.
- **App icon**: drop a square PNG at `assets\ICON.png`. The build converts it
  to `installer\app.ico` (via `tools\make_icon.py`) and the spec picks it up
  automatically for the exe; Inno reuses the exe's icon for shortcuts. To change
  the icon, just replace the PNG and rebuild.
- **Smaller build**: `RTS.spec` already excludes `tkinter`. You can add more to
  `excludes`, but test the result — `pygame` can pull `numpy` lazily.

## If a tester's build fails to launch

Most likely a module PyInstaller didn't auto-detect. Build once with
`console=True` in `RTS.spec` to see the traceback, then add the missing module
to `hiddenimports`. Revert `console=False` before shipping.
