"""Telegraph attacks (§7.2): pushes at the human cue only when scouted."""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest


@pytest.fixture(scope="module")
def game():
    random.seed(4321)
    from core.game import Game

    return Game(mode="human_1v1", player_count=2)


def make_ctx(game, ai_player):
    from systems.ai.utility.context import GoalContext

    return GoalContext.build(game, ai_player)


def test_telegraph_fires_when_squad_is_visible(game):
    brain = game.ai_system.military_brain
    human, ai = game.players[0], game.players[1]
    ui = game.ui_manager
    ui.alerts.clear()
    ui._alert_last.clear()

    castle = next(b for b in game.buildings if b.player is human and b.name == "castle")
    # Squad member standing right at the human castle: certainly visible
    squad_unit = next(u for u in game.units if u.player is ai)
    squad_unit.x, squad_unit.y = castle.x + 50, castle.y
    for _ in range(30):  # let the fog visibility grid refresh
        game.update(delta_time_override=1 / 60)
    assert game.fog_of_war.is_visible(human, squad_unit.x, squad_unit.y)

    brain._telegraph_attack(make_ctx(game, ai), castle, [squad_unit])
    assert any("attack incoming" in text.lower() for text, _ in ui.alerts)


def test_no_telegraph_from_the_fog(game):
    brain = game.ai_system.military_brain
    human, ai = game.players[0], game.players[1]
    ui = game.ui_manager
    ui.alerts.clear()
    ui._alert_last.clear()

    castle = next(b for b in game.buildings if b.player is human and b.name == "castle")
    ai_castle = next(b for b in game.buildings if b.player is ai and b.name == "castle")
    # Squad still deep in the AI's own base: not visible to the human
    squad_unit = next(u for u in game.units if u.player is ai)
    squad_unit.x, squad_unit.y = ai_castle.x + 50, ai_castle.y
    assert not game.fog_of_war.is_visible(human, squad_unit.x, squad_unit.y)

    brain._telegraph_attack(make_ctx(game, ai), castle, [squad_unit])
    assert ui.alerts == []


def test_no_telegraph_for_ai_vs_ai(game):
    brain = game.ai_system.military_brain
    ai = game.players[1]
    ui = game.ui_manager
    ui.alerts.clear()
    ui._alert_last.clear()

    ai_castle = next(b for b in game.buildings if b.player is ai and b.name == "castle")
    squad_unit = next(u for u in game.units if u.player is ai)
    brain._telegraph_attack(make_ctx(game, ai), ai_castle, [squad_unit])
    assert ui.alerts == []
