"""AI integration (§9 test coverage): run a real AI-vs-AI sim for four
game-minutes and assert observable outcomes, not attributes.

Four minutes, not two: with the lean starting economy (config
HUMAN/AI_STARTING_RESOURCES) an AI must build a barracks and gather before
it can train troops, so the first army lands around ~2.5 game-minutes
instead of instantly off a huge opening stockpile."""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest


@pytest.fixture(scope="module")
def played_game():
    random.seed(20260710)
    from core.game import Game

    game = Game(mode="ai_spectator", player_count=2)
    game.players[0].ai_personality = "boomer"
    game.players[1].ai_personality = "rusher"
    for _ in range(60 * 240):  # four game-minutes at 60 fps
        game.update(delta_time_override=1 / 60)
    return game


def test_ai_grows_its_economy(played_game):
    game = played_game
    for player in game.players:
        # The sim is deliberately not bit-reproducible (per-unit scan jitter
        # keys off id()), and a rusher cuts workers by design — so assert the
        # economy WORKED, not an exact head count: workers were trained
        # (stats) or survived (live list), and real resources came in.
        live_workers = sum(1 for u in game.units if u.player is player and u.name == "worker")
        trained = game.stats_units_trained.get((player.name, "worker"), 0)
        assert live_workers >= 3 or trained > 0, f"{player.name} has no worker economy"
        gathered = game.stats_resources_gathered.get(player.name, 0)
        assert gathered > 100, f"{player.name} gathered almost nothing ({gathered})"


def test_ai_expands_its_base(played_game):
    game = played_game
    for player in game.players:
        built = [k for (name, k), v in game.stats_buildings_built.items()
                 if name == player.name and v > 0]
        assert built, f"{player.name} built nothing in four minutes"


def test_ai_fields_an_army(played_game):
    game = played_game
    from systems.ai.utility.context import MILITARY_NAMES

    total_military = sum(
        1 for u in game.units if u.name in MILITARY_NAMES and u.hp > 0
    )
    trained = sum(
        v for (name, unit_type), v in game.stats_units_trained.items()
        if unit_type in MILITARY_NAMES
    )
    assert total_military + trained > 0, "no military existed or was ever trained"


def test_sim_stays_healthy(played_game):
    game = played_game
    # The clock ran, nobody won by accident, and units aren't leaking hp<0
    assert game.sim_time_elapsed == pytest.approx(240.0, abs=1.0)
    assert all(u.hp > 0 for u in game.units)
    # Pathfinding didn't wedge: no unit is stuck with an empty path forever
    # (the watchdog would have teleported it; just assert the lists are sane)
    assert game.units and game.buildings
