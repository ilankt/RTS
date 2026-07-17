"""§8.13.3 regression tests: units near water must slide along shorelines,
get rescued when wedged, and never permanently stall.

Phase 3's gate passed on benchmarks that never walked a shoreline — the
steering/mover/watchdog probe asymmetry (center-point tests vs the mover's
full-radius ring) lived exactly there. These tests physically walk units
along and into water with the REAL collision + movement + pathfinding stack.
"""
import math
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from systems.collision_system import CollisionSystem
from systems.movement_system import MovementSystem
from systems.pathfinding import Pathfinding
from systems.production_manager import ProductionManager
from systems.unit_watchdog import UnitWatchdog


class LakeMap:
    """20x10 tiles (64 px squares, 1280x640 world) with a central lake:
    water rows 3-6 (y 192-448), cols 6-13 (x 384-896)."""

    width = 20
    height = 10

    def __init__(self):
        self.grid = [["grass" for _ in range(self.width)] for _ in range(self.height)]
        for row in range(3, 7):
            for col in range(6, 14):
                self.grid[row][col] = "water"

    def world_to_grid(self, x, y):
        col = int(x // 64)
        row = int(y // 64)
        if col < 0 or row < 0 or col >= self.width or row >= self.height:
            return None
        return (col, row)

    def grid_to_world(self, col, row):
        return (col * 64, row * 64)


class FakeUnit:
    def __init__(self, x, y):
        self.name = "warrior"
        self.player = None
        self.x = x
        self.y = y
        self.hp = 100
        self.radius = 8
        self.movement_speed = 120
        self.path = None
        self.path_index = 0
        self.path_target = None
        self.destination = None
        self.status = "idle"
        self.is_gathering = False
        self.gathering_target = None
        self.resource_type = None
        self.resource_amount = 0
        self.drop_off_target = None
        self.is_dropping_off = False
        self.drop_off_timer = 0.0
        self.previous_gathering_target = None
        self.is_building = False
        self.building_target = None
        self.current_target = None
        self.in_combat = False
        self.is_engaging = False
        self.has_los = False
        self.is_fallback_movement = False
        self.collision = True

    def update_animation(self, delta_time=None):
        pass

    def get_target_tolerance(self, target_type="movement"):
        return 8


class FakeGame:
    def __init__(self):
        self.game_map = LakeMap()
        self.units = []
        self.buildings = []
        self.resources = []
        self.construction_sites = []
        self.frame_counter = 0
        self.pathfinder = Pathfinding(self.game_map, self)
        self.collision_system = CollisionSystem(self)
        self.movement_system = MovementSystem(self)

    def _check_unit_collision_and_adjust(self, unit, new_pos, direction):
        return self.collision_system.check_unit_collision_and_adjust(unit, new_pos, direction)

    def _handle_blocked_unit(self, unit):
        return self.collision_system.handle_blocked_unit(unit)


def tick(game, count=1, delta_time=0.1):
    for _ in range(count):
        game.frame_counter += 1
        game.pathfinder.process_pending()
        game.collision_system.begin_frame()
        for unit in list(game.units):
            game.movement_system.update_unit_movement(unit, delta_time)
        game.collision_system.separate_overlapping_units()


def body_in_water(game, unit):
    return game.collision_system._is_on_unwalkable_terrain(unit.x, unit.y, unit.radius)


def test_lakeshore_crowd_arrives_without_stalling():
    """A 20-unit crowd ordered across the lake's latitude routes around it
    and every single unit arrives — no permanent stalls, nobody left wedged
    at the shore. (The old steering/mover probe asymmetry livelocked crowds
    exactly here: lone units were fine, groups broke.)"""
    game = FakeGame()
    for i in range(20):
        unit = FakeUnit(80 + (i % 4) * 24, 250 + (i // 4) * 30)
        game.units.append(unit)
    game.pathfinder.mark_dirty()

    goal = (1180, 320)
    for unit in game.units:
        assert game.pathfinder.issue_move(unit, goal)

    tick(game, count=900, delta_time=0.1)

    stragglers = [
        (round(u.x), round(u.y)) for u in game.units
        if math.hypot(u.x - goal[0], u.y - goal[1]) > 160
    ]
    assert not stragglers, f"units never arrived (stalled): {stragglers}"
    wedged = [(round(u.x), round(u.y)) for u in game.units if body_in_water(game, u)]
    assert not wedged, f"units ended overlapping water: {wedged}"


def test_step_into_shore_slides_along_it():
    """§8.13.3 shoreline sliding: a step with a seaward component keeps its
    along-shore component instead of stopping dead (the old atomic reject
    killed both axes)."""
    import pygame

    game = FakeGame()
    unit = FakeUnit(600, 170)  # just north of the lake's north shore
    game.units.append(unit)
    game.pathfinder.mark_dirty()
    assert not body_in_water(game, unit)

    # A south-east step whose full position is terrain-rejected
    blocked_step = pygame.math.Vector2(601.5, 173.0)
    assert game.collision_system._is_on_unwalkable_terrain(
        blocked_step.x, blocked_step.y, unit.radius)

    game.movement_system._check_terrain_and_update(unit, blocked_step)

    assert unit.x > 600, "along-shore (east) component must survive"
    assert unit.y == 170, "seaward (south) component must be dropped"
    assert not body_in_water(game, unit)


def test_wedged_unit_is_rescued_not_let_deeper():
    """§8.13.3 escape hatch: a unit already overlapping water (bad spawn,
    legacy push) used to be allowed to move ANYWHERE — including deeper in.
    Now it snaps to the nearest clear spot and stays on land."""
    game = FakeGame()
    unit = FakeUnit(600, 174)  # center on land, body overlapping the shore band
    game.units.append(unit)
    game.pathfinder.mark_dirty()
    assert body_in_water(game, unit), "test setup must start wedged"

    unit.destination = (600, 300)  # direct order into the lake (no planner)
    tick(game, count=120, delta_time=0.1)

    assert not body_in_water(game, unit), "unit must be rescued onto clear ground"
    assert unit.y < 192, f"unit walked into the lake (y={unit.y:.0f})"


def test_watchdog_is_safe_matches_the_movement_gate():
    """§8.13.3 watchdog: _is_safe must test terrain at FULL radius. The old
    center-point probe judged a shore-wedged unit 'already safe', returned
    its own position, and never nudged it — permanent idle at the shore."""
    game = FakeGame()
    unit = FakeUnit(600, 174)  # wedged: center-cell walkable, body in water
    game.units.append(unit)
    game.pathfinder.mark_dirty()
    watchdog = UnitWatchdog(game)

    assert not watchdog._is_safe(unit.x, unit.y, unit.radius), \
        "wedged position judged safe: watchdog can never recover it"

    safe = watchdog._find_nearby_safe_position(unit)
    assert safe is not None
    assert math.hypot(safe[0] - unit.x, safe[1] - unit.y) > 1, \
        "watchdog returned the wedged position itself (no nudge)"
    assert not game.collision_system._is_on_unwalkable_terrain(
        safe[0], safe[1], unit.radius)


def test_spawn_position_rejects_shoreline_at_full_radius():
    """§8.13.3: production spawn probing must use the spawn radius — the old
    center-point probe let a barracks near water spawn units body-into the
    shoreline (creating exactly the wedge the other fixes clean up)."""
    game = FakeGame()
    game.pathfinder.mark_dirty()
    manager = SimpleNamespace(game=game)

    shoreline = ProductionManager._is_valid_spawn_position(manager, 600, 174)
    assert not shoreline, "shoreline spawn accepted by a center-only probe"

    clear = ProductionManager._is_valid_spawn_position(manager, 600, 100)
    assert clear, "clearly-walkable spawn rejected"
