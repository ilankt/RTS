import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from systems.pathfinding import CLEARANCE_BUFFER, Pathfinding
import systems.pathfinding as pathfinding_module


class FakeMap:
    def __init__(self, width=8, height=8, fill="grass"):
        self.width = width
        self.height = height
        self.grid = [[fill for _ in range(width)] for _ in range(height)]

    def world_to_grid(self, x, y):
        col = int(x // 64)
        row = int(y // 64)
        if col < 0 or row < 0 or col >= self.width or row >= self.height:
            return None
        return (col, row)

    def grid_to_world(self, col, row):
        return (col * 64, row * 64)


class FakeGame:
    def __init__(self, game_map):
        self.game_map = game_map
        self.buildings = []
        self.resources = []
        self.construction_sites = []
        self.units = []


class FakeObject:
    def __init__(self, name="object", x=0, y=0, radius=16, hp=100):
        self.name = name
        self.x = x
        self.y = y
        self.radius = radius
        self.hp = hp


class FakeResource(FakeObject):
    def __init__(self, name="wood", x=0, y=0, radius=16):
        super().__init__(name, x, y, radius, hp=0)
        self.amount_remaining = 100
        self.gatherers = []


class FakeUnit:
    def __init__(self, x=0, y=0, radius=8):
        self.name = "worker"
        self.x = x
        self.y = y
        self.radius = radius
        self.path = None
        self.path_index = 0
        self.path_target = None
        self.destination = None
        self.status = "idle"
        self.is_gathering = False
        self.gathering_target = None
        self.is_dropping_off = False
        self.drop_off_timer = 0
        self.drop_off_target = None
        self.current_target = None
        self.in_combat = False
        self.is_engaging = False
        self.is_building = False
        self.building_target = None
        self.has_los = False
        self.is_fallback_movement = False
        self.resource_amount = 0
        self.attack_range = 48


def make_pathfinder(game_map=None):
    game_map = game_map or FakeMap()
    game = FakeGame(game_map)
    return Pathfinding(game_map, game), game


def test_open_terrain_returns_direct_path():
    pathfinder, _ = make_pathfinder()

    result = pathfinder.find_result((40, 96), (320, 96), unit_radius=8)

    assert result.ok
    assert result.waypoints == [(320, 96)]
    assert result.final_point == (320, 96)


def test_water_barrier_returns_clean_failure():
    game_map = FakeMap(width=8, height=5)
    for row in range(game_map.height):
        game_map.grid[row][3] = "water"
    pathfinder, _ = make_pathfinder(game_map)

    result = pathfinder.find_result((80, 160), (420, 160), unit_radius=8)

    assert not result.ok
    assert result.failure_reason == "no_path"


def test_static_blocker_inflates_for_unit_radius():
    pathfinder, game = make_pathfinder()
    blocker = FakeObject("house", x=192, y=96, radius=32)
    game.buildings.append(blocker)
    pathfinder.mark_dirty()

    result = pathfinder.find_result((40, 96), (360, 96), unit_radius=8)

    assert result.ok
    assert not pathfinder.grid.segment_clear((40, 96), (360, 96), 8)
    for point in result.waypoints:
        distance = math.hypot(point[0] - blocker.x, point[1] - blocker.y)
        assert distance >= blocker.radius + 8 + CLEARANCE_BUFFER


def test_blocked_move_goal_resolves_to_reachable_point():
    pathfinder, game = make_pathfinder()
    blocker = FakeObject("house", x=192, y=160, radius=32)
    game.buildings.append(blocker)
    pathfinder.mark_dirty()

    result = pathfinder.find_result((64, 160), (192, 160), unit_radius=8)

    assert result.ok
    assert result.final_point != (192, 160)
    assert math.hypot(result.final_point[0] - blocker.x, result.final_point[1] - blocker.y) >= blocker.radius + 8


def test_unreachable_enclosed_goal_fails():
    game_map = FakeMap(width=7, height=7)
    for row in (2, 4):
        for col in range(2, 5):
            game_map.grid[row][col] = "water"
    for row in range(2, 5):
        for col in (2, 4):
            game_map.grid[row][col] = "water"
    pathfinder, _ = make_pathfinder(game_map)

    result = pathfinder.find_result((64, 224), (224, 224), unit_radius=4)

    assert not result.ok
    assert result.failure_reason == "no_path"


def test_mark_dirty_rebuilds_static_occupancy():
    pathfinder, game = make_pathfinder()
    start = (40, 96)
    goal = (360, 96)

    direct = pathfinder.find_result(start, goal, unit_radius=8)
    game.buildings.append(FakeObject("house", x=192, y=96, radius=40))
    pathfinder.mark_dirty()
    detour = pathfinder.find_result(start, goal, unit_radius=8)

    assert direct.ok
    assert direct.waypoints == [goal]
    assert detour.ok
    assert detour.waypoints != [goal]
    assert pathfinder.grid.revision == 1


def test_navigation_index_matches_reference_walkability_for_static_blockers():
    game_map = FakeMap(width=8, height=8)
    game_map.grid[3][3] = "water"
    pathfinder, game = make_pathfinder(game_map)
    game.buildings.append(FakeObject("house", x=160, y=96, radius=28))
    game.resources.append(FakeResource("wood", x=288, y=96, radius=20))
    game.construction_sites.append(FakeObject("farm_construction", x=224, y=224, radius=32))
    pathfinder.mark_dirty()

    points = [
        (64, 64),
        (160, 96),
        (190, 96),
        (288, 96),
        (224, 224),
        (224, 192),
        (224, 224),
        (224, 224 + 64),
    ]

    for point in points:
        assert pathfinder.grid.point_walkable(point, 8) == reference_walkable(game, point, 8)


def test_path_cache_invalidates_on_mark_dirty():
    pathfinder, game = make_pathfinder()

    assert pathfinder.find_result((40, 96), (320, 96), unit_radius=8).ok
    assert len(pathfinder._path_cache) == 1

    game.buildings.append(FakeObject("house", x=192, y=96, radius=32))
    pathfinder.mark_dirty()

    assert len(pathfinder._path_cache) == 0
    assert pathfinder.grid.revision == 1


def test_astar_expansion_cap_returns_safe_failure(monkeypatch):
    pathfinder, game = make_pathfinder(FakeMap(width=16, height=16))
    game.buildings.append(FakeObject("house", x=160, y=96, radius=28))
    pathfinder.mark_dirty()
    monkeypatch.setattr(pathfinding_module, "PATHFINDING_MAX_EXPANSIONS", 1)

    result = pathfinder.find_result((40, 96), (640, 96), unit_radius=8)

    assert not result.ok
    assert result.failure_reason == "too_expensive"


def test_issue_interact_build_sets_contact_target_metadata():
    pathfinder, game = make_pathfinder()
    unit = FakeUnit(x=64, y=160)
    site = FakeObject("farm_construction", x=224, y=160, radius=32)
    game.construction_sites.append(site)
    pathfinder.mark_dirty()

    assert pathfinder.issue_interact(unit, site, "build") is True

    assert unit.status == "run"
    assert unit.building_target is site
    assert unit.path_target_object is site
    assert unit.path_target_mode == "build"
    assert math.hypot(unit.path_target[0] - site.x, unit.path_target[1] - site.y) >= site.radius + unit.radius


def test_issue_interact_gather_uses_resource_ring_not_center():
    pathfinder, game = make_pathfinder()
    unit = FakeUnit(x=64, y=160)
    resource = FakeResource(x=224, y=160, radius=16)
    game.resources.append(resource)
    pathfinder.mark_dirty()

    assert pathfinder.issue_interact(unit, resource, "gather") is True

    assert unit.gathering_target is resource
    assert unit in resource.gatherers
    assert unit.path_target != (resource.x, resource.y)
    assert math.hypot(unit.path_target[0] - resource.x, unit.path_target[1] - resource.y) > resource.radius


def test_issue_interact_gather_honors_reachable_preferred_slot():
    pathfinder, game = make_pathfinder()
    unit = FakeUnit(x=64, y=160)
    resource = FakeResource(x=224, y=160, radius=16)
    preferred = (224, 224)
    game.resources.append(resource)
    pathfinder.mark_dirty()

    assert pathfinder.issue_interact(unit, resource, "gather", preferred_point=preferred) is True

    assert unit.gathering_target is resource
    assert unit.path_target == preferred


def test_navigation_index_matches_reference_walkability_dense_sweep():
    """Safety net for nav-grid changes: sweep the whole map at several radii and
    require exact agreement with the brute-force reference, including after
    mutations (depleted resource, destroyed building) + mark_dirty."""
    game_map = FakeMap(width=10, height=10)
    for row in range(2, 5):
        game_map.grid[row][6] = "water"
    game_map.grid[7][2] = "lava"
    pathfinder, game = make_pathfinder(game_map)

    house = FakeObject("house", x=160, y=96, radius=28)
    tree = FakeResource("wood", x=288, y=352, radius=20)
    gold = FakeResource("gold", x=480, y=160, radius=24)
    site = FakeObject("farm_construction", x=224, y=480, radius=32)
    game.buildings.append(house)
    game.resources.extend([tree, gold])
    game.construction_sites.append(site)
    pathfinder.mark_dirty()

    def sweep():
        for radius in (4, 8, 12):
            for y in range(16, game_map.height * 64, 48):
                for x in range(16, game_map.width * 64, 48):
                    point = (x, y)
                    assert pathfinder.grid.point_walkable(point, radius) == reference_walkable(
                        game, point, radius
                    ), f"mismatch at {point} radius {radius}"

    sweep()

    # Deplete a resource and destroy a building; the nav index must track it.
    tree.amount_remaining = 0
    house.hp = 0
    pathfinder.mark_dirty()
    sweep()


def test_incremental_blocker_updates_match_reference():
    """The incremental add/remove path must produce exactly the same walkability
    as a full rebuild, including cache invalidation in the changed region."""
    game_map = FakeMap(width=10, height=10)
    for row in range(2, 5):
        game_map.grid[row][6] = "water"
    pathfinder, game = make_pathfinder(game_map)

    def sweep():
        for radius in (4, 8, 12):
            for y in range(16, game_map.height * 64, 48):
                for x in range(16, game_map.width * 64, 48):
                    point = (x, y)
                    assert pathfinder.grid.point_walkable(point, radius) == reference_walkable(
                        game, point, radius
                    ), f"mismatch at {point} radius {radius}"

    def sweep_cells():
        # cell_walkable goes through the per-cell cache — exercise it too
        for radius in (8,):
            for cell_y in range(0, 30):
                for cell_x in range(0, 30):
                    cell = (cell_x, cell_y)
                    expected = reference_walkable(game, pathfinder.grid.cell_to_world(cell), radius)
                    assert pathfinder.grid.cell_walkable(cell, radius) == expected, f"cell {cell}"

    # Warm caches on the empty map
    sweep_cells()

    # Incrementally add blockers of each type (no mark_dirty)
    house = FakeObject("house", x=160, y=96, radius=28)
    tree = FakeResource("wood", x=288, y=352, radius=20)
    site = FakeObject("farm_construction", x=224, y=480, radius=32)
    game.buildings.append(house)
    pathfinder.notify_blocker_added(house)
    game.resources.append(tree)
    pathfinder.notify_blocker_added(tree)
    game.construction_sites.append(site)
    pathfinder.notify_blocker_added(site)

    sweep()
    sweep_cells()

    # Cache a path that crosses the house, then remove the house incrementally
    result = pathfinder.find_result((40, 96), (360, 96), unit_radius=8)
    assert result.ok and result.waypoints != [(360, 96)]

    game.buildings.remove(house)
    house.hp = 0
    pathfinder.notify_blocker_removed(house)
    tree.amount_remaining = 0
    game.resources.remove(tree)
    pathfinder.notify_blocker_removed(tree)

    sweep()
    sweep_cells()

    # The stale detour path must have been invalidated: a fresh request now
    # goes straight through where the house used to be.
    result = pathfinder.find_result((40, 96), (360, 96), unit_radius=8)
    assert result.ok
    assert result.waypoints == [(360, 96)]


def test_incremental_add_invalidates_cached_straight_path():
    pathfinder, game = make_pathfinder()
    start, goal = (40, 96), (360, 96)

    direct = pathfinder.find_result(start, goal, unit_radius=8)
    assert direct.ok and direct.waypoints == [goal]

    blocker = FakeObject("house", x=192, y=96, radius=32)
    game.buildings.append(blocker)
    pathfinder.notify_blocker_added(blocker)

    detour = pathfinder.find_result(start, goal, unit_radius=8)
    assert detour.ok
    assert detour.waypoints != [goal]
    for point in detour.waypoints:
        assert math.hypot(point[0] - blocker.x, point[1] - blocker.y) >= blocker.radius + 8 + CLEARANCE_BUFFER


def reference_astar_cost(pathfinder, start_cell, goal_cell, radius):
    """Plain A* over the exact same neighbor rule (pathfinder._neighbors);
    optimal-cost oracle for the JPS implementation."""
    import heapq

    open_heap = [(pathfinder._heuristic(start_cell, goal_cell), 0, start_cell)]
    g = {start_cell: 0.0}
    closed = set()
    counter = 0
    while open_heap:
        _, _, current = heapq.heappop(open_heap)
        if current == goal_cell:
            return g[current]
        if current in closed:
            continue
        closed.add(current)
        for neighbor, cost in pathfinder._neighbors(current, radius):
            tentative = g[current] + cost
            if tentative < g.get(neighbor, float("inf")):
                g[neighbor] = tentative
                counter += 1
                heapq.heappush(open_heap, (tentative + pathfinder._heuristic(neighbor, goal_cell), counter, neighbor))
    return None


def jps_path_cost(pathfinder, cells):
    cost = 0.0
    for a, b in zip(cells, cells[1:]):
        cost += pathfinder._heuristic(a, b)
    return cost


def test_jps_matches_plain_astar_cost_on_random_maps():
    import random

    rng = random.Random(4242)
    radius = 8
    trials_run = 0
    for trial in range(30):
        game_map = FakeMap(width=12, height=12)
        for _ in range(rng.randint(4, 14)):
            game_map.grid[rng.randrange(12)][rng.randrange(12)] = "water"
        pathfinder, game = make_pathfinder(game_map)
        for _ in range(rng.randint(0, 4)):
            game.buildings.append(
                FakeObject("house", x=rng.uniform(64, 700), y=rng.uniform(64, 700), radius=rng.choice((20, 28, 36)))
            )
        pathfinder.mark_dirty()
        # Give each trial its own frame so A* budgets never accumulate.
        game.frame_counter = trial + 1

        for _ in range(4):
            start_cell = pathfinder.grid.nearest_walkable_cell((rng.uniform(30, 730), rng.uniform(30, 730)), radius)
            goal_cell = pathfinder.grid.nearest_walkable_cell((rng.uniform(30, 730), rng.uniform(30, 730)), radius)
            if not start_cell or not goal_cell:
                continue
            expected = reference_astar_cost(pathfinder, start_cell, goal_cell, radius)
            actual = pathfinder._astar(start_cell, goal_cell, radius)
            assert actual != "too_expensive"
            if expected is None:
                assert actual is None, f"JPS found a path where A* found none: {start_cell}->{goal_cell}"
            else:
                assert actual is not None, f"JPS found no path where A* found one: {start_cell}->{goal_cell}"
                assert actual[0] == start_cell and actual[-1] == goal_cell
                assert abs(jps_path_cost(pathfinder, actual) - expected) < 1e-6, (
                    f"cost mismatch {start_cell}->{goal_cell}: jps={jps_path_cost(pathfinder, actual)} astar={expected}"
                )
                # Every jump-point hop must be a straight or diagonal ray.
                for a, b in zip(actual, actual[1:]):
                    dx, dy = b[0] - a[0], b[1] - a[1]
                    assert dx == 0 or dy == 0 or abs(dx) == abs(dy), f"non-ray hop {a}->{b}"
            trials_run += 1
    assert trials_run > 60  # sanity: the comparison actually exercised many pairs


def reference_terrain_walkable(game_map, x, y, cell_size=20):
    """Independent implementation of the conservative per-nav-cell terrain rule:
    a probe point is walkable iff every terrain sample (center + 4 inset corners)
    of its 20px nav cell is on walkable terrain."""
    if x < 0 or y < 0:
        return False
    x0 = (x // cell_size) * cell_size
    y0 = (y // cell_size) * cell_size
    inset = 0.5
    for sample_x, sample_y in (
        (x0 + cell_size * 0.5, y0 + cell_size * 0.5),
        (x0 + inset, y0 + inset),
        (x0 + cell_size - inset, y0 + inset),
        (x0 + inset, y0 + cell_size - inset),
        (x0 + cell_size - inset, y0 + cell_size - inset),
    ):
        grid_pos = game_map.world_to_grid(sample_x, sample_y)
        if grid_pos is None:
            return False
        col, row = grid_pos
        if game_map.grid[row][col] in {"water", "lava"}:
            return False
    return True


def reference_walkable(game, point, unit_radius):
    x, y = point
    if x < 0 or y < 0 or x > game.game_map.width * 64 or y > game.game_map.height * 64:
        return False

    diag = unit_radius * 0.7
    for check_x, check_y in (
        (x, y),
        (x + unit_radius, y),
        (x - unit_radius, y),
        (x, y + unit_radius),
        (x, y - unit_radius),
        (x + diag, y + diag),
        (x - diag, y + diag),
        (x + diag, y - diag),
        (x - diag, y - diag),
    ):
        if not reference_terrain_walkable(game.game_map, check_x, check_y):
            return False

    blockers = game.buildings + game.resources + game.construction_sites
    for obj in blockers:
        if getattr(obj, "amount_remaining", None) is not None and obj.amount_remaining <= 0:
            continue
        if getattr(obj, "hp", 1) <= 0 and getattr(obj, "amount_remaining", None) is None:
            continue
        if math.hypot(obj.x - x, obj.y - y) < obj.radius + unit_radius + CLEARANCE_BUFFER:
            return False
    return True
