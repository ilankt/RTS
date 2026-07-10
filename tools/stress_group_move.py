"""Headless group-move stress test (Phase 3 gate).

Spawns N warriors in a block, orders them across the map, and reports how
many arrive, how long it takes, and watchdog recovery counts.

Usage:
    python tools/stress_group_move.py --units 100 --seconds 120 --speed 5
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def parse_args():
    parser = argparse.ArgumentParser(description="Group-move stress test.")
    parser.add_argument("--units", type=int, default=100)
    parser.add_argument("--seconds", type=float, default=120.0, help="Max simulated seconds.")
    parser.add_argument("--speed", type=float, default=5.0)
    parser.add_argument("--dt", type=float, default=1 / 60)
    parser.add_argument("--seed", type=int, default=12345)
    parser.add_argument("--arrive-radius", type=float, default=150.0)
    return parser.parse_args()


def main():
    args = parse_args()
    import random

    random.seed(args.seed)

    from core.game import Game
    from entities.unit import Unit, STANCE_NO_ATTACK
    from utils.debug_logger import debug_log
    from utils.perf_stats import perf_stats

    perf_stats.enabled = True
    game = Game(mode="ai_spectator", player_count=2)
    game.game_speed = args.speed
    # Disable the AI so nothing else commands our test units.
    game.ai_system.update = lambda dt: None

    player = game.players[0]
    # Wipe existing units so only the test group exists.
    for unit in list(game.units):
        unit.in_world = False
    game.units.clear()

    # Find two walkable areas far apart: use player castles as anchors.
    castles = [b for b in game.buildings if b.name == "castle"]
    src = castles[0]
    dst = castles[-1]

    units_data = game.production_manager.units_data
    warrior = units_data["warrior"]

    spawned = []
    cols = max(1, int(math.sqrt(args.units)))
    index = 0
    radius_px = 400
    while len(spawned) < args.units and index < args.units * 40:
        angle = (index % 360) * math.pi / 180 * 7
        dist = 60 + (index / max(1, args.units * 40)) * radius_px + (index % 17) * 9
        x = src.x + math.cos(angle) * dist
        y = src.y + math.sin(angle) * dist
        index += 1
        if not game.pathfinder.is_position_walkable((x, y), 10):
            continue
        collides = any(math.hypot(u.x - x, u.y - y) < 22 for u in spawned)
        if collides:
            continue
        unit = Unit(
            name="warrior",
            size=warrior["size"],
            hp=warrior["hp"],
            movement_speed=warrior["movement_speed"],
            attack=warrior.get("attack"),
            animations={},
            x=x,
            y=y,
            radius=warrior["size"][0] * 8,
            player=player,
            can_attack=True,
        )
        unit.animations = {}
        unit.update_animation = lambda dt=None: None
        unit.get_current_sprite = lambda: None
        unit.stance = STANCE_NO_ATTACK  # pure movement test - never fight
        game.units.append(unit)
        spawned.append(unit)

    # Neutral destination: walkable spot near the midpoint between castles.
    mid = ((src.x + dst.x) / 2, (src.y + dst.y) / 2)
    goal_cell = game.pathfinder.grid.nearest_walkable_cell(mid, 10)
    target = game.pathfinder.grid.cell_to_world(goal_cell) if goal_cell else mid

    # Group order via one shared flow field (sunflower-packed slots),
    # falling back to per-unit paths if no field is possible.
    slots = []
    for i in range(len(spawned)):
        angle = i * 2.39996
        ring = 16.0 * math.sqrt(i)
        slots.append((target[0] + math.cos(angle) * ring, target[1] + math.sin(angle) * ring))
    if not game.pathfinder.request_group_move(spawned, target, slots):
        for unit, slot in zip(spawned, slots):
            game.pathfinder.issue_move(unit, slot)

    total_frames = max(1, int(math.ceil(args.seconds / (args.dt * game.game_speed))))
    arrived_at = None
    sim_time = 0.0
    for frame in range(total_frames):
        game.update(delta_time_override=args.dt)
        sim_time += args.dt * game.game_speed
        if frame % 60 == 0:
            arrived = sum(
                1
                for u in spawned
                if math.hypot(u.x - target[0], u.y - target[1]) <= args.arrive_radius + len(spawned) * 0.6
            )
            if arrived >= len(spawned) * 0.95:
                arrived_at = sim_time
                break

    distances = sorted(math.hypot(u.x - target[0], u.y - target[1]) for u in spawned)
    arrive_zone = args.arrive_radius + len(spawned) * 0.6
    arrived = sum(1 for d in distances if d <= arrive_zone)
    summary = perf_stats.summary()
    result = {
        "units": len(spawned),
        "arrived": arrived,
        "arrive_zone": arrive_zone,
        "arrived_95pct_at_sim_s": arrived_at,
        "sim_seconds_run": sim_time,
        "median_final_distance": distances[len(distances) // 2] if distances else None,
        "p90_final_distance": distances[int(len(distances) * 0.9)] if distances else None,
        "watchdog_recoveries": summary["watchdog_recoveries"],
        "watchdog_teleports": summary["watchdog_teleports"],
        "path_queue_enqueued": summary.get("path_queue_enqueued", 0),
        "path_queue_dropped": summary.get("path_queue_dropped", 0),
        "astar_capped": summary.get("astar_capped", 0),
        "frame_avg_ms": round(summary["frame_avg_ms"], 2),
        "frame_p95_ms": round(summary["frame_p95_ms"], 2),
        "frame_max_ms": round(summary["frame_max_ms"], 2),
    }
    stragglers = [
        {
            "pos": (round(u.x), round(u.y)),
            "dist": round(math.hypot(u.x - target[0], u.y - target[1])),
            "status": u.status,
            "has_path": bool(u.path),
            "destination": bool(u.destination),
            "queued": getattr(u, "_pending_path_seq", None) is not None,
        }
        for u in spawned
        if math.hypot(u.x - target[0], u.y - target[1]) > arrive_zone
    ]
    result["stragglers"] = stragglers[:12]
    debug_log.close()
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
