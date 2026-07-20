"""§8.15 personality-gate battery: all 6 pairings x N seeds x both seats.

The 30-match matrix could not judge the 0.35-0.65 personality win-rate gate
(±0.14 at ~14 appearances; rusher swung 0.36->0.50->0.29 across same-seed
batteries). At --reps 20 this runs 240 matches -> 120 appearances per
personality -> ±~0.09 (95% CI), enough to rule.

Samples are effectively disabled (--sample-every 1e6) to keep 240 JSONs
small; goal histograms and combat aggregates stay in.

Usage:
  python tools/launch_personality_battery.py --outdir tools/personality_battery_2026-07-20
  python tools/analyze_personalities.py tools/personality_battery_2026-07-20
"""
import argparse
import itertools
import os
import subprocess
import sys
import time

TOOLS = os.path.dirname(os.path.abspath(__file__))
RUNNER = os.path.join(TOOLS, "instrumented_match.py")
ROOT = os.path.dirname(TOOLS)

PERSONALITIES = ("rusher", "boomer", "turtle", "balanced")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--outdir", type=str, required=True)
    parser.add_argument("--reps", type=int, default=20, help="seeds per pairing (x2 seats)")
    parser.add_argument("--seconds", type=float, default=2400.0)
    parser.add_argument("--wave-size", type=int, default=14)
    parser.add_argument("--seed-base", type=int, default=5000)
    args = parser.parse_args()
    os.makedirs(args.outdir, exist_ok=True)

    configs = []
    pairings = list(itertools.combinations(PERSONALITIES, 2))
    for pairing_index, (a, b) in enumerate(pairings):
        for rep in range(args.reps):
            seed = args.seed_base + pairing_index * 1000 + rep * 2
            # both seat orders, distinct seeds — seat/spawn bias averages out
            configs.append((seed, f"{a},{b}"))
            configs.append((seed + 1, f"{b},{a}"))

    print(f"{len(configs)} matches across {len(pairings)} pairings", flush=True)
    start = time.time()
    failed = []
    pending = list(configs)
    wave_num = 0
    while pending:
        wave, pending = pending[:args.wave_size], pending[args.wave_size:]
        wave_num += 1
        procs = []
        for seed, pers in wave:
            out = os.path.join(args.outdir, f"match_{seed}.json")
            log = open(os.path.join(args.outdir, f"match_{seed}.log"), "w")
            cmd = [sys.executable, RUNNER,
                   "--seed", str(seed), "--players", "2",
                   "--map-w", "70", "--map-h", "70",
                   "--personalities", pers,
                   "--sample-every", "1000000",
                   "--seconds", str(args.seconds), "--output", out]
            procs.append((seed, subprocess.Popen(cmd, cwd=ROOT, stdout=log, stderr=log)))
        for seed, proc in procs:
            rc = proc.wait()
            if rc != 0:
                failed.append(seed)
        done = len(configs) - len(pending)
        print(f"wave {wave_num}: {done}/{len(configs)} done "
              f"({time.time() - start:.0f}s elapsed, {len(failed)} failed)", flush=True)
    print(f"battery done in {time.time() - start:.0f}s; failures: {failed or 'none'}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
