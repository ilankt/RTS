"""Scouting payoff (§7.2): first sightings of enemy types toast as intel."""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest


@pytest.fixture()
def game():
    random.seed(4321)
    from core.game import Game

    game = Game(mode="human_1v1", player_count=2)
    for _ in range(30):  # let the fog visibility grid build
        game.update(delta_time_override=1 / 60)
    return game


def run_intel_check(game):
    game._intel_timer = 1.5  # force the 1s cadence to fire
    game._check_scouting_intel(0.0)


def spawn_enemy_cavalry(game, x, y):
    from entities import Unit

    template = game.game_data["units"]["cavalry"]
    unit = Unit(name="cavalry", size=template.size, hp=template.hp,
                movement_speed=template.movement_speed, attack=None,
                animations={}, x=x, y=y, radius=template.radius,
                player=game.players[1])
    game.units.append(unit)
    return unit


def test_visible_enemy_type_alerts_once(game):
    human = game.players[0]
    ui = game.ui_manager
    ui.alerts.clear()
    castle = next(b for b in game.buildings if b.player is human and b.name == "castle")

    cavalry = spawn_enemy_cavalry(game, castle.x + 60, castle.y)
    assert game.fog_of_war.is_visible(human, cavalry.x, cavalry.y)

    run_intel_check(game)
    assert any("cavalry spotted" in text.lower() for text, _ in ui.alerts)

    ui.alerts.clear()
    run_intel_check(game)  # same type again: silent
    assert not any("cavalry" in text.lower() for text, _ in ui.alerts)

    game.units.remove(cavalry)


def test_hidden_enemy_gives_no_intel(game):
    human = game.players[0]
    ui = game.ui_manager
    ui.alerts.clear()
    enemy_castle = next(b for b in game.buildings if b.player is not human and b.name == "castle")

    cavalry = spawn_enemy_cavalry(game, enemy_castle.x + 60, enemy_castle.y)
    assert not game.fog_of_war.is_visible(human, cavalry.x, cavalry.y)

    run_intel_check(game)
    assert not any("cavalry" in text.lower() for text, _ in ui.alerts)
    # The unseen enemy castle stayed secret too
    assert not any("castle located" in text.lower() for text, _ in ui.alerts)

    game.units.remove(cavalry)


def test_no_intel_with_fog_disabled(game):
    human = game.players[0]
    ui = game.ui_manager
    ui.alerts.clear()
    castle = next(b for b in game.buildings if b.player is human and b.name == "castle")
    cavalry = spawn_enemy_cavalry(game, castle.x + 60, castle.y)

    game.fog_of_war_enabled = False
    run_intel_check(game)
    game.fog_of_war_enabled = True
    assert ui.alerts == []

    game.units.remove(cavalry)
