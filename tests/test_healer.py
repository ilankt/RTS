"""Healer behavior tests (§9 backlog: healers now actually heal)."""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from entities.unit import Unit
from systems.collision_system import CollisionSystem
from systems.combat_system import CombatSystem


class FakeMap:
    width = 20
    height = 20

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
        self.game_data = {"units": {"warrior": SimpleNamespace(hp=100), "healer": SimpleNamespace(hp=60)}}
        self.collision_system = CollisionSystem(self)


def make_unit(game, name, player, x, y, hp):
    unit = Unit(
        name=name, size=[1, 1], hp=hp, movement_speed=80, attack=0, animations={},
        x=x, y=y, radius=8, player=player,
    )
    game.units.append(unit)
    return unit


def test_healer_heals_most_wounded_ally_in_range():
    game = FakeGame()
    ally_player = FakePlayer("P1")
    enemy_player = FakePlayer("P2")
    game.players = [ally_player, enemy_player]

    healer = make_unit(game, "healer", ally_player, 200, 200, hp=60)
    lightly_hurt = make_unit(game, "warrior", ally_player, 240, 200, hp=90)
    badly_hurt = make_unit(game, "warrior", ally_player, 200, 260, hp=40)
    enemy_hurt = make_unit(game, "warrior", enemy_player, 220, 220, hp=10)

    combat = CombatSystem(game)
    combat._update_healer(healer, 1 / 60)

    assert badly_hurt.hp == 46  # most-wounded ally healed by HEALER_HEAL_AMOUNT
    assert lightly_hurt.hp == 90
    assert enemy_hurt.hp == 10  # enemies never healed

    # Cooldown gates the next tick
    combat._update_healer(healer, 1 / 60)
    assert badly_hurt.hp == 46

    # After the interval elapses it heals again, clamped at max hp
    combat._update_healer(healer, 2.0)
    assert badly_hurt.hp == 52


def test_healer_ignores_out_of_range_and_full_hp():
    game = FakeGame()
    player = FakePlayer("P1")
    game.players = [player]

    healer = make_unit(game, "healer", player, 200, 200, hp=60)
    far_wounded = make_unit(game, "warrior", player, 900, 900, hp=10)
    healthy = make_unit(game, "warrior", player, 220, 200, hp=100)

    combat = CombatSystem(game)
    combat._update_healer(healer, 1 / 60)

    assert far_wounded.hp == 10
    assert healthy.hp == 100
