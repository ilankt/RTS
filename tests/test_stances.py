"""Defensive-stance leash regression tests (MASTER_PLAN §9 backlog).

A DEFENSIVE unit that chases beyond stance_chase_distance must return to its
home position instead of freezing in the field.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from entities.unit import Unit, STANCE_DEFENSIVE
from systems.combat_system import CombatSystem
from systems.pathfinding import Pathfinding


class FakeMap:
    width = 40
    height = 40

    def __init__(self):
        self.grid = [["grass" for _ in range(self.width)] for _ in range(self.height)]

    def world_to_grid(self, x, y):
        col = int(x // 64)
        row = int(y // 64)
        if col < 0 or row < 0 or col >= self.width or row >= self.height:
            return None
        return (col, row)

    def grid_to_world(self, col, row):
        return (col * 64, row * 64)


class FakePlayer:
    def __init__(self, name):
        self.name = name
        self.human = False
        self.upgrades = {}


class FakeGame:
    def __init__(self):
        self.game_map = FakeMap()
        self.units = []
        self.buildings = []
        self.resources = []
        self.construction_sites = []
        self.players = []
        self.frame_counter = 1
        self.pathfinder = Pathfinding(self.game_map, self)


def make_defensive_warrior(game, player, x, y, home):
    unit = Unit(
        name="warrior",
        size=[1, 1],
        hp=100,
        movement_speed=100,
        attack=10,
        animations={},
        x=x,
        y=y,
        radius=8,
        player=player,
        can_attack=True,
        min_damage=5,
        max_damage=8,
        attack_range=32,
    )
    unit.stance = STANCE_DEFENSIVE
    unit.stance_home_position = home
    unit.status = "run"
    game.units.append(unit)
    return unit


def test_defensive_unit_past_leash_returns_home():
    game = FakeGame()
    ally = FakePlayer("P1")
    enemy_player = FakePlayer("P2")
    game.players = [ally, enemy_player]

    home = (200.0, 200.0)
    unit = make_defensive_warrior(game, ally, x=800, y=200, home=home)
    enemy = make_defensive_warrior(game, enemy_player, x=900, y=200, home=(900, 200))
    unit.current_target = enemy
    unit.is_engaging = True

    combat = CombatSystem(game)
    combat.update_combat_units(1 / 60)

    assert unit.current_target is None
    assert not unit.is_engaging
    assert unit.path_target == home or unit.destination == home


def test_defensive_unit_within_leash_keeps_chasing():
    game = FakeGame()
    ally = FakePlayer("P1")
    enemy_player = FakePlayer("P2")
    game.players = [ally, enemy_player]

    home = (200.0, 200.0)
    unit = make_defensive_warrior(game, ally, x=260, y=200, home=home)
    enemy = make_defensive_warrior(game, enemy_player, x=360, y=200, home=(360, 200))
    unit.current_target = enemy
    unit.is_engaging = True

    combat = CombatSystem(game)
    combat.update_combat_units(1 / 60)

    assert unit.current_target is enemy
    assert unit.is_engaging
