"""Box selection over a fight (bugfix 2026-07-20): enemies inside the drag
rect must not block selecting your own units."""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

from entities.unit import Unit


@pytest.fixture(scope="module")
def game():
    random.seed(1234)
    from core.game import Game

    g = Game(mode="human_1v1", player_count=2)
    g.ai_system.update = lambda dt: None
    return g


def make_warrior(game, player, x, y):
    unit = Unit(name="warrior", size=[1, 1], hp=250, movement_speed=50, attack=10,
                animations={}, x=x, y=y, radius=16, player=player,
                min_damage=18, max_damage=22, attack_speed=1.2, attack_range=48,
                can_attack=True)
    game.units.append(unit)
    return unit


def test_filter_ignores_enemies_when_own_units_present(game):
    sm = game.selection_manager
    human, enemy = game.players[0], game.players[1]
    h1 = make_warrior(game, human, 1200, 1200)
    e1 = make_warrior(game, enemy, 1220, 1210)
    h2 = make_warrior(game, human, 1240, 1220)

    result = sm._filter_selectable_objects([h1, e1, h2], allow_multi_select=True)
    assert result == [h1, h2]


def test_filter_enemy_only_box_falls_back_to_single(game):
    sm = game.selection_manager
    enemy = game.players[1]
    e1 = make_warrior(game, enemy, 1300, 1300)
    e2 = make_warrior(game, enemy, 1320, 1310)

    result = sm._filter_selectable_objects([e1, e2], allow_multi_select=True)
    assert result == [e1]


def test_drag_selection_over_fight_selects_own_units(game):
    sm = game.selection_manager
    human, enemy = game.players[0], game.players[1]
    # Interleave one enemy between two friendly units, in open ground far
    # from both bases so nothing else falls inside the rect.
    h1 = make_warrior(game, human, 2200, 2000)
    e1 = make_warrior(game, enemy, 2220, 2010)
    h2 = make_warrior(game, human, 2240, 2020)

    old_fog = getattr(game, "fog_of_war_enabled", True)
    game.fog_of_war_enabled = False
    try:
        cam = game.camera

        def to_screen(obj):
            return (obj.x * cam.zoom + cam.x, obj.y * cam.zoom + cam.y)

        xs, ys = zip(*(to_screen(obj) for obj in (h1, e1, h2)))
        pad = 5 * cam.zoom
        sm._handle_drag_selection((min(xs) - pad, min(ys) - pad),
                                  (max(xs) + pad, max(ys) + pad))
    finally:
        game.fog_of_war_enabled = old_fog

    assert h1 in sm.selected_objects and h2 in sm.selected_objects
    assert e1 not in sm.selected_objects
    assert h1.selected and h2.selected
    assert not e1.selected
