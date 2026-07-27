"""Single source of truth for the game version.

Shown on the main menu (screens/main_menu.py) and used for the Windows
installer: build_installer.bat reads it via
``python -c "import core.version; print(core.version.GAME_VERSION)"`` and hands
it to Inno Setup as ``/DMyAppVersion``. Update the number here only.

Kept import-free on purpose so it's cheap to read from the build script.
"""
GAME_VERSION = "0.12.0-beta"
