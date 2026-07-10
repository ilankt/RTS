"""Income-rate HUD backend (§8.3): rolling per-second income for the human."""
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


def test_income_rate_rolls_over_window(game):
    human = game.players[0]
    game.income_events.clear()
    game.sim_time_elapsed = 100.0

    # 30 wood over the last few seconds -> 30 / window
    game.record_income(human, "wood", 10)
    game.sim_time_elapsed = 105.0
    game.record_income(human, "wood", 20)
    assert game.income_rate("wood") == pytest.approx(30 / game.INCOME_WINDOW_SECS)

    # Events age out of the window
    game.sim_time_elapsed = 100.0 + game.INCOME_WINDOW_SECS + 6.0
    assert game.income_rate("wood") == 0.0
    assert game.income_events["wood"] == []  # pruned


def test_ai_income_not_tracked(game):
    ai = game.players[1]
    game.income_events.clear()
    game.record_income(ai, "gold", 50)
    assert game.income_rate("gold") == 0.0


def test_real_gathering_feeds_the_tracker(game):
    """A worker drop-off ends up in income_events via the gathering manager."""
    human = game.players[0]
    game.income_events.clear()
    worker = next(u for u in game.units if u.player is human and u.name == "worker")
    castle = next(b for b in game.buildings if b.player is human and b.name == "castle")

    worker.resource_amount = 10
    worker.resource_type = "wood"
    worker.is_dropping_off = True
    worker.drop_off_target = castle
    worker.drop_off_timer = 10.0  # past DROP_OFF_DELAY
    worker.x, worker.y = castle.x, castle.y

    game.gathering_manager.drop_off_resources(worker, castle, 0.5)
    assert game.income_rate("wood") > 0
