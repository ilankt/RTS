"""§8.2.2 truncation audit: measured `fit_text` replaces blind `[:N]` caps
(event log, selection-header name, global queue label, research strip)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from ui import fonts as ui_fonts


@pytest.fixture(scope="module")
def font():
    pygame.init()
    return ui_fonts.font(19)


def test_fitting_text_is_unchanged(font):
    text = "Barracks"
    assert ui_fonts.fit_text(font, text, font.size(text)[0]) == text


def test_long_text_ellipsized_within_width(font):
    text = "Research Improved Fletching III · queue 2"
    for max_w in (60, 100, 140):
        fitted = ui_fonts.fit_text(font, text, max_w)
        assert fitted.endswith("…")
        assert font.size(fitted)[0] <= max_w
        assert text.startswith(fitted[:-1].rstrip()) or fitted == "…"


def test_result_is_a_prefix_not_a_rewrite(font):
    text = "Watchtower Construction"
    fitted = ui_fonts.fit_text(font, text, 90)
    assert text.startswith(fitted[:-1].rstrip())


def test_absurdly_narrow_width_degrades_to_ellipsis(font):
    assert ui_fonts.fit_text(font, "Castle", 1) == "…"
