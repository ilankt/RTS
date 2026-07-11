"""User-reported: units ordered to attack sometimes stop trying to reach
the target. Two fixes under test: the watchdog resumes interrupted attack
orders instead of wiping them, and attack contact points prefer arcs not
already held by in-combat friendlies."""
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


def spawn_warrior(game, x, y, player):
    from entities import Unit

    data = game.production_manager.units_data["warrior"]
    unit = Unit(name="warrior", size=data['size'], hp=data['hp'],
                movement_speed=data['movement_speed'], attack=data.get('attack'),
                animations={}, x=x, y=y, radius=8, player=player,
                can_attack=data.get('can_attack', False),
                min_damage=data['min_damage'], max_damage=data['max_damage'],
                attack_type=data['attack_type'])
    game.units.append(unit)
    return unit


def test_watchdog_resumes_attack_orders(game):
    """Recovery used to wipe current_target entirely - the wedged besieger
    idled in the field forever."""
    human, enemy = game.players[0], game.players[1]
    enemy_castle = next(b for b in game.buildings
                        if b.player is enemy and b.name == "castle")
    unit = spawn_warrior(game, enemy_castle.x - 300, enemy_castle.y, human)
    unit.current_target = enemy_castle
    unit.is_engaging = True

    game.unit_watchdog._recover_unit(unit)

    assert unit.current_target is enemy_castle   # order survives recovery
    assert unit.is_engaging is True
    assert unit.path is not None or unit.destination is not None

    game.units.remove(unit)


def test_watchdog_does_not_resume_attack_on_dead_target(game):
    human, enemy = game.players[0], game.players[1]
    enemy_castle = next(b for b in game.buildings
                        if b.player is enemy and b.name == "castle")
    unit = spawn_warrior(game, enemy_castle.x - 300, enemy_castle.y, human)
    unit.current_target = enemy_castle
    unit.is_engaging = True

    old_hp = enemy_castle.hp
    enemy_castle.hp = 0
    game.unit_watchdog._recover_unit(unit)
    enemy_castle.hp = old_hp

    assert unit.current_target is None  # no zombie orders
    game.units.remove(unit)


def test_attack_candidates_prefer_free_arcs(game):
    """A contact point held by an in-combat friendly sorts behind free ones,
    so latecomers route around the ring instead of wedging."""
    human, enemy = game.players[0], game.players[1]
    enemy_castle = next(b for b in game.buildings
                        if b.player is enemy and b.name == "castle")

    attacker = spawn_warrior(game, enemy_castle.x - 300, enemy_castle.y, human)
    pf = game.pathfinder
    candidates = pf._interaction_candidates(
        (attacker.x, attacker.y), attacker, enemy_castle, "attack")
    near_point = candidates[0]  # geometric order: nearest arc first

    # Park an in-combat friendly exactly on that point
    blocker = spawn_warrior(game, near_point[0], near_point[1], human)
    blocker.in_combat = True
    game.collision_system.mark_dirty() if hasattr(game.collision_system, 'mark_dirty') else None
    game.update(delta_time_override=1 / 60)  # let the spatial index see it

    reordered = pf._interaction_candidates(
        (attacker.x, attacker.y), attacker, enemy_castle, "attack")
    spacing = max(12.0, attacker.radius * 1.8)
    dx = reordered[0][0] - near_point[0]
    dy = reordered[0][1] - near_point[1]
    assert (dx * dx + dy * dy) ** 0.5 > spacing  # occupied arc no longer first
    assert sorted(reordered) == sorted(candidates)  # same points, reordered

    game.units.remove(attacker)
    game.units.remove(blocker)


def test_enemy_health_bars_respect_fog(game):
    """User-reported: enemy health bars leaked through unexplored fog
    (bars draw above the fog overlay, so they must fog-check themselves)."""
    human, enemy = game.players[0], game.players[1]
    enemy_castle = next(b for b in game.buildings
                        if b.player is enemy and b.name == "castle")
    own_castle = next(b for b in game.buildings
                      if b.player is human and b.name == "castle")

    game.fog_of_war_enabled = True
    fui = game.floating_ui
    assert fui._visible_through_fog(own_castle) is True
    # The enemy start is unexplored at match start
    if not game.fog_of_war.is_object_visible(enemy_castle):
        assert fui._visible_through_fog(enemy_castle) is False

    game.fog_of_war_enabled = False
    assert fui._visible_through_fog(enemy_castle) is True  # fog off: draw all
