"""Multi-select panel (§8.2): mixed selections group by type with counts."""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest


@pytest.fixture(scope="module")
def game():
    random.seed(4321)
    from core.game import Game

    return Game(mode="human_1v1", player_count=2)


def test_selection_groups_by_type_largest_first(game):
    panel = game.ui_manager.unit_panel
    all_units = list(game.units)
    assert all_units

    selection = all_units + ["not-a-unit", game.buildings[0]]
    groups = panel.group_selected_units(selection)

    sizes = [len(units) for _name, units in groups]
    assert sizes == sorted(sizes, reverse=True)       # biggest group first
    assert sum(sizes) == len(all_units)               # non-units dropped
    for name, units in groups:
        assert all(u.name == name for u in units)     # grouped by type


def test_draw_multi_selection_smoke(game):
    panel = game.ui_manager.unit_panel
    human = game.players[0]
    units = [u for u in game.units if u.player is human]
    surface = pygame.Surface((220, 500))
    panel._draw_multi_selection(surface, units)  # must not raise
