"""Dynamic map events (§7.5): resource booms + bumper harvests, mutator-gated."""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

from core.config import RESOURCE_LIMITS


@pytest.fixture(scope="module")
def game():
    random.seed(4321)
    from core.game import Game

    return Game(mode="human_1v1", player_count=2)


def test_events_only_fire_under_the_mutator(game):
    events = game.dynamic_events
    game.mutators = set()
    before = len(game.resources)
    events._timer = 0.1
    for _ in range(5):
        events.update(100.0)
    assert len(game.resources) == before  # nothing without the mutator


def test_resource_boom_spawns_rich_cluster_away_from_castles(game):
    import math

    events = game.dynamic_events
    game.ui_manager.alerts.clear()
    before = len(game.resources)

    random.seed(99)
    events.trigger("boom_gold")
    new_nodes = game.resources[before:]
    assert len(new_nodes) == events.BOOM_CLUSTER
    for node in new_nodes:
        assert node.name == "gold"
        assert node.amount_remaining == int(RESOURCE_LIMITS.get("gold", 100) * events.BOOM_RICHNESS)
        for castle in (b for b in game.buildings if b.name == "castle"):
            assert math.hypot(node.x - castle.x, node.y - castle.y) >= events.MIN_CASTLE_DISTANCE - 60
    assert any("deposit" in text for text, _ in game.ui_manager.alerts)

    # AI can gather from it once scouted: nodes are real Resources
    for node in new_nodes:
        game.resources.remove(node)
        game.pathfinder.notify_blocker_removed(node)


def test_bumper_harvest_primes_every_farm(game):
    from entities.building import Building
    from core.config import FARM_FOOD_INTERVAL

    template = game.game_data["buildings"]["farm"]
    farm = Building(name="farm", size=template.size, hp=template.hp, sprite=template.sprite,
                    build_duration=template.build_duration, x=600, y=600,
                    radius=template.radius, player=game.players[0],
                    armor_type=template.armor_type)
    farm.food_timer = 0.0
    game.buildings.append(farm)

    game.dynamic_events.trigger("bumper_harvest")
    assert farm.food_timer == FARM_FOOD_INTERVAL  # ticks on the next frame

    game.buildings.remove(farm)


def test_timer_cadence(game):
    events = game.dynamic_events
    game.mutators = {"random_events"}
    events._timer = 5.0
    random.seed(7)
    events.update(4.0)
    assert events._timer == pytest.approx(1.0)  # not due yet
    events.update(2.0)  # fires and re-arms with jitter
    assert events.EVENT_INTERVAL - events.JITTER <= events._timer <= events.EVENT_INTERVAL + events.JITTER
    game.mutators = set()
