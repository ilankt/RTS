"""Headless benchmark for the 4-AI spectator scenario."""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time


os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.config import PERF_BENCHMARK_SECONDS  # noqa: E402
from core.game import Game  # noqa: E402
from utils.debug_logger import debug_log  # noqa: E402
from utils.perf_stats import perf_stats  # noqa: E402


def parse_args():
    parser = argparse.ArgumentParser(description="Run a headless 4-AI RTS performance benchmark.")
    parser.add_argument("--seconds", type=float, default=PERF_BENCHMARK_SECONDS, help="Simulated game seconds.")
    parser.add_argument("--speed", type=float, default=5.0, help="Game speed multiplier.")
    parser.add_argument("--dt", type=float, default=1 / 60, help="Raw frame delta before game speed.")
    parser.add_argument("--warmup-frames", type=int, default=30, help="Frames to ignore before collecting stats.")
    parser.add_argument("--stall-ms", type=float, default=500.0, help="Long-frame failure threshold.")
    parser.add_argument("--fail-on-stall", action="store_true", help="Return nonzero if max update exceeds stall threshold.")
    return parser.parse_args()


def run_benchmark(args):
    perf_stats.enabled = True
    game = Game()
    game.game_speed = args.speed

    for _ in range(max(0, args.warmup_frames)):
        game.update(delta_time_override=args.dt)

    simulated_per_frame = args.dt * game.game_speed
    total_frames = max(1, int(math.ceil(args.seconds / simulated_per_frame)))
    perf_stats.reset(max_frames=max(total_frames, args.warmup_frames, 600))
    perf_stats.enabled = True

    started = time.perf_counter()
    ended_early_at = None

    for frame in range(total_frames):
        game.update(delta_time_override=args.dt)
        if game.game_over_state:
            ended_early_at = (frame + 1) * simulated_per_frame
            break

    wall_seconds = time.perf_counter() - started
    summary = perf_stats.summary()
    summary.update(
        {
            "requested_sim_seconds": args.seconds,
            "completed_sim_seconds": ended_early_at or total_frames * simulated_per_frame,
            "game_speed": game.game_speed,
            "raw_dt": args.dt,
            "wall_seconds": wall_seconds,
            "units": len(game.units),
            "buildings": len(game.buildings),
            "resources": len(game.resources),
            "construction_sites": len(game.construction_sites),
            "players": len(game.players),
            "ended_early": ended_early_at is not None,
            "game_over_state": game.game_over_state,
        }
    )
    return summary


def main():
    args = parse_args()
    try:
        summary = run_benchmark(args)
    finally:
        debug_log.close()

    print(json.dumps(summary, indent=2, sort_keys=True))
    if args.fail_on_stall and summary["frame_max_ms"] > args.stall_ms:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
