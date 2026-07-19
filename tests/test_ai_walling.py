"""AI walling (§8.10): wall-line planning, incremental placement, gate management."""
import math
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from systems.ai.building_placer import BuildingPlacer
from systems.ai.utility.context import GoalContext
from systems.ai.utility.goals.military import BuildWallGoal


class FakeMap:
    """Large all-grass map so wall slots are always on valid terrain."""
    width = 60
    height = 60

    def __init__(self):
        self.grid = [["grass"] * self.width for _ in range(self.height)]

    def world_to_grid(self, x, y):
        col, row = int(x // 64), int(y // 64)
        if col < 0 or row < 0 or col >= self.width or row >= self.height:
            return None
        return (col, row)


def make_template():
    return SimpleNamespace(size=[1, 1])


def make_game(placer_holder=True):
    game = SimpleNamespace(
        game_map=FakeMap(),
        game_data={"buildings": {"wooden_wall": make_template(),
                                 "gate": make_template(),
                                 "wall": make_template()}},
        collision_system=None,
    )
    placer = BuildingPlacer(game)
    if placer_holder:
        game.ai_system = SimpleNamespace(building_placer=placer)
    return game, placer


def make_ctx(game, personality="turtle", workers=6, wood=500):
    player = SimpleNamespace(name="AI 1", ai_personality=personality,
                             resources={"wood": wood, "gold": 0, "food": 0})
    ctx = GoalContext(game=game, player=player)
    ctx.castle = SimpleNamespace(name="castle", x=1000.0, y=1000.0, hp=2500)
    ctx.workers = [SimpleNamespace(name="worker")] * workers
    ctx.enemy_buildings = [SimpleNamespace(name="castle", x=3000.0, y=1000.0, hp=2500)]
    ctx.resources = dict(player.resources)
    ctx.cost_data = {"wooden_wall": {"wood": 40}, "gate": {"wood": 80}}
    return ctx


def test_wall_plan_crosses_threat_bearing_with_middle_gate():
    game, placer = make_game()
    ctx = make_ctx(game)
    plan = placer.plan_wall_line(ctx, 11)

    assert len(plan) == 11
    # Enemy is due east: the line stands east of the castle, running north-south
    for piece, x, y in plan:
        assert abs(x - (1000 + placer.WALL_DISTANCE)) < 1e-6
    ys = [y for _, _, y in plan]
    assert max(ys) - min(ys) == (11 - 1) * placer.WALL_SPACING
    # Exactly one gate, at the center slot (on the bearing line)
    gates = [(piece, x, y) for piece, x, y in plan if piece == "gate"]
    assert len(gates) == 1
    assert abs(gates[0][2] - 1000) < 1e-6
    assert all(piece == "wooden_wall" for piece, _, _ in plan if piece != "gate")


def test_next_wall_piece_fills_line_incrementally():
    game, placer = make_game()
    ctx = make_ctx(game)

    piece, pos = placer.next_wall_piece(ctx, 11)
    assert piece in ("wooden_wall", "gate")

    # Occupy the first three planned slots and expect the fourth
    plan = placer.plan_wall_line(ctx, 11)
    ctx.buildings["wooden_wall"] = [SimpleNamespace(name="wooden_wall", x=x, y=y)
                                    for _, x, y in plan[:3]]
    piece, pos = placer.next_wall_piece(ctx, 11)
    assert (abs(pos[0] - plan[3][1]) < 1e-6 and abs(pos[1] - plan[3][2]) < 1e-6)

    # Fully built line -> nothing left to place
    ctx.buildings["wooden_wall"] = [SimpleNamespace(name="wooden_wall", x=x, y=y)
                                    for _, x, y in plan]
    assert placer.next_wall_piece(ctx, 11) is None


def test_wall_goal_only_for_walling_personalities():
    game, _ = make_game()
    goal = BuildWallGoal()

    assert goal.score(make_ctx(game, personality="rusher")) == 0
    assert goal.score(make_ctx(game, personality="boomer")) == 0
    assert goal.score(make_ctx(game, personality="balanced")) == 0

    turtle_ctx = make_ctx(game, personality="turtle")
    assert goal.score(turtle_ctx) > 0

    # Gated on economy size and affordability
    assert goal.score(make_ctx(game, workers=4)) == 0
    assert goal.score(make_ctx(game, wood=10)) == 0

    # One segment at a time: an in-flight wall site zeroes the score
    busy = make_ctx(game)
    busy.site_types.add("wooden_wall")
    assert goal.score(busy) == 0


def test_gate_management_toggles_with_threat():
    from entities.building import Building
    from systems.ai.military_brain import MilitaryBrain

    class RecordingPathfinder:
        def __init__(self):
            self.added, self.removed = [], []

        def notify_blocker_added(self, obj):
            self.added.append(obj)

        def notify_blocker_removed(self, obj):
            self.removed.append(obj)

    game, _ = make_game()
    game.pathfinder = RecordingPathfinder()
    brain = MilitaryBrain(game)

    gate = Building(name="gate", size=[1, 1], hp=1200, sprite=None,
                    build_duration=6, x=1360, y=1000, radius=32,
                    armor_type="fortified")
    assert gate.is_gate and not gate.passable  # gates spawn closed

    ctx = make_ctx(game)
    ctx.buildings["gate"] = [gate]

    # No threat -> brain opens the gate for the economy
    brain._manage_gates(ctx)
    assert gate.passable
    assert game.pathfinder.removed == [gate]

    # Enemy strength near the gate -> brain closes it
    cell = ctx.threat_cell_size
    ctx.threat_cells[(int(gate.x // cell), int(gate.y // cell))] = 500.0
    brain._manage_gates(ctx)
    assert not gate.passable
    assert game.pathfinder.added == [gate]

    # Threat clears -> reopens
    ctx.threat_cells.clear()
    brain._manage_gates(ctx)
    assert gate.passable
