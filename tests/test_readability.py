"""§7.4 readability pass: heal floats, owner-colored HP-bar borders,
hover highlight under the cursor."""
import os
import random
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest


@pytest.fixture(scope="module")
def game():
    random.seed(7411)
    from core.game import Game

    return Game(mode="human_1v1", player_count=2)


FLAT_CAMERA = SimpleNamespace(zoom=1.0, x=0, y=0)


def test_healer_spawns_green_heal_float(game):
    from entities.unit import Unit
    from core.config import HEALER_HEAL_AMOUNT

    human = game.players[0]
    healer = Unit(name="healer", size=[1, 1], hp=60, movement_speed=80, attack=0,
                  animations={}, x=3000, y=3000, radius=8, player=human)
    wounded = Unit(name="warrior", size=[1, 1], hp=40, movement_speed=80, attack=0,
                   animations={}, x=3040, y=3000, radius=8, player=human)
    game.units.extend([healer, wounded])
    try:
        before = len(game.floating_ui.notifications)
        game.combat_system._update_healer(healer, 1 / 60)
        floats = game.floating_ui.notifications[before:]
        assert any(n.text == f"+{HEALER_HEAL_AMOUNT}" and n.color == (90, 230, 110)
                   for n in floats), "heal should spawn a green +N float"
    finally:
        game.units.remove(healer)
        game.units.remove(wounded)


def test_hp_bar_border_carries_owner_color(game):
    human = game.players[0]
    obj = SimpleNamespace(name="worker", x=200, y=200, hp=50,
                          movement_speed=80, player=human)
    surface = pygame.Surface((400, 400))
    game.floating_ui.draw_health_bar(surface, obj, FLAT_CAMERA)

    # Bar geometry at zoom 1: 32x4, centered, 40px above the object.
    bar_x, bar_y = 200 - 16, 200 - 40
    assert surface.get_at((bar_x, bar_y))[:3] == tuple(human.color), \
        "HP bar border should be the owner's player color"


def test_hp_bar_border_black_for_unowned(game):
    obj = SimpleNamespace(name="worker", x=200, y=200, hp=50,
                          movement_speed=80, player=None)
    surface = pygame.Surface((400, 400), pygame.SRCALPHA)
    game.floating_ui.draw_health_bar(surface, obj, FLAT_CAMERA)
    assert surface.get_at((200 - 16, 200 - 40))[:3] == (0, 0, 0)


def test_hover_marker_draws_and_clears_on_death(game):
    sm = game.selection_manager
    fog_was = game.fog_of_war_enabled
    game.fog_of_war_enabled = False
    try:
        obj = SimpleNamespace(x=100, y=100, radius=10, hp=100,
                              in_world=True, selected=False, player=None)
        sm.hovered_object = obj
        surface = pygame.Surface((300, 300))
        sm._draw_hover_marker(surface, FLAT_CAMERA)
        # Ellipse outline: rect (89, 101, 22, 8) -> top-center pixel is lit.
        assert surface.get_at((100, 101))[:3] == (170, 170, 170), \
            "hovered neutral object should get a gray ground ellipse"

        # Dead objects drop the hover marker instead of ghost-highlighting.
        obj.hp = 0
        sm._draw_hover_marker(surface, FLAT_CAMERA)
        assert sm.hovered_object is None
    finally:
        game.fog_of_war_enabled = fog_was
        sm.hovered_object = None


def test_hover_marker_skips_selected_objects(game):
    sm = game.selection_manager
    fog_was = game.fog_of_war_enabled
    game.fog_of_war_enabled = False
    try:
        obj = SimpleNamespace(x=100, y=100, radius=10, hp=100,
                              in_world=True, selected=True, player=None)
        sm.hovered_object = obj
        surface = pygame.Surface((300, 300))
        sm._draw_hover_marker(surface, FLAT_CAMERA)
        assert surface.get_at((100, 101))[:3] == (0, 0, 0), \
            "selected objects already show the selection ellipse - no hover ring"
    finally:
        game.fog_of_war_enabled = fog_was
        sm.hovered_object = None


def test_cursor_context_clears_hover_over_ui(game):
    sm = game.selection_manager
    sm.hovered_object = SimpleNamespace()
    game._update_cursor_for_context((5, 5))  # inside the top bar
    assert sm.hovered_object is None
