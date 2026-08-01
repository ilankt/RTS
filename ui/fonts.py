"""Shared UI fonts (§8.2.2).

One place to resolve a font, so the HUD reads consistently and the typeface or
scale can change in one spot. Uses a clean system sans (Segoe UI / Arial /
DejaVu / Verdana) instead of pygame's chunky, uneven built-in default; falls
back to the default only if none of those are installed, so it stays portable.

Call `font(px)` with a pixel size. `title`/`body`/etc. are the semantic sizes
the sidebar uses — bump them here, not at 44 scattered call sites.
"""
import pygame

import core.config as config

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
    """A font at `size` DESIGN px — the clean face, default as fallback.

    `size` is multiplied by `config.UI_SCALE` (§8.2.2), which is what makes one
    edit here resize every migrated call site. config is imported as a MODULE,
    not by value, so the scale that apply_resolution() computed at startup is
    the one used here.

    Deliberately NOT cached at module level: a pygame.font.quit()/init cycle
    (which some tests and the main menu trigger) would leave a module-cached
    Font holding a dead TTF handle and segfault on the next render. Callers
    build their fonts once in __init__ (tied to the Game/UI lifecycle), so
    the per-frame cost is nil and each Game gets fonts from the live subsystem.
    """
    if not pygame.font.get_init():
        pygame.font.init()
    path = _face()
    scaled = max(1, int(round(size * config.UI_SCALE)))
    f = pygame.font.Font(path, scaled) if path else pygame.font.Font(None, scaled)
    f.set_bold(bool(bold))
    return f


def fit_text(font_obj, text, max_width):
    """Measured truncation: `text` unchanged if it fits `max_width` px, else
    the widest prefix that fits with a trailing ellipsis. §8.2.2: replaces
    the blind `[:N]` caps, which count characters and so cut too early for
    narrow glyphs and still overflow for wide ones."""
    if font_obj.size(text)[0] <= max_width:
        return text
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if font_obj.size(text[:mid].rstrip() + "…")[0] <= max_width:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo].rstrip() + "…"


# Semantic sizes for the command card + unit panel. Tuned for the real system
# face (a touch larger than the old default-font literals, which rendered
# smaller and rougher than their nominal size).
def title(bold=True):      return font(26, bold)   # selection header name
def body():                return font(19)         # tooltip / stat lines
def label():               return font(18, True)   # chip + tile labels
def cost():                return font(19, True)   # tile cost numbers
def badge():               return font(15, True)   # hotkey / queue badges
def bar_text():            return font(16, True)   # value inside a bar
