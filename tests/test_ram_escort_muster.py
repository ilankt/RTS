"""§8.14 AI tuning: rams never march unescorted, attacks launch as
mustered waves instead of trickling singles."""
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
from systems.ai.utility.context import GoalContext, combatants_of


@pytest.fixture(scope="module")
def game():
    random.seed(8814)
    from core.game import Game

    return Game(mode="human_1v1", player_count=2)


def spawn(game, player, name, x, y, **kw):
    unit = Unit(name=name, size=[1, 1], hp=kw.get("hp", 250), movement_speed=50,
                attack=10, animations={}, x=x, y=y, radius=16, player=player,
                min_damage=18, max_damage=22, attack_speed=1.2, attack_range=48,
                can_attack=True)
    if name == "ram":
        unit.building_only_attack = True
    game.units.append(unit)
    return unit


def add_barracks(game, player, x=900, y=900):
    from entities.building import Building

    template = game.game_data["buildings"]["barracks"]
    barracks = Building(
        name="barracks", size=template.size, hp=template.hp, sprite=template.sprite,
        build_duration=template.build_duration, x=x, y=y, radius=template.radius,
        player=player, armor_type=template.armor_type)
    game.buildings.append(barracks)
    return barracks


@pytest.fixture
def moved(monkeypatch, game):
    calls = []
    monkeypatch.setattr(
        game.selection_manager, "_move_unit_to_position",
        lambda unit, pos, pf: calls.append((unit, pos)))
    return calls


# ------------------------------------------------------- ram escorts (§8.14)

def test_unescorted_working_ram_is_recalled_home(game, moved):
    brain = game.ai_system.military_brain
    ai = game.players[1]
    castle = next(b for b in game.buildings if b.player is ai and b.name == "castle")
    barracks = add_barracks(game, ai)  # a trainer exists -> fighters can come
    ai.resources = {"food": 500, "gold": 500, "stone": 500, "wood": 500}
    ram = spawn(game, ai, "ram", castle.x + 900, castle.y + 900)
    ram.destination = (castle.x + 1500, castle.y + 1500)  # marching out alone
    try:
        ctx = GoalContext.build(game, ai)
        combatants = combatants_of(ctx.military)
        assert ram in combatants and len(combatants) == 1  # no fighters at all
        brain._maintain_ram_escorts(ctx, combatants)
        assert moved, "the escortless ram was not recalled"
        recalled, pos = moved[-1]
        assert recalled is ram
        assert math.hypot(pos[0] - castle.x, pos[1] - castle.y) <= brain.RAM_HOME_RADIUS
    finally:
        game.units.remove(ram)
        game.buildings.remove(barracks)
        ram.in_world = barracks.in_world = False


def test_desperate_ram_is_released(game, moved):
    """No trainer, no savings, nothing queued -> the all-in is sanctioned."""
    brain = game.ai_system.military_brain
    ai = game.players[1]
    castle = next(b for b in game.buildings if b.player is ai and b.name == "castle")
    saved = dict(ai.resources)
    ai.resources = {"food": 0, "gold": 0, "stone": 0, "wood": 0}
    ram = spawn(game, ai, "ram", castle.x + 900, castle.y + 900)
    ram.destination = (castle.x + 1500, castle.y + 1500)
    try:
        ctx = GoalContext.build(game, ai)
        assert not brain._fighters_incoming(ctx)
        brain._maintain_ram_escorts(ctx, combatants_of(ctx.military))
        assert not moved, "a desperate ram must be allowed to press on"
    finally:
        ai.resources = saved
        game.units.remove(ram)
        ram.in_world = False


def test_launch_wave_holds_rams_without_fighters(game, moved, monkeypatch):
    brain = game.ai_system.military_brain
    ai = game.players[1]
    castle = next(b for b in game.buildings if b.player is ai and b.name == "castle")
    barracks = add_barracks(game, ai)
    ai.resources = {"food": 500, "gold": 500, "stone": 500, "wood": 500}
    ram = spawn(game, ai, "ram", castle.x + 100, castle.y + 100)
    attacked = []
    monkeypatch.setattr(brain, "_command_attack",
                        lambda unit, target, ctx: attacked.append(unit))
    monkeypatch.setattr(brain, "_find_attack_target",
                        lambda ctx: SimpleNamespace(name="castle", x=2000, y=2000, hp=2500))
    monkeypatch.setattr(brain, "_find_focus_fire_target", lambda ctx, wave: None)
    try:
        ctx = GoalContext.build(game, ai)
        brain._launch_wave(ctx, [ram])
        assert attacked == [], "a ram with no fighter escort must not be sent"
    finally:
        game.units.remove(ram)
        game.buildings.remove(barracks)
        ram.in_world = barracks.in_world = False


# ------------------------------------------------------- attack musters

def test_attack_tick_musters_instead_of_sending(game, moved, monkeypatch):
    brain = game.ai_system.military_brain
    ai = game.players[1]
    castle = next(b for b in game.buildings if b.player is ai and b.name == "castle")
    squad = [spawn(game, ai, "warrior", castle.x + 60 * i, castle.y + 400)
             for i in range(4)]
    attacked = []
    monkeypatch.setattr(brain, "_command_attack",
                        lambda unit, target, ctx: attacked.append(unit))
    target = SimpleNamespace(name="castle", x=3000, y=3000, hp=2500)
    try:
        ctx = GoalContext.build(game, ai)
        brain._create_muster(ctx, combatants_of(ctx.military), target)
        assert ai.name in brain._musters
        # Units were rallied to a gathering point, NOT sent at the enemy
        assert attacked == []
        assert moved, "muster members must be walked to the rally point"
        point = brain._musters[ai.name]["point"]
        for _unit, pos in moved:
            assert math.hypot(pos[0] - point[0], pos[1] - point[1]) <= brain.MUSTER_RADIUS
    finally:
        brain._musters.pop(ai.name, None)
        for u in squad:
            game.units.remove(u)
            u.in_world = False


def test_formed_wave_launches_together(game, moved, monkeypatch):
    brain = game.ai_system.military_brain
    ai = game.players[1]
    castle = next(b for b in game.buildings if b.player is ai and b.name == "castle")
    point = (castle.x + 500, castle.y + 500)
    squad = [spawn(game, ai, "warrior", point[0] + 20 * i, point[1]) for i in range(5)]
    waves = []
    monkeypatch.setattr(brain, "_launch_wave", lambda ctx, wave: waves.append(list(wave)))
    brain._musters[ai.name] = {"point": point, "since": game.sim_time_elapsed}
    try:
        ctx = GoalContext.build(game, ai)
        brain._advance_muster(ctx, combatants_of(ctx.military))
        assert ai.name not in brain._musters
        assert len(waves) == 1 and len(waves[0]) >= 5, \
            "a formed-up wave must launch as one group"
    finally:
        brain._musters.pop(ai.name, None)
        for u in squad:
            game.units.remove(u)
            u.in_world = False


def test_undersized_muster_waits_then_launches_on_timeout(game, moved, monkeypatch):
    brain = game.ai_system.military_brain
    ai = game.players[1]
    castle = next(b for b in game.buildings if b.player is ai and b.name == "castle")
    # Two fighters formed at the rally, three more far away: below the wave
    # size -> the muster holds...
    point = (castle.x + 500, castle.y + 500)
    near = [spawn(game, ai, "warrior", point[0] + 20 * i, point[1]) for i in range(2)]
    far = [spawn(game, ai, "warrior", point[0] + 2000, point[1] + 2000) for _ in range(3)]
    waves = []
    monkeypatch.setattr(brain, "_launch_wave", lambda ctx, wave: waves.append(list(wave)))
    brain._musters[ai.name] = {"point": point, "since": game.sim_time_elapsed}
    try:
        ctx = GoalContext.build(game, ai)
        brain._advance_muster(ctx, combatants_of(ctx.military))
        assert waves == [] and ai.name in brain._musters, "2/5 formed: keep gathering"

        # ...until the wait runs out — then whoever formed up goes together
        brain._musters[ai.name]["since"] = game.sim_time_elapsed - brain.MUSTER_TIMEOUT_S - 1
        brain._advance_muster(ctx, combatants_of(ctx.military))
        assert len(waves) == 1 and set(waves[0]) == set(near)
    finally:
        brain._musters.pop(ai.name, None)
        for u in near + far:
            game.units.remove(u)
            u.in_world = False
