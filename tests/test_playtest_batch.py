"""§8.11 playtest feedback batch: frozen attack animations, retaliation
while moving, emergency castle defense, worker stall timeouts."""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from entities.unit import Unit, STANCE_NO_ATTACK
from systems.collision_system import CollisionSystem
from systems.combat_system import CombatSystem
from systems.ai.military_brain import MilitaryBrain


class FakeMap:
    width = 30
    height = 30

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
    def __init__(self, name, human=False):
        self.name = name
        self.human = human
        self.upgrades = {}
        self.upgrades_version = 0
        self.auto_attack = True


class FakeGame:
    def __init__(self):
        self.game_map = FakeMap()
        self.units = []
        self.buildings = []
        self.resources = []
        self.construction_sites = []
        self.players = []
        self.frame_counter = 1
        self.game_data = {"units": {"warrior": SimpleNamespace(hp=250),
                                    "healer": SimpleNamespace(hp=120)}}
        self.collision_system = CollisionSystem(self)


def make_warrior(game, player, x, y, hp=250):
    unit = Unit(
        name="warrior", size=[1, 1], hp=hp, movement_speed=50, attack=10,
        animations={}, x=x, y=y, radius=16, player=player,
        min_damage=18, max_damage=22, attack_type="slash", armor_type="heavy",
        armor_value=4, attack_speed=1.2, attack_range=48, can_attack=True,
    )
    game.units.append(unit)
    return unit


def make_combat_pair():
    game = FakeGame()
    p1, p2 = FakePlayer("P1"), FakePlayer("P2")
    game.players = [p1, p2]
    return game, p1, p2


# ---------------------------------------------------------------- frozen
def test_target_death_resets_attackers_to_idle():
    """Focus-fire kill: units whose target dies must not freeze in the
    attack pose - they reset to idle and can re-acquire."""
    game, p1, p2 = make_combat_pair()
    a = make_warrior(game, p1, 100, 100)
    b = make_warrior(game, p1, 140, 100)
    victim = make_warrior(game, p2, 120, 120, hp=1)

    for attacker in (a, b):
        attacker.current_target = victim
        attacker.in_combat = True
        attacker.status = "attack"

    combat = CombatSystem(game)
    victim.hp = 0
    combat.handle_unit_death(victim)

    for attacker in (a, b):
        assert attacker.current_target is None
        assert attacker.in_combat is False
        assert attacker.status == "idle", "no more frozen attack animation"


def test_corpses_are_not_valid_targets():
    from systems.combat_rules import is_valid_attack_target

    game, p1, p2 = make_combat_pair()
    attacker = make_warrior(game, p1, 100, 100)
    corpse = make_warrior(game, p2, 120, 100, hp=0)
    despawned = make_warrior(game, p2, 130, 100)
    despawned.in_world = False

    assert not is_valid_attack_target(attacker, corpse)
    assert not is_valid_attack_target(attacker, despawned)


def test_idle_healer_drops_cast_pose():
    game, p1, _ = make_combat_pair()
    healer = Unit(name="healer", size=[1, 1], hp=120, movement_speed=55, attack=0,
                  animations={}, x=200, y=200, radius=16, player=p1)
    game.units.append(healer)
    healer.status = "attack"  # finished a cast, nobody wounded anymore

    combat = CombatSystem(game)
    combat._update_healer(healer, 1 / 60)
    assert healer.status == "idle"


# ------------------------------------------------------------ retaliation
def test_moving_unit_retaliates_against_attacker():
    """§8.11: a unit hit while marching turns on its attacker instead of
    soaking free damage."""
    game, p1, p2 = make_combat_pair()
    marcher = make_warrior(game, p1, 300, 300)
    far_goal = SimpleNamespace(name="castle", x=1500, y=1500, hp=2500,
                               player=p2, in_world=True)
    marcher.current_target = far_goal
    marcher.is_engaging = True
    marcher.status = "run"

    attacker = make_warrior(game, p2, 330, 300)

    combat = CombatSystem(game)
    # Simulate the damage stamp the combat loop writes when attacker hits
    marcher.hp -= 20
    marcher.last_attacker = attacker
    marcher._last_damage_frame = game.frame_counter

    combat.update_combat_units(1 / 60)

    assert marcher.current_target is attacker, "marcher should turn and fight"
    # Same tick the engagement handler may already promote it into combat
    assert marcher.is_engaging or marcher.in_combat


def test_no_attack_stance_never_retaliates():
    game, p1, p2 = make_combat_pair()
    pacifist = make_warrior(game, p1, 300, 300)
    pacifist.stance = STANCE_NO_ATTACK
    pacifist.status = "run"
    attacker = make_warrior(game, p2, 330, 300)
    pacifist.last_attacker = attacker
    pacifist._last_damage_frame = game.frame_counter

    CombatSystem(game).update_combat_units(1 / 60)
    assert pacifist.current_target is not attacker


def test_ram_never_retaliates_against_units():
    """Rams can only hit buildings — a marching ram under fire keeps rolling
    (this path once crashed on a missing import: rams are the only units
    that evaluate the building-target check)."""
    game, p1, p2 = make_combat_pair()
    ram = Unit(name="ram", size=[1.25, 1.25], hp=300, movement_speed=28, attack=45,
               animations={}, x=300, y=300, radius=20, player=p1,
               min_damage=85, max_damage=115, attack_type="siege",
               armor_type="siege", armor_value=0, attack_speed=0.45,
               attack_range=56, can_attack=True)
    ram.building_only_attack = True
    game.units.append(ram)
    ram.status = "run"

    attacker = make_warrior(game, p2, 330, 300)
    ram.last_attacker = attacker
    ram._last_damage_frame = game.frame_counter

    CombatSystem(game).update_combat_units(1 / 60)  # must not raise
    assert ram.current_target is not attacker


def test_out_of_range_attacker_is_ignored():
    game, p1, p2 = make_combat_pair()
    marcher = make_warrior(game, p1, 300, 300)
    marcher.status = "run"
    sniper = make_warrior(game, p2, 300 + 800, 300)  # beyond chase distance
    marcher.last_attacker = sniper
    marcher._last_damage_frame = game.frame_counter

    CombatSystem(game).update_combat_units(1 / 60)
    assert marcher.current_target is not sniper


# ---------------------------------------------------- §8.12 awareness
def test_ai_marcher_engages_enemy_units_passing_by():
    """Armies no longer pass each other blindly: an AI unit on the move
    engages enemy units that come within reach (no damage needed)."""
    game, p1, p2 = make_combat_pair()
    marcher = make_warrior(game, p1, 300, 300)
    marcher.status = "run"
    enemy = make_warrior(game, p2, 420, 300)  # within MARCH_ENGAGE_RANGE

    CombatSystem(game).update_combat_units(1 / 60)
    assert marcher.current_target is enemy


def test_human_marcher_orders_stay_literal():
    game, p1, p2 = make_combat_pair()
    p1.human = True
    marcher = make_warrior(game, p1, 300, 300)
    marcher.status = "run"
    make_warrior(game, p2, 420, 300)

    CombatSystem(game).update_combat_units(1 / 60)
    assert marcher.current_target is None, "human move commands are not hijacked"


def test_sieging_unit_switches_to_guard_when_hit():
    """§8.12 no tunnel vision: hammering a building while a guard kills you
    is over — the unit turns on the guard."""
    game, p1, p2 = make_combat_pair()
    attacker_of_building = make_warrior(game, p1, 300, 300)

    class Building:  # is_building_target checks the class NAME
        pass

    building = Building()
    building.name, building.x, building.y = "castle", 320, 300
    building.hp, building.player, building.in_world = 2500, p2, True
    building.radius, building.size = 60, [2.5, 2.5]
    building.armor_type, building.armor_value = "fortified", 10
    attacker_of_building.current_target = building
    attacker_of_building.in_combat = True
    attacker_of_building.status = "attack"

    guard = make_warrior(game, p2, 330, 320)
    attacker_of_building.last_attacker = guard
    attacker_of_building._last_damage_frame = game.frame_counter

    CombatSystem(game).update_combat_units(1 / 60)
    assert attacker_of_building.current_target is guard, "the building can wait"


# ------------------------------------------------------- emergency defense
def _emergency_ctx(castle, military, enemy, under_attack):
    return SimpleNamespace(
        castle=castle,
        military=military,
        enemies_near_base=[enemy],
        player=SimpleNamespace(name="AI", ai_personality="balanced"),
        buildings={},
        castle_under_attack=under_attack,
    )


def _brain_with_recorder(game):
    brain = MilitaryBrain(game)
    commanded = []
    brain._command_attack = lambda unit, target, ctx: commanded.append((unit, target))
    brain._apply_micro = lambda military, castle, cache: None
    return brain, commanded


def test_castle_under_attack_recalls_far_marchers():
    game, p1, p2 = make_combat_pair()
    castle = SimpleNamespace(name="castle", x=200, y=200, hp=1200, player=p1)
    raider = make_warrior(game, p2, 250, 250)

    far_marcher = make_warrior(game, p1, 1500, 1500)
    far_marcher.is_engaging = True
    far_marcher.current_target = SimpleNamespace(name="castle", x=1800, y=1800, hp=100)
    near_fighter = make_warrior(game, p1, 300, 250)
    near_fighter.in_combat = True
    near_fighter.current_target = raider

    brain, commanded = _brain_with_recorder(game)
    ctx = _emergency_ctx(castle, [far_marcher, near_fighter], raider, under_attack=True)
    brain.update(ctx, should_attack=False)

    assert far_marcher.is_engaging is False, "far marcher aborts its attack"
    assert far_marcher in [u for u, _t in commanded], "and is sent home to defend"
    assert near_fighter.current_target is raider, "local fighters keep fighting"
    assert near_fighter not in [u for u, _t in commanded]


def test_normal_defense_never_interrupts_marches():
    game, p1, p2 = make_combat_pair()
    castle = SimpleNamespace(name="castle", x=200, y=200, hp=2500, player=p1)
    raider = make_warrior(game, p2, 250, 250)
    far_marcher = make_warrior(game, p1, 1500, 1500)
    far_marcher.is_engaging = True

    brain, commanded = _brain_with_recorder(game)
    ctx = _emergency_ctx(castle, [far_marcher], raider, under_attack=False)
    brain.update(ctx, should_attack=False)

    assert far_marcher.is_engaging is True
    assert far_marcher not in [u for u, _t in commanded]


def test_defend_goal_escalates_when_castle_hit():
    from systems.ai.utility.goals.tactical import DefendBaseGoal

    threats = [object()]
    calm = SimpleNamespace(castle=object(), enemies_near_base=threats,
                           castle_under_attack=False)
    emergency = SimpleNamespace(castle=object(), enemies_near_base=threats,
                                castle_under_attack=True)
    goal = DefendBaseGoal()
    assert goal.score(emergency) > goal.score(calm) + 250
