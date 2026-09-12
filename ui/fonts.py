"""Shared UI fonts (§8.2.2).

One place to resolve a font, so the HUD reads consistently and the typeface or
scale can change in one spot. Uses a clean system sans (Segoe UI / Arial /
DejaVu / Verdana) instead of pygame's chunky, uneven built-in default; falls
back to the default only if none of those are installed, so it stays portable.

Call `font(px)` with a pixel size. `title`/`body`/etc. are the semantic sizes
the sidebar uses — bump them here, not at 44 scattered call sites.
"""
import os
from pathlib import Path
import pygame

import core.config as config

_UNSET = "__unset__"
_face_path = _UNSET


def _face():
    """Path to the preferred UI face, or None to use pygame's default."""
    global _face_path
    if _face_path is _UNSET:
        try:
            # Windows registers several Segoe faces under the same family.
            # match_font can pick Light; choose Regular explicitly for the HUD.
            regular = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts/segoeui.ttf'
            _face_path = str(regular) if regular.is_file() else pygame.font.match_font(
                "arial,dejavusans,verdana,tahoma")
        except Exception:
            _face_path = None
    return _face_path


def font(size, bold=False, scaled=True):
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
    native_bold = False
    if bold and path and Path(path).name.lower() == 'segoeui.ttf':
        bold_path = Path(path).with_name('segoeuib.ttf')
        if bold_path.is_file():
            path, native_bold = str(bold_path), True
    pixels = max(1, int(round(size * (config.UI_SCALE if scaled else 1))))
    f = pygame.font.Font(path, pixels) if path else pygame.font.Font(None, pixels)
    f.set_bold(bool(bold) and not native_bold)
    return f


def fit_text(font_obj, text, max_width):
    """Measured truncation: `text` unchanged if it fits `max_width` px, else
    the widest prefix that fits with a trailing ellipsis. §8.2.2: replaces
    the blind `[:N]` caps, which count characters and so cut too early for
    narrow glyphs and still overflow for wide ones."""
    text = str(text)
    if max_width <= 0:
        return ''
    if font_obj.size(text)[0] <= max_width:
        return text
    if font_obj.size('…')[0] > max_width:
        return ''
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if font_obj.size(text[:mid].rstrip() + "…")[0] <= max_width:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo].rstrip() + "…"


def screen_font(size, bold=False):
    """Menus use screen pixels; HUD elements use resolution-scaled design pixels."""
    return font(size, bold, scaled=False)


def wrap_text(font_obj, text, max_width):
    """Measured word wrapping, splitting exceptionally long tokens as needed."""
    lines = []
    for paragraph in str(text).splitlines() or ['']:
        current = ''
        for word in paragraph.split():
            if current and font_obj.size(current + ' ' + word)[0] > max_width:
                lines.append(current)
                current = ''
            while font_obj.size(word)[0] > max_width and len(word) > 1:
                split = 1
                while split < len(word) and font_obj.size(word[:split + 1])[0] <= max_width:
                    split += 1
                lines.append(word[:split])
                word = word[split:]
            current = (current + ' ' + word).strip()
        lines.append(current)
    return lines


# Semantic sizes for the command card + unit panel. Tuned against actual font
# line boxes, including the fixed-height 720p chips, badges and health bars.
def title(bold=True):      return font(20, bold)   # selection header name
def body():                return font(16)         # tooltip / stat lines
def label():               return font(14, True)   # chip + tile labels
def cost():                return font(15, True)   # tile cost numbers
def badge():               return font(11, True)   # fits the 16px key badge vertically
def bar_text():            return font(11, True)   # fits the 15px health bar
