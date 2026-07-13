"""Filesystem locations for reads (bundled assets) and writes (user data).

Two very different concerns, kept apart so a packaged build behaves:

* **Reads** — sprites, sounds, and the JSON in ``assets/`` and ``data/`` are
  loaded through bare relative paths all over the codebase. Running from source
  that resolves against the project root. Frozen by PyInstaller, ``main.py``
  ``chdir``s into the unpacked bundle (``sys._MEIPASS``) so those same relative
  paths keep working — no call site has to change.

* **Writes** — settings, keybindings, the profile, saves, and the debug log
  must land somewhere the user can actually write. From source we keep the
  historical behaviour (relative to the working dir, i.e. the project root).
  Frozen, an installed copy may live under a read-only Program Files, so those
  files go to ``%LOCALAPPDATA%\\RTS`` instead. See MASTER_PLAN §8.10 packaging.

Only ``os``/``sys`` are imported here so this module is safe to pull into
``core.config`` and other early-import modules without any cycle.
"""
import os
import sys

APP_NAME = "RTS"


def is_frozen():
    """True when running from a PyInstaller (or similar) frozen bundle."""
    return getattr(sys, "frozen", False)


def user_data_dir():
    """Per-user writable directory for saves/settings, created on demand."""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    path = os.path.join(base, APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def user_path(*parts):
    """Resolve a path for a *writable* file (settings, saves, debug log, ...).

    From source this is just the relative path joined from ``parts`` — writes
    land in the working dir exactly as before. Frozen, it becomes an absolute
    path under :func:`user_data_dir` so nothing tries to write into the
    (possibly read-only) install directory.
    """
    if is_frozen():
        return os.path.join(user_data_dir(), *parts)
    return os.path.join(*parts)
