"""Merge per-slice balance_sim JSONs (parallel runs) into one summary.

balance_sim.py runs matches sequentially; for long fair-perception matches
it's faster to run N slices in parallel with disjoint --seed-base ranges and
merge:

    python tools/balance_sim.py --matches 3 --seed-base 1000 --output a.json &
    python tools/balance_sim.py --matches 3 --seed-base 1003 --output b.json &
    ...
    python tools/merge_balance_runs.py a.json b.json ... --output merged.json
"""
from __future__ import annotations

import argparse
import json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+")
    parser.add_argument("--output", type=str, default=None)
    args = parser.parse_args()

    runs = [json.load(open(path, encoding="utf-8")) for path in args.inputs]

    matches_detail = []
    appearances, wins = {}, {}
    unit_total, building_total = {}, {}
    unit_by_p, building_by_p = {}, {}
    tower_damage = {}
    durations, timeouts = [], 0

    for run in runs:
        timeouts += run.get("timeouts", 0)
        matches_detail += run.get("matches_detail", [])
        for match in run.get("matches_detail", []):
            if match.get("completed"):
                durations.append(match["sim_seconds"])
            for personality in match["personalities"].values():
                appearances[personality] = appearances.get(personality, 0) + 1
            winner = match.get("winner_personality")
            if winner:
                wins[winner] = wins.get(winner, 0) + 1
        for table, dest in ((run.get("unit_usage_total", {}), unit_total),
                            (run.get("building_usage_total", {}), building_total)):
            for key, count in table.items():
                dest[key] = dest.get(key, 0) + count
        for table, dest in ((run.get("unit_usage_by_personality", {}), unit_by_p),
                            (run.get("building_usage_by_personality", {}), building_by_p)):
            for personality, bucket in table.items():
                slot = dest.setdefault(personality, {})
                for key, count in bucket.items():
                    slot[key] = slot.get(key, 0) + count
        for personality, dmg in run.get("tower_damage_by_personality", {}).items():
            tower_damage[personality] = tower_damage.get(personality, 0) + dmg

    summary = {
        "matches": len(matches_detail),
        "merged_from": args.inputs,
        "timeouts": timeouts,
        "avg_match_sim_seconds": round(sum(durations) / len(durations), 1) if durations else None,
        "win_rate_by_personality": {
            p: {"appearances": appearances[p], "wins": wins.get(p, 0),
                "win_rate": round(wins.get(p, 0) / appearances[p], 2)}
            for p in sorted(appearances)
        },
        "unit_usage_total": dict(sorted(unit_total.items())),
        "building_usage_total": dict(sorted(building_total.items())),
        "unit_usage_by_personality": unit_by_p,
        "building_usage_by_personality": building_by_p,
        "tower_damage_by_personality": {k: round(v, 1) for k, v in sorted(tower_damage.items())},
        "matches_detail": matches_detail,
    }
    print(json.dumps({k: summary[k] for k in
                      ("matches", "timeouts", "avg_match_sim_seconds", "win_rate_by_personality",
                       "unit_usage_total")}, indent=2))
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            json.dump(summary, handle, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
