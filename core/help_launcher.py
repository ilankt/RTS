"""Open the Help page (§ Help) in the player's default browser.

The page is a committed, self-contained HTML file (help/index.html) built by
tools/generate_help.py. If it's somehow missing (fresh checkout that never ran
the generator), we try to build it on the fly. Any failure is swallowed — the
Help button must never crash the game.
"""
import os
import pathlib
import webbrowser

from utils.debug_logger import debug_log

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HELP_PATH = os.path.join(_ROOT, "help", "index.html")


def _candidates():
    """Where the manual might live. Frozen, PyInstaller bundles `help/` next
    to the code and main.py chdirs into the bundle, so both the __file__- and
    cwd-relative paths resolve — layouts differ between PyInstaller versions,
    so try both rather than betting on one."""
    yield HELP_PATH
    yield os.path.abspath(os.path.join("help", "index.html"))


def _existing():
    return next((p for p in _candidates() if os.path.exists(p)), None)


def open_help() -> bool:
    """Open the Help page in the default browser. Returns False on failure."""
    try:
        path = _existing()
        if path is None:
            _try_generate()          # from source only; a shipped build has it
            path = _existing()
        if path is None:
            debug_log.log("Help page not found and could not be generated", "GENERAL")
            return False
        webbrowser.open(pathlib.Path(path).as_uri())
        return True
    except Exception as e:  # never let the Help button take the game down
        debug_log.log(f"Failed to open Help page: {e}", "GENERAL")
        return False


def _try_generate():
    try:
        from tools.generate_help import build
        build(HELP_PATH)
    except Exception as e:
        debug_log.log(f"Help page generation failed: {e}", "GENERAL")
