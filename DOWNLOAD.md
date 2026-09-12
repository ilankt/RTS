# Download

Latest version: **0.13.0-beta** — Windows 64-bit.
[What's new in this version](CHANGELOG.md#0130-beta--2026-09-12)

| Download | What you get |
|---|---|
| **[Installer](https://github.com/ilankt/RTS/releases/download/v0.13.0-beta/RTS_Setup_0.13.0-beta.exe)** — `RTS_Setup_0.13.0-beta.exe` | Familiar setup wizard. Installs per-user (no admin prompt), adds a Start-menu shortcut and an uninstaller. |
| **[Portable](https://github.com/ilankt/RTS/releases/download/v0.13.0-beta/RTS_0.13.0-beta_win64_portable.zip)** — `RTS_0.13.0-beta_win64_portable.zip` | No installation: unzip anywhere and run `RTS.exe`. |
| **[SHA-256 checksums](https://github.com/ilankt/RTS/releases/download/v0.13.0-beta/SHA256SUMS.txt)** | Verify the installer and portable download. |
| **[Source code](https://github.com/ilankt/RTS/archive/refs/heads/main.zip)** — `src.zip` | The latest source. Runs on any OS with Python 3.10+ — see [Getting Started](README.md#getting-started). |

All releases: <https://github.com/ilankt/RTS/releases> ·
Full version history: **[CHANGELOG.md](CHANGELOG.md)**

Upgrading from 0.12.0-beta or earlier? The installer replaces the old version in place, and
your saves and settings are kept (they live outside the install folder).
Older saves are migrated when loaded. Ballista health is adjusted proportionally
to the new balance values.

Good to know:

- The game keeps its saves, settings, and log in `%LOCALAPPDATA%\RTS`, never in
  its install folder. Uninstalling removes the game, not your saves.
- The executable is not code-signed, so Windows SmartScreen or your antivirus
  may warn on first run. If you'd rather not trust a prebuilt binary, run from
  source instead — it's the same code you can read in this repo.

## Disclaimer

This is a hobby project, provided **“as is”**, without warranty of any kind,
express or implied — including, without limitation, any warranties of
merchantability, fitness for a particular purpose, or noninfringement. The
entire risk arising out of downloading, installing, or using this software
(including the prebuilt binaries) remains with you. In no event shall the
author be liable for any claim, damages, or other liability — whether in an
action of contract, tort, or otherwise — arising from, out of, or in
connection with the software or its use. **Download and run at your own risk.**
