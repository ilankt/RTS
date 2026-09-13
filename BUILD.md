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
  `assets/`, `data/`, the field manual, credits and release notes into the build.
  Windows file properties use the version from `core/version.py`.
- `installer.iss` — Inno Setup script. Wraps `dist\RTS\` into a per-user
  installer (no UAC prompt; installs to `%LOCALAPPDATA%\Programs\RTS`).
- `core/app_paths.py` — when frozen, the game reads bundled assets from the
  unpacked bundle and writes **saves, settings, keybindings, profile, and the
  debug log to `%LOCALAPPDATA%\RTS`** so an installed copy never writes into its
  own (possibly read-only) folder. Running from source is unchanged.

## Adjusting

### Updating the field manual and player wiki

The explanations live in `help/topics.json`. Unit and building costs, stats,
artwork, technologies, configuration values and default hotkeys are read from
the game itself. After changing these or the version, regenerate both outputs:

```bash
pip install Pillow
python tools/generate_help.py
```

Commit `help/index.html` and `docs/wiki/` with their sources. The generated HTML
works offline and is included in Windows builds. Native GitHub wiki publication
uses the same Markdown pages, with `.md` removed from local page links. After
cloning `https://github.com/ilankt/RTS.wiki.git`, prepare that checkout with
`python tools/generate_help.py --wiki-dir <path-to-wiki-checkout>`, review its
diff, then commit and push from the wiki checkout.
The installer builder regenerates the manual before packaging.

### Packaging options

For an isolated build, pass `--distpath <folder>` and `--workpath <folder>` to
PyInstaller. Pass `/DMyBuildDir=<absolute-path-to-RTS-folder>` to Inno Setup to
package that folder instead of `dist\RTS`.

- **Version**: update `GAME_VERSION` in `core/version.py`. The menu, executable
  metadata and installer use it. Update `README.md`, `DOWNLOAD.md`,
  `CHANGELOG.md` and the field manual for the public release.
- **Publisher**: edit `MyAppPublisher` in `installer.iss` and `CompanyName` in
  `RTS.spec`. Keep `AppId` stable so upgrades replace instead of duplicate.
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
