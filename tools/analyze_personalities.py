"""Judge the §8.15 personality gate from a personality-battery directory.

Per personality: wins/appearances with a Wilson 95% interval — the gate
(0.35-0.65) is judged against the INTERVAL, not the point estimate. Plus the
head-to-head pairing table, timeout rate, durations, tech uptake, and the
F6 worker-killer census.

Usage: python tools/analyze_personalities.py <dir> [--json out.json]
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import sys


def wilson(wins, n, z=1.96):
    if n == 0:
        return (0.0, 1.0)
    p = wins / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("indir")
    parser.add_argument("--json", default=None)
    args = parser.parse_args()

    matches = []
    for path in sorted(glob.glob(os.path.join(args.indir, "match_*.json"))):
        with open(path, encoding="utf-8") as fh:
            matches.append(json.load(fh))
    if not matches:
        print("no matches found", file=sys.stderr)
        return 1

    appearances, wins = {}, {}
    head_to_head = {}   # frozenset({a,b}) -> {a: wins, b: wins, "timeout": n}
    durations, timeouts = [], 0
    tech_counts, player_slots = {}, 0
    worker_killers = {}

    for m in matches:
        pers = list(m["config"]["personalities"].values())
        key = frozenset(pers) if len(set(pers)) == 2 else frozenset([pers[0], pers[0] + "#2"])
        table = head_to_head.setdefault(key, {})
        winner = m["winner_personality"]
        if m["completed"] and winner:
            durations.append(m["sim_seconds"])
            wins[winner] = wins.get(winner, 0) + 1
            table[winner] = table.get(winner, 0) + 1
        else:
            timeouts += 1
            table["timeout"] = table.get("timeout", 0) + 1
        for p in pers:
            appearances[p] = appearances.get(p, 0) + 1
        for techs in m.get("final_upgrades", {}).values():
            player_slots += 1
            for t in techs:
                tech_counts[t] = tech_counts.get(t, 0) + 1
        for killer, n in m.get("worker_killers", {}).items():
            worker_killers[killer] = worker_killers.get(killer, 0) + n

    print(f"=== {len(matches)} matches | timeouts {timeouts} "
          f"({timeouts/len(matches):.0%}) | avg decisive {sum(durations)/max(1,len(durations)):.0f} sim-s ===\n")

    print("-- personality gate (0.35-0.65 judged on the Wilson 95% interval) --")
    verdicts = {}
    for p in sorted(appearances):
        n, w = appearances[p], wins.get(p, 0)
        lo, hi = wilson(w, n)
        if lo > 0.65:
            verdict = "TOO STRONG"
        elif hi < 0.35:
            verdict = "TOO WEAK"
        elif 0.35 <= lo and hi <= 0.65:
            verdict = "IN BAND"
        else:
            verdict = "inconclusive (interval spans the bound)"
        verdicts[p] = {"wins": w, "n": n, "rate": round(w / n, 3),
                       "ci": [round(lo, 3), round(hi, 3)], "verdict": verdict}
        print(f"  {p:9s} {w:3d}/{n:3d}  {w/n:.2f}  CI [{lo:.2f}, {hi:.2f}]  {verdict}")

    print("\n-- head-to-head (wins by personality; t/o = timeouts) --")
    for key in sorted(head_to_head, key=lambda k: sorted(k)):
        table = head_to_head[key]
        parts = ", ".join(f"{k}={v}" for k, v in sorted(table.items()))
        print(f"  {' vs '.join(sorted(key)):22s} {parts}")

    print(f"\n-- tech uptake (of {player_slots} player-slots) --")
    for t, n in sorted(tech_counts.items(), key=lambda kv: -kv[1]):
        print(f"  {t:22s} {n:4d}  ({n/max(1,player_slots):.2f})")

    if worker_killers:
        total = sum(worker_killers.values())
        print(f"\n-- worker killers (F6; {total} worker deaths credited) --")
        for k, n in sorted(worker_killers.items(), key=lambda kv: -kv[1]):
            print(f"  {k:12s} {n:5d}  ({n/total:.0%})")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({
                "matches": len(matches), "timeouts": timeouts,
                "verdicts": verdicts,
                "head_to_head": {" vs ".join(sorted(k)): v for k, v in head_to_head.items()},
                "tech_counts": tech_counts, "player_slots": player_slots,
                "worker_killers": worker_killers,
            }, fh, indent=1)
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
