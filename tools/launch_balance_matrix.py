"""Launch the §8.15 balance matrix as parallel instrumented matches.

Covers the axes the balance report needs:
  - all 6 personality pairings (x2 seeds, seats swapped on the repeat)
  - map size (50/70/90) on rush-vs-macro sensitive pairings
  - 3- and 4-player FFA
  - personality mirrors (pure per-personality usage data)
  - difficulty axis on a personality-neutral mirror + crosses

Same parallel single-match-process pattern as §8.8 (aggregate win rates hide
structural defects; per-match JSON keeps everything inspectable). Runs in
waves so a 32-core box isn't oversubscribed alongside other work.

Usage:
  python tools/launch_balance_matrix.py --outdir tools/balance_matrix_2026-07-19
  python tools/analyze_balance_matrix.py tools/balance_matrix_2026-07-19
"""
import argparse
import os
import subprocess
import sys
import time

TOOLS = os.path.dirname(os.path.abspath(__file__))
RUNNER = os.path.join(TOOLS, "instrumented_match.py")
ROOT = os.path.dirname(TOOLS)

# (seed, players, map_w, map_h, personalities, difficulties-or-None)
CONFIGS = [
    # -- all 6 pairings, 70x70, normal --
    (3001, 2, 70, 70, "rusher,boomer", None),
    (3002, 2, 70, 70, "rusher,turtle", None),
    (3003, 2, 70, 70, "rusher,balanced", None),
    (3004, 2, 70, 70, "boomer,turtle", None),
    (3005, 2, 70, 70, "boomer,balanced", None),
    (3006, 2, 70, 70, "turtle,balanced", None),
    # -- same pairings, seats swapped, fresh seeds (seat/spawn bias check) --
    (3011, 2, 70, 70, "boomer,rusher", None),
    (3012, 2, 70, 70, "turtle,rusher", None),
    (3013, 2, 70, 70, "balanced,rusher", None),
    (3014, 2, 70, 70, "turtle,boomer", None),
    (3015, 2, 70, 70, "balanced,boomer", None),
    (3016, 2, 70, 70, "balanced,turtle", None),
    # -- map size axis --
    (3021, 2, 50, 50, "rusher,boomer", None),
    (3022, 2, 50, 50, "turtle,balanced", None),
    (3023, 2, 90, 90, "rusher,boomer", None),
    (3024, 2, 90, 90, "turtle,boomer", None),
    # -- multiplayer --
    (3031, 3, 70, 70, "rusher,boomer,turtle", None),
    (3032, 3, 80, 80, "balanced,turtle,boomer", None),
    (3033, 4, 70, 70, "rusher,boomer,turtle,balanced", None),
    (3034, 4, 90, 90, "rusher,boomer,turtle,balanced", None),
    (3035, 4, 80, 80, "turtle,balanced,rusher,boomer", None),
    # -- mirrors (pure per-personality data) --
    (3041, 2, 70, 70, "rusher,rusher", None),
    (3042, 2, 70, 70, "boomer,boomer", None),
    (3043, 2, 70, 70, "turtle,turtle", None),
    (3044, 2, 70, 70, "balanced,balanced", None),
    # -- difficulty axis (mirror personalities so only difficulty differs) --
    (3051, 2, 70, 70, "balanced,balanced", "hard,easy"),
    (3052, 2, 70, 70, "balanced,balanced", "hard,normal"),
    (3053, 2, 70, 70, "balanced,balanced", "normal,easy"),
    (3054, 2, 70, 70, "rusher,turtle", "hard,easy"),
    (3055, 4, 70, 70, "rusher,boomer,turtle,balanced", "hard,hard,easy,easy"),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--outdir", type=str, required=True)
    parser.add_argument("--seconds", type=float, default=2400.0)
    parser.add_argument("--wave-size", type=int, default=15)
    args = parser.parse_args()
    os.makedirs(args.outdir, exist_ok=True)

    start = time.time()
    failed = []
    pending = list(CONFIGS)
    wave_num = 0
    while pending:
        wave, pending = pending[:args.wave_size], pending[args.wave_size:]
        wave_num += 1
        procs = []
        for seed, players, w, h, pers, diffs in wave:
            out = os.path.join(args.outdir, f"match_{seed}.json")
            log = open(os.path.join(args.outdir, f"match_{seed}.log"), "w")
            cmd = [sys.executable, RUNNER,
                   "--seed", str(seed), "--players", str(players),
                   "--map-w", str(w), "--map-h", str(h),
                   "--personalities", pers,
                   "--seconds", str(args.seconds), "--output", out]
            if diffs:
                cmd += ["--difficulties", diffs]
            procs.append((seed, subprocess.Popen(cmd, cwd=ROOT, stdout=log, stderr=log)))
        print(f"wave {wave_num}: launched {len(procs)}", flush=True)
        for seed, proc in procs:
            rc = proc.wait()
            if rc != 0:
                failed.append(seed)
            print(f"  seed {seed}: {'ok' if rc == 0 else f'FAILED rc={rc}'} "
                  f"({time.time() - start:.0f}s)", flush=True)
    print(f"matrix done in {time.time() - start:.0f}s; failures: {failed or 'none'}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
