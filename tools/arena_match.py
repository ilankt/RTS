"""Arena duels for unit balance (§8.15 balance re-baseline).

Spawns two equal groups of units on probed open ground in a fresh headless
Game (AI brains disabled — the real combat/movement/collision systems do the
fighting) and reports surviving VALUE per side. This isolates unit stats
(damage, HP, attack speed, armor, counters) from AI-behavior confounds — the
matrix battery answers "who wins games", the arena answers "is the spearman's
damage right".

Two matchup tables:
  - equal HEADCOUNT (N vs N) — raw per-unit strength
  - equal COST (budget worth of A vs budget worth of B) — what a player
    should actually spend on. Cost is gold-equivalent: gold 1.0, wood 0.5,
    food 0.5 (wood gathers 2x gold's rate; food is farm-produced).
Plus ram-vs-building TTK probes and a healer-attachment A/B.

Each duel repeats over --seeds and averages. Usage:
  python tools/arena_match.py --output tools/arena_2026-07-19.json
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.chdir(ROOT)

CORE_UNITS = ("warrior", "archer", "spearman", "cavalry")
COST_WEIGHTS = {"gold": 1.0, "wood": 0.5, "food": 0.5}
BUDGET = 900.0          # gold-equivalent per side in the equal-cost table
EQUAL_COUNT = 8         # per side in the equal-count table
DUEL_TIMEOUT_S = 240.0
# Front lines must spawn inside CombatSystem.AGGRO_RANGE (200) or idle
# acquisition never fires and both groups stand at parade rest forever
# (measured: full-HP 240s timeout at 260px).
SEPARATION = 170.0


def unit_cost_ge(unit_data):
    return sum(COST_WEIGHTS.get(res, 1.0) * amt
               for res, amt in unit_data.get("costs", {}).items())


def load_units_json():
    with open("data/units.json", encoding="utf-8") as fh:
        return {u["name"]: u for u in json.load(fh)}


def fresh_game(seed):
    import random
    random.seed(seed)
    from core.game import Game

    game = Game(mode="ai_spectator", player_count=2, map_size=(50, 50))
    game.game_speed = 5.0
    # Silence the brains — the arena owns every unit. Real combat systems
    # (acquisition, approach, counters, projectiles, healers) stay live.
    game.ai_system.update = lambda *a, **k: None
    return game


def find_arena_center(game):
    """Open walkable rect away from castles and the healing fountain."""
    from core.config import BLOCKED_TERRAIN

    game_map = game.game_map
    fountains = [(f.x, f.y) for f in getattr(game, "fountains", ())]
    castles = [(b.x, b.y) for b in game.buildings]

    best, best_score = None, -1.0
    for r in range(4, game_map.height - 4, 2):
        for c in range(4, game_map.width - 4, 2):
            if any(game_map.grid[rr][cc] in BLOCKED_TERRAIN
                   for rr in range(r - 3, r + 4)
                   for cc in range(c - 3, c + 4)):
                continue
            x, y = game_map.grid_to_world(c, r)
            # §8.9 fountain heals in a 220px radius — stay well outside it
            fountain_clear = min((math.hypot(x - ox, y - oy) for ox, oy in fountains),
                                 default=1e9)
            castle_clear = min((math.hypot(x - ox, y - oy) for ox, oy in castles),
                               default=1e9)
            if fountain_clear < 380 or castle_clear < 300:
                continue
            statics = game.collision_system.query_nearby_static(
                x, y, 200, include_construction_sites=True, include_resources=True)
            if statics:
                continue
            score = min(fountain_clear, castle_clear)
            if score > best_score:
                best, best_score = (x, y), score
    if best is None:
        raise RuntimeError("no open arena ground on this seed")
    return best


def spawn_group(game, player, unit_name, count, cx, cy, facing):
    """Cluster `count` units of a type around (cx, cy) in a grid."""
    from entities.unit import Unit
    from core.config import TILE_WIDTH

    unit_data = load_units_json()[unit_name]
    spawned = []
    cols = max(1, int(math.ceil(math.sqrt(count))))
    spacing = 34.0
    for i in range(count):
        row, col = divmod(i, cols)
        x = cx + facing * (row * spacing)          # ranks extend away from the enemy
        y = cy + (col - cols / 2.0) * spacing
        unit = Unit(
            name=unit_name,
            size=unit_data["size"],
            hp=unit_data["hp"],
            movement_speed=unit_data["movement_speed"],
            attack=unit_data.get("attack"),
            animations={},
            x=x, y=y,
            radius=unit_data["size"][0] * TILE_WIDTH / 8,
            player=player,
            can_build=unit_data.get("can_build", False),
            can_attack=unit_data.get("can_attack", False),
            min_damage=unit_data.get("min_damage", 0),
            max_damage=unit_data.get("max_damage", 0),
            attack_type=unit_data.get("attack_type", "slash"),
            armor_type=unit_data.get("armor_type", "light"),
            armor_value=unit_data.get("armor_value", 0),
            attack_speed=unit_data.get("attack_speed", 1.0),
            attack_range=unit_data.get("attack_range", 32),
            strong_against=unit_data.get("strong_against", []),
            weak_against=unit_data.get("weak_against", []),
            building_only_attack=unit_data.get("building_only_attack", False),
        )
        unit.max_hp = unit_data["hp"]
        game.units.append(unit)
        spawned.append(unit)
    return spawned


def spawn_building(game, player, name, x, y):
    """Stand up one enemy building (ram target) with nav/collision wired."""
    from entities.building import Building

    template = game.game_data["buildings"][name]
    building = Building(
        name=template.name, size=template.size, hp=template.hp,
        sprite=None, build_duration=template.build_duration,
        x=x, y=y, radius=template.radius, player=player,
        armor_type=getattr(template, "armor_type", "fortified"),
        armor_value=getattr(template, "armor_value", 0),
        can_attack=getattr(template, "can_attack", False),
        min_damage=getattr(template, "min_damage", 0),
        max_damage=getattr(template, "max_damage", 0),
        attack_type=getattr(template, "attack_type", "pierce"),
        attack_speed=getattr(template, "attack_speed", 1.0),
        attack_range=getattr(template, "attack_range", 0),
    )
    game.buildings.append(building)
    game.pathfinder.notify_blocker_added(building)
    game.collision_system.invalidate_static_index()
    return building


def surviving_value(units, unit_ge):
    return sum(unit_ge * max(0.0, u.hp) / max(1.0, getattr(u, "max_hp", u.hp) or 1.0)
               for u in units if u.hp > 0)


def run_duel(seed, side_a, side_b, extra=None):
    """side = (unit_name, count). Returns per-side value survival."""
    game = fresh_game(seed)
    units_json = load_units_json()
    cx, cy = find_arena_center(game)
    pa, pb = game.players[0], game.players[1]

    a_name, a_count = side_a
    b_name, b_count = side_b
    group_a = spawn_group(game, pa, a_name, a_count, cx - SEPARATION / 2, cy, facing=-1)
    group_b = spawn_group(game, pb, b_name, b_count, cx + SEPARATION / 2, cy, facing=+1)
    if extra == "healer_a":  # healer A/B rider: 2 healers ride with side A
        group_a += spawn_group(game, pa, "healer", 2, cx - SEPARATION / 2 - 40, cy, facing=-1)

    # Attack-move both armies at each other (§8.14) — the real "army attacks"
    # order. Without it, back spawn ranks sit outside the 200px idle-aggro
    # radius and archer duels stall into 240s standoffs (measured); healers
    # never follow their line and heal 0.
    for unit, goal in [(u, (cx + SEPARATION / 2, cy)) for u in group_a] + \
                      [(u, (cx - SEPARATION / 2, cy)) for u in group_b]:
        if unit.name == "healer":
            goal = (cx - 60, cy)   # trail just behind A's front, in heal range
        elif unit.can_attack_flag:
            unit.attack_move_target = goal
        game.pathfinder.issue_move(unit, goal)

    dt = 1 / 60
    sim_per_frame = dt * game.game_speed
    frames = int(DUEL_TIMEOUT_S / sim_per_frame)
    sim_t = 0.0
    total_hp = sum(u.hp for u in group_a + group_b)
    for _ in range(frames):
        game.update(delta_time_override=dt)
        sim_t += sim_per_frame
        if sim_t > 40.0 and sum(u.hp for u in group_a + group_b) >= total_hp:
            raise RuntimeError(f"no contact after 40s: {a_name} vs {b_name}")
        a_alive = any(u.hp > 0 and u.can_attack_flag for u in group_a)
        b_alive = any(u.hp > 0 and u.can_attack_flag for u in group_b)
        if not a_alive or not b_alive:
            break

    ge_a, ge_b = unit_cost_ge(units_json[a_name]), unit_cost_ge(units_json[b_name])
    cost_a = ge_a * a_count + (2 * unit_cost_ge(units_json["healer"]) if extra == "healer_a" else 0)
    cost_b = ge_b * b_count
    healer_units = [u for u in group_a if u.name == "healer"]
    fighters_a = [u for u in group_a if u.name == a_name]
    return {
        "a_survive_value": round(surviving_value(fighters_a, ge_a)
                                 + surviving_value(healer_units, unit_cost_ge(units_json["healer"])), 1),
        "b_survive_value": round(surviving_value(group_b, ge_b), 1),
        "a_cost": round(cost_a, 1), "b_cost": round(cost_b, 1),
        "a_alive": sum(1 for u in group_a if u.hp > 0),
        "b_alive": sum(1 for u in group_b if u.hp > 0),
        "sim_s": round(sim_t, 1),
        "healing_done": round(sum(game.stats_healing.values()), 1),
    }


def run_ram_probe(seed, escort_warriors, target_building):
    """Rams (+escort) vs one enemy building: time to kill, ram losses."""
    game = fresh_game(seed)
    cx, cy = find_arena_center(game)
    pa, pb = game.players[0], game.players[1]

    building = spawn_building(game, pb, target_building, cx + 200, cy)
    rams = spawn_group(game, pa, "ram", 2, cx - 200, cy, facing=-1)
    escorts = (spawn_group(game, pa, "warrior", escort_warriors, cx - 240, cy, facing=-1)
               if escort_warriors else [])
    for ram in rams:
        ram.current_target = building
        ram.is_engaging = True
    for esc in escorts:
        game.pathfinder.issue_move(esc, (cx + 120, cy))

    dt = 1 / 60
    sim_per_frame = dt * game.game_speed
    sim_t = 0.0
    for _ in range(int(DUEL_TIMEOUT_S / sim_per_frame)):
        game.update(delta_time_override=dt)
        sim_t += sim_per_frame
        if building.hp <= 0 or all(r.hp <= 0 for r in rams):
            break
    return {
        "target": target_building, "escorts": escort_warriors,
        "killed": building.hp <= 0,
        "time_s": round(sim_t, 1),
        "rams_lost": sum(1 for r in rams if r.hp <= 0),
        "escorts_lost": sum(1 for e in escorts if e.hp <= 0),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", required=True)
    parser.add_argument("--seeds", type=str, default="11,22,33")
    args = parser.parse_args()
    seeds = [int(s) for s in args.seeds.split(",")]
    units_json = load_units_json()

    results = {"equal_count": {}, "equal_cost": {}, "ram_probes": [], "healer_ab": {}}

    pairs = list(itertools.combinations(CORE_UNITS, 2)) + [("warrior", "warrior")]
    for a, b in pairs:
        # equal headcount
        runs = [run_duel(s, (a, EQUAL_COUNT), (b, EQUAL_COUNT)) for s in seeds]
        results["equal_count"][f"{a}_vs_{b}"] = runs
        print(f"count  {a:9s} vs {b:9s}: "
              f"A {sum(r['a_survive_value'] for r in runs)/len(runs):7.1f}  "
              f"B {sum(r['b_survive_value'] for r in runs)/len(runs):7.1f}", flush=True)
        # equal cost
        ca = max(1, round(BUDGET / unit_cost_ge(units_json[a])))
        cb = max(1, round(BUDGET / unit_cost_ge(units_json[b])))
        runs = [run_duel(s, (a, ca), (b, cb)) for s in seeds]
        results["equal_cost"][f"{a}{ca}_vs_{b}{cb}"] = runs
        print(f"cost   {a}x{ca:2d} vs {b}x{cb:2d}: "
              f"A {sum(r['a_survive_value'] for r in runs)/len(runs):7.1f}  "
              f"B {sum(r['b_survive_value'] for r in runs)/len(runs):7.1f}", flush=True)

    for target in ("watchtower", "castle"):
        for escorts in (0, 3):
            probes = [run_ram_probe(s, escorts, target) for s in seeds[:2]]
            results["ram_probes"].extend(probes)
            print(f"ram vs {target} esc={escorts}: {probes}", flush=True)

    # Healer A/B at ~equal cost: 8 warriors + 2 healers vs 10 warriors
    runs = [run_duel(s, ("warrior", 8), ("warrior", 10), extra="healer_a") for s in seeds]
    results["healer_ab"]["w8h2_vs_w10"] = runs
    print(f"healer A/B: {[(r['a_survive_value'], r['b_survive_value'], r['healing_done']) for r in runs]}",
          flush=True)

    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=1)
    print(f"wrote {args.output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
