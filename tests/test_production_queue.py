"""Production queue economics (§7.4): pay on queue, cap, cancel refunds."""
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

    return Game(mode="human_1v1", player_count=2)


def setup_castle(game, stock=100000):
    human = game.players[0]
    for resource in human.resources:
        human.resources[resource] = stock
    castle = next(b for b in game.buildings if b.player is human and b.name == "castle")
    return human, castle


def worker_costs(game):
    return game.production_manager.units_data["worker"].get("costs", {})


def total(resources):
    return sum(resources.values())


def test_queueing_charges_up_front(game):
    pm = game.production_manager
    human, castle = setup_castle(game)
    cost = total(worker_costs(game))
    assert cost > 0

    before = total(human.resources)
    ok, _ = pm.start_production(castle, "worker")   # starts
    assert ok
    ok, _ = pm.start_production(castle, "worker")   # queues
    assert ok and castle.production_queue == ["worker"]
    assert total(human.resources) == before - 2 * cost


def test_queue_cap(game):
    pm = game.production_manager
    human, castle = setup_castle(game)

    pm.start_production(castle, "worker")
    for _ in range(pm.MAX_QUEUE):
        assert pm.start_production(castle, "worker")[0]
    ok, message = pm.start_production(castle, "worker")
    assert not ok and "full" in message.lower()
    assert len(castle.production_queue) == pm.MAX_QUEUE


def test_queue_pop_does_not_charge_again(game):
    pm = game.production_manager
    human, castle = setup_castle(game)

    pm.start_production(castle, "worker")
    pm.start_production(castle, "worker")
    after_paying = total(human.resources)

    # Finish the current unit; the queued one must start for free
    castle.current_production["progress"] = castle.current_production["total_time"] + 1
    pm.update(0.001)
    assert castle.current_production is not None
    assert castle.production_queue == []
    assert total(human.resources) == after_paying


def test_cancel_queued_refunds_full_cost(game):
    pm = game.production_manager
    human, castle = setup_castle(game)
    cost = total(worker_costs(game))

    pm.start_production(castle, "worker")
    pm.start_production(castle, "worker")
    before = total(human.resources)

    ok, _ = pm.cancel_queued(castle, "worker")
    assert ok and castle.production_queue == []
    assert total(human.resources) == before + cost

    # Nothing left to cancel
    assert not pm.cancel_queued(castle, "worker")[0]
