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
    parser.add_argument("--max-frame-avg-ms", type=float, default=None, help="Fail if frame_avg_ms exceeds this.")
    parser.add_argument("--max-frame-p95-ms", type=float, default=None, help="Fail if frame_p95_ms exceeds this.")
    parser.add_argument("--max-ai-max-ms", type=float, default=None, help="Fail if ai_max_ms exceeds this.")
    parser.add_argument("--output", type=str, default=None, help="Write the summary JSON to this path.")
    parser.add_argument("--profile", type=str, default=None, help="Run under cProfile and dump stats to this path.")
    return parser.parse_args()


def run_benchmark(args):
    perf_stats.enabled = True
    game = Game(mode="ai_spectator", player_count=4)
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


def check_thresholds(args, summary):
    failures = []
    if args.fail_on_stall and summary["frame_max_ms"] > args.stall_ms:
        failures.append(f"frame_max_ms {summary['frame_max_ms']:.1f} > stall threshold {args.stall_ms:.1f}")
    if args.max_frame_avg_ms is not None and summary["frame_avg_ms"] > args.max_frame_avg_ms:
        failures.append(f"frame_avg_ms {summary['frame_avg_ms']:.1f} > {args.max_frame_avg_ms:.1f}")
    if args.max_frame_p95_ms is not None and summary["frame_p95_ms"] > args.max_frame_p95_ms:
        failures.append(f"frame_p95_ms {summary['frame_p95_ms']:.1f} > {args.max_frame_p95_ms:.1f}")
    if args.max_ai_max_ms is not None and summary["ai_max_ms"] > args.max_ai_max_ms:
        failures.append(f"ai_max_ms {summary['ai_max_ms']:.1f} > {args.max_ai_max_ms:.1f}")
    return failures


def main():
    args = parse_args()
    profiler = None
    if args.profile:
        import cProfile

        profiler = cProfile.Profile()
        profiler.enable()
    try:
        summary = run_benchmark(args)
    finally:
        if profiler is not None:
            profiler.disable()
            profiler.dump_stats(args.profile)
        debug_log.close()

    print(json.dumps(summary, indent=2, sort_keys=True))
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            json.dump(summary, handle, indent=2, sort_keys=True)
    failures = check_thresholds(args, summary)
    for failure in failures:
        print(f"THRESHOLD FAIL: {failure}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
