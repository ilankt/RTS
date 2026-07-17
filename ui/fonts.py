"""Shared UI fonts (§8.2.2).

One place to resolve a font, so the HUD reads consistently and the typeface or
scale can change in one spot. Uses a clean system sans (Segoe UI / Arial /
DejaVu / Verdana) instead of pygame's chunky, uneven built-in default; falls
back to the default only if none of those are installed, so it stays portable.

Call `font(px)` with a pixel size. `title`/`body`/etc. are the semantic sizes
the sidebar uses — bump them here, not at 44 scattered call sites.
"""
import pygame

_UNSET = "__unset__"
_face_path = _UNSET


def _face():
    """Path to the preferred UI face, or None to use pygame's default."""
    global _face_path
    if _face_path is _UNSET:
        try:
            _face_path = pygame.font.match_font("segoeui,arial,dejavusans,verdana,tahoma")
        except Exception:
            _face_path = None
    return _face_path


def font(size, bold=False):
    """A font at `size` px — the clean face, default as fallback.

    Deliberately NOT cached at module level: a pygame.font.quit()/init cycle
    (which some tests and the main menu trigger) would leave a module-cached
    Font holding a dead TTF handle and segfault on the next render. Callers
    build their fonts once in __init__ (tied to the Game/UI lifecycle), so
    the per-frame cost is nil and each Game gets fonts from the live subsystem.
    """
    if not pygame.font.get_init():
        pygame.font.init()
    path = _face()
    f = pygame.font.Font(path, int(size)) if path else pygame.font.Font(None, int(size))
    f.set_bold(bool(bold))
    return f


# Semantic sizes for the command card + unit panel. Tuned for the real system
# face (a touch larger than the old default-font literals, which rendered
# smaller and rougher than their nominal size).
def title(bold=True):      return font(26, bold)   # selection header name
def body():                return font(19)         # tooltip / stat lines
def label():               return font(18, True)   # chip + tile labels
def cost():                return font(19, True)   # tile cost numbers
def badge():               return font(15, True)   # hotkey / queue badges
def bar_text():            return font(16, True)   # value inside a bar
