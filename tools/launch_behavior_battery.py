"""Launch the 12-match instrumented behavior battery as parallel processes.

Same parallel pattern as the balance-sim workflow (12 single-match processes).
Varies map size (50-90), player count (2-4), and personality matchups so the
battery exercises small-map rushes, big-map macro, and FFA dynamics.

Usage:
  python tools/launch_behavior_battery.py --outdir tools/behavior_battery_out
Then:
  python tools/analyze_behavior_battery.py tools/behavior_battery_out
"""
import argparse
import os
import subprocess
import sys
import time

TOOLS = os.path.dirname(os.path.abspath(__file__))
RUNNER = os.path.join(TOOLS, "instrumented_match.py")
ROOT = os.path.dirname(TOOLS)

CONFIGS = [
    # (seed, players, map_w, map_h, personalities)
    (2001, 2, 70, 70, "rusher,turtle"),
    (2002, 2, 70, 70, "boomer,balanced"),
    (2003, 2, 50, 50, "rusher,boomer"),
    (2004, 2, 50, 50, "turtle,balanced"),
    (2005, 2, 90, 90, "boomer,turtle"),
    (2006, 2, 90, 90, "balanced,rusher"),
    (2007, 3, 70, 70, "rusher,boomer,turtle"),
    (2008, 3, 80, 80, "balanced,balanced,rusher"),
    (2009, 4, 70, 70, "rusher,boomer,turtle,balanced"),
    (2010, 4, 90, 90, "rusher,boomer,turtle,balanced"),
    (2011, 2, 70, 70, "turtle,turtle"),
    (2012, 2, 70, 70, "boomer,boomer"),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--outdir", type=str, required=True)
    parser.add_argument("--seconds", type=float, default=2400.0)
    args = parser.parse_args()
    os.makedirs(args.outdir, exist_ok=True)

    procs = []
    for seed, players, w, h, pers in CONFIGS:
        out = os.path.join(args.outdir, f"battery_{seed}.json")
        log = open(os.path.join(args.outdir, f"battery_{seed}.log"), "w")
        cmd = [sys.executable, RUNNER,
               "--seed", str(seed), "--players", str(players),
               "--map-w", str(w), "--map-h", str(h),
               "--personalities", pers,
               "--seconds", str(args.seconds), "--output", out]
        procs.append((seed, subprocess.Popen(cmd, cwd=ROOT, stdout=log, stderr=log)))

    print(f"launched {len(procs)} matches", flush=True)
    start = time.time()
    failed = []
    for seed, proc in procs:
        rc = proc.wait()
        if rc != 0:
            failed.append(seed)
        print(f"seed {seed}: {'ok' if rc == 0 else f'FAILED rc={rc}'} "
              f"({time.time() - start:.0f}s elapsed)", flush=True)
    print(f"battery done in {time.time() - start:.0f}s; failures: {failed or 'none'}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
