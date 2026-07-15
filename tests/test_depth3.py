"""§8.9 depth round 3: healing fountain, garrison, squad retreat & regroup."""
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
from systems import garrison


@pytest.fixture(scope="module")
def game():
    random.seed(31007)
    from core.game import Game

    return Game(mode="human_1v1", player_count=2)


def make_warrior(game, player, x, y, hp=250):
    unit = Unit(name="warrior", size=[1, 1], hp=hp, movement_speed=50, attack=10,
                animations={}, x=x, y=y, radius=16, player=player,
                min_damage=18, max_damage=22, attack_speed=1.2, attack_range=48,
                can_attack=True)
    game.units.append(unit)
    return unit


# ----------------------------------------------------------- fountain
def test_fountain_placed_near_center_away_from_spawns(game):
    assert game.fountains, "every generated map gets a healing fountain"
    fountain = game.fountains[0]
    for building in game.buildings:
        if building.name == "castle":
            dist = math.hypot(fountain.x - building.x, fountain.y - building.y)
            assert dist > 600, "fountain must be neutral ground, not a base buff"


def test_fountain_heals_nearby_units_only(game):
    from systems.fountain_system import FOUNTAIN_HEAL_RATE

    fountain = game.fountains[0]
    human = game.players[0]
    near = make_warrior(game, human, fountain.x + 80, fountain.y, hp=100)
    far = make_warrior(game, human, fountain.x + 900, fountain.y, hp=100)
    try:
        game.fountain_system.update(2.0)
        assert near.hp == pytest.approx(100 + 2 * FOUNTAIN_HEAL_RATE)
        assert far.hp == 100
        near.hp = 249.5
        game.fountain_system.update(2.0)
        assert near.hp == 250, "healing caps at max hp"
    finally:
        game.units.remove(near)
        game.units.remove(far)


# ----------------------------------------------------------- garrison
def test_garrison_enter_and_eject(game):
    human = game.players[0]
    castle = next(b for b in game.buildings if b.player is human and b.name == "castle")
    unit = make_warrior(game, human, castle.x + castle.radius + 20, castle.y)

    assert garrison.try_enter(game, unit, castle)
    assert unit not in game.units
    assert unit in castle.garrison
    assert unit.garrisoned_in is castle

    ejected = garrison.eject_all(game, castle)
    assert unit in ejected and unit in game.units
    assert unit.garrisoned_in is None
    assert not castle.garrison
    game.units.remove(unit)


def test_garrison_capacity_and_enemy_rejection(game):
    human, enemy = game.players[0], game.players[1]
    castle = next(b for b in game.buildings if b.player is human and b.name == "castle")
    foe = make_warrior(game, enemy, castle.x + 40, castle.y)
    try:
        assert not garrison.can_accept(castle, foe), "no enemies inside"
        units = [make_warrior(game, human, castle.x + 40, castle.y) for _ in range(11)]
        entered = sum(1 for u in units if garrison.try_enter(game, u, castle))
        assert entered == garrison.GARRISON_CAPACITY["castle"]
        garrison.eject_all(game, castle)
        for u in units:
            if u in game.units:
                game.units.remove(u)
    finally:
        if foe in game.units:
            game.units.remove(foe)


def test_building_destruction_ejects_survivors(game):
    human = game.players[0]
    castle = next(b for b in game.buildings if b.player is human and b.name == "castle")
    unit = make_warrior(game, human, castle.x + 40, castle.y)
    assert garrison.try_enter(game, unit, castle)

    game.combat_system.handle_building_destruction(castle)
    try:
        assert unit in game.units, "garrisoned units survive the rubble"
        assert unit.garrisoned_in is None
    finally:
        game.units.remove(unit)
        # put the castle back for the other tests
        castle.in_world = True
        castle.hp = max(castle.hp, 1000)
        game.buildings.append(castle)
        game.pathfinder.notify_blocker_added(castle)


def test_garrisoned_worker_keeps_player_alive(game):
    human = game.players[0]
    castle = next(b for b in game.buildings if b.player is human and b.name == "castle")
    worker = next(u for u in game.units if u.player is human and u.name == "worker")
    assert garrison.try_enter(game, worker, castle)
    try:
        # no castle count, no sites, no field workers - the garrisoned one counts
        others = [u for u in game.units if u.player is human and u.name == "worker"]
        for u in others:
            game.units.remove(u)
        assert game._player_can_continue(human, 0) is True
        for u in others:
            game.units.append(u)
    finally:
        garrison.eject_all(game, castle)


def test_tower_fire_bonus_from_garrison():
    from entities.building import Building

    owner = SimpleNamespace(name="P1", human=False, upgrades={}, upgrades_version=0)
    foe = SimpleNamespace(name="P2", human=False, upgrades={}, upgrades_version=0)
    tower = Building(name="watchtower", size=[2, 2], hp=1500, sprite=None,
                     build_duration=15, x=100, y=100, radius=50, player=owner,
                     can_attack=True, min_damage=14, max_damage=18,
                     attack_speed=1.5, attack_range=230)
    target = SimpleNamespace(hp=1000, x=140, y=100, radius=16, in_world=True,
                             player=foe, armor_type="light", armor_value=0)
    tower.current_target = target
    tower.in_combat = True

    tower._attack_cooldown = 0.0
    tower.update_combat(0.01)
    empty_cooldown = tower._attack_cooldown

    garrison.garrison_list(tower).extend([object(), object()])
    tower._attack_cooldown = 0.0
    tower.update_combat(0.01)
    assert tower._attack_cooldown < empty_cooldown, "garrison speeds tower fire"


# ------------------------------------------------- squad retreat & regroup
def test_squad_retreats_when_outmatched(game):
    from systems.ai.military_brain import MilitaryBrain

    human, enemy = game.players[0], game.players[1]
    moved = []
    fake_game = SimpleNamespace(
        frame_counter=500,
        sim_time_elapsed=100.0,
        selection_manager=SimpleNamespace(
            _move_unit_to_position=lambda u, pos, pf: moved.append((u, pos))),
        pathfinder=None,
    )
    brain = MilitaryBrain(fake_game)

    squad = [make_warrior(game, human, 1000 + i * 30, 1000, hp=100) for i in range(4)]
    for u in squad:
        u.is_engaging = True
    horde = [SimpleNamespace(hp=250, x=1050 + i * 20, y=1020) for i in range(8)]
    castle = SimpleNamespace(x=200, y=200)
    ctx = SimpleNamespace(
        player=SimpleNamespace(name="AI 1", ai_personality="balanced"),
        enemy_units=horde, enemy_buildings=[], fountains=[],
        threat_at=lambda x, y: 0.0,
    )
    try:
        assert brain._check_squad_retreat(ctx, squad, castle) is True
        assert all(not u.is_engaging and not u.in_combat for u in squad)
        assert len(moved) == 4, "every engaged unit was sent to the rally"
        assert brain.is_regrouping(ctx.player) is True

        # Regrouping silences AttackGoal
        from systems.ai.utility.goals.tactical import AttackGoal
        atk_ctx = SimpleNamespace(player=ctx.player, military=squad,
                                  enemy_buildings=[object()], regrouping=True)
        assert AttackGoal().score(atk_ctx) == 0
    finally:
        for u in squad:
            game.units.remove(u)


def test_winning_fight_does_not_retreat(game):
    from systems.ai.military_brain import MilitaryBrain

    human = game.players[0]
    fake_game = SimpleNamespace(frame_counter=1, sim_time_elapsed=0.0,
                                selection_manager=None, pathfinder=None)
    brain = MilitaryBrain(fake_game)
    squad = [make_warrior(game, human, 1000 + i * 30, 1000, hp=250) for i in range(5)]
    for u in squad:
        u.is_engaging = True
    lone_enemy = [SimpleNamespace(hp=100, x=1050, y=1020)]
    ctx = SimpleNamespace(player=SimpleNamespace(name="AI 2"), enemy_units=lone_enemy,
                          enemy_buildings=[], fountains=[], threat_at=lambda x, y: 0.0)
    try:
        assert brain._check_squad_retreat(ctx, squad, SimpleNamespace(x=0, y=0)) is False
        assert all(u.is_engaging for u in squad)
    finally:
        for u in squad:
            game.units.remove(u)
