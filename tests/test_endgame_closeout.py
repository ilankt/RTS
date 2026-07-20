"""§8.16 endgame close-out (balance report change 6): dominant armies launch
full-strength waves, sweep explored ground for remnant workers, and keep
AttackGoal live through regroup pauses; ram share cap 25% -> 12%."""
import math
import os
import random
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

from entities.unit import Unit
from systems.ai.utility.context import GoalContext


@pytest.fixture(scope="module")
def game():
    random.seed(8816)
    from core.game import Game

    return Game(mode="human_1v1", player_count=2)


def spawn(game, player, name, x, y):
    unit = Unit(name=name, size=[1, 1], hp=250, movement_speed=50,
                attack=10, animations={}, x=x, y=y, radius=16, player=player,
                min_damage=18, max_damage=22, attack_speed=1.2, attack_range=48,
                can_attack=True)
    game.units.append(unit)
    return unit


def cleanup(game, units):
    for unit in units:
        unit.in_world = False
        if unit in game.units:
            game.units.remove(unit)


# ---------------------------------------------------------- overwhelming()

def test_overwhelming_requires_a_real_army(game):
    brain = game.ai_system.military_brain
    ai = game.players[1]
    castle = next(b for b in game.buildings if b.player is ai and b.name == "castle")
    spawned = [spawn(game, ai, "warrior", castle.x + 60 + i * 20, castle.y) for i in range(5)]
    try:
        ctx = GoalContext.build(game, ai)
        assert brain.overwhelming(ctx) is False, "5 fighters is not dominance"
    finally:
        cleanup(game, spawned)


def test_overwhelming_true_vs_remnants_false_vs_army(game):
    brain = game.ai_system.military_brain
    ai, enemy = game.players[1], game.players[0]
    castle = next(b for b in game.buildings if b.player is ai and b.name == "castle")
    spawned = [spawn(game, ai, "warrior", castle.x + 60 + i * 20, castle.y) for i in range(14)]
    try:
        ctx = GoalContext.build(game, ai)
        ctx.enemy_units = []              # nothing visible through fog
        assert brain.overwhelming(ctx) is True, "14 fighters vs nothing visible is dominance"

        # A comparable visible enemy force cancels dominance. (Set on the
        # snapshot directly — fog visibility grids only refresh on frame
        # ticks, which these fixture games never run.)
        ctx.enemy_units = [SimpleNamespace(name="warrior", player=enemy) for _ in range(6)]
        assert brain.overwhelming(ctx) is False, "14 vs 6 visible is not 3x dominance"

        # §8.15 FFA close-out: dominance is judged against the WEAKEST enemy —
        # a second enemy fielding a token force makes mop-up start even
        # though the combined enemy count would deny 3x.
        third = SimpleNamespace(name="AI 3")
        ctx.enemy_units += [SimpleNamespace(name="warrior", player=third) for _ in range(2)]
        assert brain.overwhelming(ctx) is True, \
            "14 vs a weakest-enemy force of 2 is dominance (per-player, not summed)"
    finally:
        cleanup(game, spawned)


# ---------------------------------------------------------- AttackGoal

def test_dominant_attack_bypasses_regroup_and_hunts_units(game):
    from systems.ai.utility.goals.tactical import AttackGoal

    ai, enemy = game.players[1], game.players[0]
    castle = next(b for b in game.buildings if b.player is ai and b.name == "castle")
    spawned = [spawn(game, ai, "warrior", castle.x + 60 + i * 20, castle.y) for i in range(14)]
    worker = spawn(game, enemy, "worker", castle.x + 200, castle.y + 40)
    spawned.append(worker)
    try:
        ctx = GoalContext.build(game, ai)
        ctx.enemy_buildings = []          # everything known is razed
        ctx.enemy_units = [worker]        # the spotted remnant

        goal = AttackGoal()
        assert goal.score(ctx) > 0, "dominant army must hunt remnant units"

        ctx.regrouping = True
        assert goal.score(ctx) > 0, "dominance bypasses the regroup pause"
    finally:
        cleanup(game, spawned)


def test_normal_attack_still_needs_buildings_and_respects_regroup(game):
    from systems.ai.utility.goals.tactical import AttackGoal

    ai, enemy = game.players[1], game.players[0]
    castle = next(b for b in game.buildings if b.player is ai and b.name == "castle")
    # Small army (not dominant), a visible enemy fighter but no buildings
    spawned = [spawn(game, ai, "warrior", castle.x + 60 + i * 20, castle.y) for i in range(8)]
    foes = [SimpleNamespace(name="warrior", player=enemy) for _ in range(4)]
    try:
        ctx = GoalContext.build(game, ai)
        ctx.enemy_buildings = []
        ctx.enemy_units = list(foes)
        goal = AttackGoal()
        assert goal.score(ctx) == 0, "non-dominant armies still need a building target"

        ctx = GoalContext.build(game, ai)
        ctx.enemy_units = list(foes)
        ctx.regrouping = True
        assert goal.score(ctx) == 0, "regroup pause still holds for even fights"
    finally:
        cleanup(game, spawned)


# ---------------------------------------------------------- muster wave size

def test_dominant_muster_launches_the_whole_army(game, monkeypatch):
    brain = game.ai_system.military_brain
    ai = game.players[1]
    castle = next(b for b in game.buildings if b.player is ai and b.name == "castle")
    # 15 fighters: 3 formed at the rally, 12 scattered far away
    point = (castle.x + 400, castle.y)
    formed = [spawn(game, ai, "warrior", point[0] + i * 10, point[1]) for i in range(3)]
    scattered = [spawn(game, ai, "warrior", castle.x - 600 - i * 30, castle.y - 500)
                 for i in range(12)]
    spawned = formed + scattered
    waves = []
    monkeypatch.setattr(brain, "_launch_wave", lambda ctx, wave: waves.append(list(wave)))
    try:
        ctx = GoalContext.build(game, ai)
        brain._musters[ai.name] = {"point": point, "since": -1e9}  # timeout: launch now
        brain._advance_muster(ctx, list(ctx.military))
        assert waves, "muster must launch on timeout"
        assert len(waves[0]) == 15, (
            f"dominant wave must commit everyone, got {len(waves[0])}")
        assert ai.name not in brain._musters
    finally:
        cleanup(game, spawned)


# ---------------------------------------------------------- remnant sweep

def test_sweep_anchors_rotate_across_the_map(game):
    brain = game.ai_system.military_brain
    ai = game.players[1]
    ctx = SimpleNamespace(player=ai)
    from core.config import TILE_WIDTH, TILE_HEIGHT

    world_w = game.game_map.width * TILE_WIDTH
    world_h = game.game_map.height * TILE_HEIGHT
    anchors = {brain._next_sweep_anchor(ctx) for _ in range(brain.SWEEP_GRID ** 2)}
    assert len(anchors) == brain.SWEEP_GRID ** 2, "anchors must cycle, not repeat"
    for x, y in anchors:
        assert 0 < x < world_w and 0 < y < world_h


def test_army_sweeps_when_map_explored_and_no_targets(game, monkeypatch):
    brain = game.ai_system.military_brain
    ai = game.players[1]
    castle = next(b for b in game.buildings if b.player is ai and b.name == "castle")
    spawned = [spawn(game, ai, "warrior", castle.x + 60 + i * 20, castle.y) for i in range(8)]
    moved = []
    monkeypatch.setattr(game.selection_manager, "_move_unit_to_position",
                        lambda unit, pos, pf: moved.append((unit, pos)))
    # Fully-explored map: no unexplored anchor left
    monkeypatch.setattr(game.ai_system.scout_brain, "next_unexplored_anchor",
                        lambda player, from_pos=None: None)
    try:
        ctx = GoalContext.build(game, ai)
        ctx.enemy_buildings = []
        ctx.enemy_units = []              # remnants hiding in fog
        brain.update(ctx, should_attack=False)
        assert moved, "idle dominant army must sweep explored ground for remnants"
    finally:
        cleanup(game, spawned)


# ---------------------------------------------------------- ram cap

def test_ram_cap_holds_at_12_percent(game):
    from entities.building import Building
    from systems.ai.utility.goals.military import TrainRamGoal

    ai = game.players[1]
    castle = next(b for b in game.buildings if b.player is ai and b.name == "castle")
    template = game.game_data["buildings"]["siege_workshop"]
    workshop = Building(
        name="siege_workshop", size=template.size, hp=template.hp, sprite=template.sprite,
        build_duration=template.build_duration, x=castle.x + 200, y=castle.y + 200,
        radius=template.radius, player=ai, armor_type=template.armor_type)
    game.buildings.append(workshop)
    saved = dict(ai.resources)
    ai.resources = {"food": 500, "gold": 500, "wood": 500}

    # 25-strong military: 3 rams is 12% -> capped silent
    spawned = [spawn(game, ai, "warrior", castle.x + 60 + i * 15, castle.y) for i in range(22)]
    spawned += [spawn(game, ai, "ram", castle.x + 90 + i * 20, castle.y + 60) for i in range(3)]
    goal = TrainRamGoal()
    try:
        ctx = GoalContext.build(game, ai)
        ctx.pop_max = 200                 # cap test, not a housing test
        assert len(ctx.military) == 25
        assert goal.score(ctx) == 0, "3 rams in 25 (12%) must hit the cap"

        # Drop one ram -> 2/24 (8%) is under the cap again
        cleanup(game, [spawned[-1]])
        spawned.pop()
        ctx = GoalContext.build(game, ai)
        ctx.pop_max = 200
        assert goal.score(ctx) > 0, "8% rams must be allowed to build"
    finally:
        ai.resources = saved
        cleanup(game, spawned)
        game.buildings.remove(workshop)
        workshop.in_world = False
