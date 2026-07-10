"""Smart context commands + instant command feedback (§7.4)."""
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


def make_dropoff(game, name, near_resource):
    from entities.building import Building

    template = game.game_data["buildings"][name]
    building = Building(
        name=name, size=template.size, hp=template.hp, sprite=template.sprite,
        build_duration=template.build_duration,
        x=near_resource.x + 100, y=near_resource.y,
        radius=template.radius, player=game.players[0],
        armor_type=template.armor_type,
    )
    game.buildings.append(building)
    return building


def test_rightclick_own_dropoff_converts_to_gather(game):
    sm = game.selection_manager
    human = game.players[0]
    worker = next(u for u in game.units if u.player is human and u.name == "worker")
    wood = next(r for r in game.resources if r.name == "wood" and r.amount_remaining > 0)
    lumbermill = make_dropoff(game, "lumbermill", wood)

    worker.resource_amount = 0
    kind, payload = sm._command_spec_for(worker, lumbermill, (lumbermill.x, lumbermill.y))
    assert kind == "gather"
    assert payload.name == "wood"

    # Carrying worker still drops off instead
    worker.resource_amount = 5
    worker.resource_type = "wood"
    kind, _payload = sm._command_spec_for(worker, lumbermill, (lumbermill.x, lumbermill.y))
    assert kind == "dropoff"
    worker.resource_amount = 0

    game.buildings.remove(lumbermill)


def test_enemy_dropoff_is_not_converted(game):
    sm = game.selection_manager
    human = game.players[0]
    worker = next(u for u in game.units if u.player is human and u.name == "worker")
    wood = next(r for r in game.resources if r.name == "wood" and r.amount_remaining > 0)
    lumbermill = make_dropoff(game, "lumbermill", wood)
    lumbermill.player = game.players[1]  # enemy building

    worker.resource_amount = 0
    kind, _payload = sm._command_spec_for(worker, lumbermill, (lumbermill.x, lumbermill.y))
    assert kind != "gather"  # enemy drop-off: move/attack, never gather

    game.buildings.remove(lumbermill)


def test_order_flash_lifecycle(game):
    sm = game.selection_manager
    game.order_flashes = []
    sm._add_order_flash((100, 200), "move")
    assert len(game.order_flashes) == 1
    assert game.order_flashes[0][:3] == (100, 200, "move")

    # Renderer prunes expired flashes
    rs = game.rendering_system
    surface = pygame.Surface((640, 480))
    now = pygame.time.get_ticks()
    game.order_flashes = [
        (100, 200, "move", now),
        (300, 300, "attack", now - rs.ORDER_FLASH_MS - 1),
    ]
    rs._draw_order_flashes(surface, game.camera)
    assert [f[2] for f in game.order_flashes] == ["move"]
