"""Power spikes (§7.2): research completion floats over affected units."""
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


def test_affected_unit_names_covers_effect_shapes(game):
    rm = game.research_manager
    forged = next(t for t in game.game_data["techs"].values() if t["id"] == "forged_blades")
    assert rm.affected_unit_names(forged) == {"warrior", "spearman", "cavalry"}

    tools = next(t for t in game.game_data["techs"].values() if t["id"] == "improved_tools")
    assert "worker" in rm.affected_unit_names(tools)


def test_completion_floats_over_affected_units(game):
    rm = game.research_manager
    human = game.players[0]
    before = len(game.floating_ui.notifications)

    forged = next(t for t in game.game_data["techs"].values() if t["id"] == "forged_blades")
    rm._show_power_spike(human, forged)
    # Fresh match: human has workers but no melee military yet -> no floats
    assert len(game.floating_ui.notifications) == before

    tools = next(t for t in game.game_data["techs"].values() if t["id"] == "improved_tools")
    rm._show_power_spike(human, tools)
    workers = sum(1 for u in game.units if u.player is human and u.name == "worker")
    floats = len(game.floating_ui.notifications) - before
    assert floats == min(workers, rm.POWER_SPIKE_FLOAT_CAP)
    assert floats > 0
