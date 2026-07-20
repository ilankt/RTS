"""§8.17 follow-up (user: "make them more cowards"): workers flee on
SIGHTING enemy military, and the AI never assigns work into a threat zone."""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

from entities.unit import Unit
from systems.ai.utility.context import GoalContext


@pytest.fixture(scope="module")
def game():
    random.seed(8819)
    from core.game import Game

    return Game(mode="human_1v1", player_count=2)


@pytest.fixture
def no_fog(game):
    was = getattr(game, "fog_of_war_enabled", True)
    game.fog_of_war_enabled = False
    yield game
    game.fog_of_war_enabled = was


def spawn(game, player, name, x, y, can_attack=True):
    unit = Unit(name=name, size=[1, 1], hp=250, movement_speed=50, attack=10,
                animations={}, x=x, y=y, radius=16, player=player,
                min_damage=18, max_damage=22, attack_speed=1.2, attack_range=48,
                can_attack=can_attack)
    game.units.append(unit)
    return unit


def cleanup(game, units):
    for u in units:
        u.in_world = False
        if u in game.units:
            game.units.remove(u)


def test_ai_worker_flees_on_sighting_before_any_damage(game):
    tasks = game.worker_task_system
    ai, enemy = game.players[1], game.players[0]
    worker = spawn(game, ai, "worker", 2000, 2000, can_attack=False)
    raider = spawn(game, enemy, "warrior", 2150, 2000)  # inside sight radius, no shot fired
    try:
        assert getattr(worker, "_last_damage_frame", -1) < 0  # never hit
        worker._next_danger_scan_frame = 0
        tasks._flee_from_attackers()
        assert getattr(worker, "_fleeing_until", 0) > game.frame_counter, \
            "sighting enemy military must trigger flight before the first hit"
    finally:
        cleanup(game, [worker, raider])


def test_sighting_ignores_rams_and_enemy_workers(game):
    tasks = game.worker_task_system
    ai, enemy = game.players[1], game.players[0]
    worker = spawn(game, ai, "worker", 2600, 2600, can_attack=False)
    ram = spawn(game, enemy, "ram", 2700, 2600)
    ram.building_only_attack = True
    peon = spawn(game, enemy, "worker", 2550, 2600, can_attack=False)
    try:
        worker._next_danger_scan_frame = 0
        tasks._flee_from_attackers()
        assert getattr(worker, "_fleeing_until", 0) <= game.frame_counter, \
            "rams (can't hit units) and enemy workers are not flight triggers"
    finally:
        cleanup(game, [worker, ram, peon])


def test_human_workers_never_auto_flee(game):
    tasks = game.worker_task_system
    human, enemy = game.players[0], game.players[1]
    worker = spawn(game, human, "worker", 3000, 3000, can_attack=False)
    raider = spawn(game, enemy, "warrior", 3100, 3000)
    try:
        worker._next_danger_scan_frame = 0
        tasks._flee_from_attackers()
        assert getattr(worker, "_fleeing_until", 0) <= game.frame_counter, \
            "human workers stay under player control"
    finally:
        cleanup(game, [worker, raider])


def test_gather_assignment_skips_threatened_nodes(no_fog):
    game = no_fog
    ai, enemy = game.players[1], game.players[0]
    brain = game.ai_system.worker_brain
    worker = spawn(game, ai, "worker", 500, 500, can_attack=False)
    # A visible enemy squad parked on the nearest gold node
    resource = min((r for r in game.resources if r.name == "gold"),
                   key=lambda r: (r.x - 500) ** 2 + (r.y - 500) ** 2)
    campers = [spawn(game, enemy, "warrior", resource.x + i * 20, resource.y)
               for i in range(3)]
    try:
        ctx = GoalContext.build(game, ai)
        assert ctx.threat_at(resource.x, resource.y) > 0, "campers must register as threat"
        pick = brain._find_best_resource_to_gather(worker, ctx)
        assert pick is not resource, "never assign a gather into a fight"
    finally:
        cleanup(game, [worker] + campers)


def test_builder_assignment_skips_threatened_sites(no_fog):
    game = no_fog
    from entities.construction_site import ConstructionSite

    ai, enemy = game.players[1], game.players[0]
    brain = game.ai_system.worker_brain
    worker = spawn(game, ai, "worker", 900, 900, can_attack=False)
    data = {"size": [1, 1], "hp": 750, "build_duration": 8}
    site = ConstructionSite("mine", data, 1000, 900, radius=32, player=ai)
    game.construction_sites.append(site)
    campers = [spawn(game, enemy, "warrior", 1000 + i * 20, 920) for i in range(3)]
    try:
        ctx = GoalContext.build(game, ai)
        assert ctx.threat_at(site.x, site.y) > 0
        assert brain._find_unattended_construction_site(worker, ctx) is not site, \
            "a worker must not walk into a battle to build a mine"

        cleanup(game, campers)
        campers = []
        ctx = GoalContext.build(game, ai)
        assert brain._find_unattended_construction_site(worker, ctx) is site, \
            "the site comes back into play once the fight clears"
    finally:
        cleanup(game, [worker] + campers)
        site.in_world = False
        game.construction_sites.remove(site)


def test_dropoff_planning_skips_contested_clusters(no_fog):
    game = no_fog
    from systems.ai.economy_helpers import ranked_resources_for_dropoff

    ai, enemy = game.players[1], game.players[0]
    resource = min((r for r in game.resources if r.name == "gold"),
                   key=lambda r: r.x)
    campers = [spawn(game, enemy, "warrior", resource.x + i * 20, resource.y)
               for i in range(3)]
    try:
        ctx = GoalContext.build(game, ai)
        candidates = ranked_resources_for_dropoff(ctx, "mine", limit=10)
        assert resource not in candidates, \
            "never plan a drop-off on a contested cluster"
    finally:
        cleanup(game, campers)
