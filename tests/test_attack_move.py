"""§8.14 attack-move: march to a point, auto-engage enemies sighted en
route, resume the march after the fight, clear the order on arrival."""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

from entities.unit import Unit


@pytest.fixture(scope="module")
def game():
    random.seed(8814)
    from core.game import Game

    g = Game(mode="human_1v1", player_count=2)
    # The AI must not interfere with the scripted marches below
    g.ai_system.update = lambda dt: None
    return g


def make_warrior(game, player, x, y, hp=250):
    unit = Unit(name="warrior", size=[1, 1], hp=hp, movement_speed=50, attack=10,
                animations={}, x=x, y=y, radius=16, player=player,
                min_damage=18, max_damage=22, attack_speed=1.2, attack_range=48,
                can_attack=True)
    game.units.append(unit)
    return unit


def order_attack_move(game, units, point):
    game.selection_manager._execute_command_mode_action(
        "attack_move", units, point, None)


def run(game, frames, dt=0.1):
    for _ in range(frames):
        game.update(delta_time_override=dt)


def test_attack_move_engages_enemy_on_the_way(game):
    human, enemy_player = game.players[0], game.players[1]
    # Open ground far from both bases
    marcher = make_warrior(game, human, 1200, 1200)
    enemy = make_warrior(game, enemy_player, 1400, 1200)
    try:
        order_attack_move(game, [marcher], (1700, 1200))
        assert marcher.attack_move_target == (1700, 1200)
        run(game, 80)
        # The march noticed the enemy inside MOVE_AGGRO_RANGE and engaged —
        # a plain move would have walked straight past
        assert (marcher.current_target is enemy or marcher.in_combat
                or enemy.hp < 250), "attack-move never engaged the enemy en route"
        assert marcher.attack_move_target == (1700, 1200), \
            "the order must survive the engagement"
    finally:
        for u in (marcher, enemy):
            if u in game.units:
                game.units.remove(u)
            u.in_world = False


def test_attack_move_resumes_after_kill_and_clears_on_arrival(game):
    human, enemy_player = game.players[0], game.players[1]
    marcher = make_warrior(game, human, 1200, 1500)
    enemy = make_warrior(game, enemy_player, 1330, 1500, hp=40)
    try:
        order_attack_move(game, [marcher], (1600, 1500))
        run(game, 200)
        assert enemy.hp <= 0, "the weak enemy should have died to the marcher"
        run(game, 300)
        # March resumed and completed: order cleared at the destination
        assert marcher.attack_move_target is None
        assert math.hypot(marcher.x - 1600, marcher.y - 1500) <= 120
    finally:
        for u in (marcher, enemy):
            if u in game.units:
                game.units.remove(u)
            u.in_world = False


def test_plain_move_and_stop_cancel_attack_move(game):
    human = game.players[0]
    unit = make_warrior(game, human, 900, 900)
    try:
        order_attack_move(game, [unit], (1500, 900))
        assert unit.attack_move_target is not None
        game.selection_manager._move_unit_to_position(unit, (950, 900), game.pathfinder)
        assert unit.attack_move_target is None

        order_attack_move(game, [unit], (1500, 900))
        assert unit.attack_move_target is not None
        unit.stop()
        assert unit.attack_move_target is None
    finally:
        if unit in game.units:
            game.units.remove(unit)
        unit.in_world = False


def test_attack_move_valid_units_are_combatants_only(game):
    human = game.players[0]
    worker = next(u for u in game.units if u.player is human and u.name == "worker")
    warrior = make_warrior(game, human, 800, 800)
    try:
        game.selection_manager.selected_objects = [worker, warrior]
        valid = game.selection_manager._get_valid_units_for_command("attack_move")
        assert warrior in valid and worker not in valid
    finally:
        game.selection_manager.selected_objects = []
        if warrior in game.units:
            game.units.remove(warrior)
        warrior.in_world = False
