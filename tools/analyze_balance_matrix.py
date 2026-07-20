"""Aggregate the §8.15 balance-matrix battery into balance-relevant tables.

Reads every match_*.json in the given directory (instrumented_match output)
and prints:
  - win rates by personality (difficulty-varied matches excluded), map size,
    player count; the difficulty axis separately
  - per-unit combat economics: trained/lost/kills/damage, damage per unit,
    damage per 1000 gold-equivalent spent, K/D, survival
  - per-building usage + losses + never-built audit
  - tech uptake rates
  - match duration stats

Usage:
  python tools/analyze_balance_matrix.py tools/balance_matrix_2026-07-19 [--json out.json]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

COST_WEIGHTS = {"gold": 1.0, "wood": 0.5, "food": 0.5}


def ge_cost(costs):
    return sum(COST_WEIGHTS.get(r, 1.0) * a for r, a in costs.items())


def load_costs():
    units = {u["name"]: ge_cost(u.get("costs", {}))
             for u in json.load(open("data/units.json", encoding="utf-8"))}
    buildings = {b["name"]: ge_cost(b.get("costs", {}))
                 for b in json.load(open("data/buildings.json", encoding="utf-8"))}
    return units, buildings


def split_key(key):
    player, _, kind = key.partition("|")
    return player, kind


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
        print("no match files found", file=sys.stderr)
        return 1

    unit_ge, building_ge = load_costs()

    # ---- win rates ---------------------------------------------------------
    def is_difficulty_match(m):
        diffs = set(m["config"].get("difficulties", {}).values())
        return len(diffs) > 1

    appearances, wins = {}, {}
    by_map, by_players = {}, {}
    durations, timeouts = [], 0
    for m in matches:
        if m["completed"]:
            durations.append(m["sim_seconds"])
        else:
            timeouts += 1
        if not is_difficulty_match(m):
            for pers in m["config"]["personalities"].values():
                appearances[pers] = appearances.get(pers, 0) + 1
            if m["winner_personality"]:
                wins[m["winner_personality"]] = wins.get(m["winner_personality"], 0) + 1
        map_key = f"{m['config']['map'][0]}x{m['config']['map'][1]}"
        by_map.setdefault(map_key, []).append(m)
        by_players.setdefault(m["config"]["players"], []).append(m)

    # ---- difficulty axis ---------------------------------------------------
    difficulty_outcomes = []
    for m in matches:
        if not is_difficulty_match(m):
            continue
        diffs = m["config"]["difficulties"]
        winner_diff = diffs.get(m["winner_name"]) if m["winner_name"] else None
        difficulty_outcomes.append({
            "seed": m["config"]["seed"],
            "matchup": diffs,
            "personalities": m["config"]["personalities"],
            "winner_difficulty": winner_diff,
            "sim_s": m["sim_seconds"],
        })

    # ---- per-unit economics ------------------------------------------------
    unit_rows = {}
    for m in matches:
        pers_of = m["config"]["personalities"]

        def bucket(unit):
            return unit_rows.setdefault(unit, {
                "trained": 0, "lost": 0, "kills": 0,
                "damage_dealt": 0.0, "damage_taken": 0.0,
                "by_personality": {},
            })

        for key, n in m["units_trained"].items():
            player, unit = split_key(key)
            row = bucket(unit)
            row["trained"] += n
            per = row["by_personality"].setdefault(pers_of.get(player, "?"), {"trained": 0})
            per["trained"] += n
        for key, n in m.get("units_lost", {}).items():
            _, unit = split_key(key)
            bucket(unit)["lost"] += n
        for key, n in m.get("kills", {}).items():
            _, unit = split_key(key)
            bucket(unit)["kills"] += n
        for key, v in m.get("damage_dealt", {}).items():
            _, unit = split_key(key)
            bucket(unit)["damage_dealt"] += v
        for key, v in m.get("damage_taken", {}).items():
            _, unit = split_key(key)
            bucket(unit)["damage_taken"] += v

    for unit, row in unit_rows.items():
        trained = max(1, row["trained"])
        row["dmg_per_unit"] = round(row["damage_dealt"] / trained, 1)
        row["kills_per_unit"] = round(row["kills"] / trained, 2)
        row["kd"] = round(row["kills"] / max(1, row["lost"]), 2)
        row["survival"] = round(1.0 - row["lost"] / trained, 2)
        cost = unit_ge.get(unit)
        row["ge_cost"] = cost
        row["dmg_per_1000ge"] = (round(1000.0 * row["damage_dealt"] / (cost * trained), 1)
                                 if cost else None)

    # ---- buildings ---------------------------------------------------------
    building_rows = {}
    for m in matches:
        for key, n in m["buildings_built"].items():
            _, b = split_key(key)
            building_rows.setdefault(b, {"built": 0, "lost": 0, "damage_dealt": 0.0})["built"] += n
        for key, n in m.get("buildings_lost", {}).items():
            _, b = split_key(key)
            building_rows.setdefault(b, {"built": 0, "lost": 0, "damage_dealt": 0.0})["lost"] += n
        for key, v in m.get("damage_dealt", {}).items():
            _, name = split_key(key)
            if name in building_ge:
                building_rows.setdefault(name, {"built": 0, "lost": 0, "damage_dealt": 0.0})["damage_dealt"] += v

    all_units = set(json.load(open("data/units.json", encoding="utf-8"))[i]["name"]
                    for i in range(len(unit_ge)))
    all_buildings = set(building_ge)
    never_trained = sorted(all_units - set(unit_rows))
    never_built = sorted(all_buildings - set(building_rows))

    # ---- techs -------------------------------------------------------------
    tech_counts, player_slots = {}, 0
    for m in matches:
        for techs in m.get("final_upgrades", {}).values():
            player_slots += 1
            for t in techs:
                tech_counts[t] = tech_counts.get(t, 0) + 1

    # ---- healing -----------------------------------------------------------
    total_healing = sum(sum(m.get("healing", {}).values()) for m in matches)

    # ---- worker attrition (F6 census) --------------------------------------
    worker_killers = {}
    for m in matches:
        for killer, n in m.get("worker_killers", {}).items():
            worker_killers[killer] = worker_killers.get(killer, 0) + n
    workers_trained = sum(m.get("units_trained", {}).get(k, 0)
                          for m in matches
                          for k in m.get("units_trained", {}) if k.endswith("|worker"))
    worker_deaths = sum(worker_killers.values())

    # ---- print -------------------------------------------------------------
    print(f"=== {len(matches)} matches | avg {sum(durations)/max(1,len(durations)):.0f} sim-s "
          f"| timeouts {timeouts} ===\n")

    print("-- win rate by personality (non-difficulty matches; matchup-bias caveat) --")
    for pers in sorted(appearances):
        n, w = appearances[pers], wins.get(pers, 0)
        print(f"  {pers:9s} {w:2d}/{n:2d}  ({w/n:.2f})")

    print("\n-- by map size --")
    for size in sorted(by_map):
        ms = by_map[size]
        rushed = [m for m in ms if m["winner_personality"]]
        print(f"  {size}: {len(ms)} matches, "
              f"winners: {[m['winner_personality'] for m in rushed]}")

    print("\n-- by player count --")
    for n in sorted(by_players):
        ms = by_players[n]
        print(f"  {n}p: {len(ms)} matches, "
              f"winners: {[m['winner_personality'] or 'timeout' for m in ms]}")

    print("\n-- difficulty axis --")
    for o in difficulty_outcomes:
        print(f"  seed {o['seed']}: {o['matchup']} -> winner {o['winner_difficulty']} "
              f"({o['sim_s']:.0f}s)")

    print("\n-- unit economics (all matches) --")
    header = (f"  {'unit':9s} {'ge':>5s} {'train':>5s} {'lost':>5s} {'surv':>5s} "
              f"{'kills':>5s} {'K/D':>5s} {'dmg/unit':>8s} {'dmg/1000ge':>10s}")
    print(header)
    for unit in sorted(unit_rows, key=lambda u: -(unit_rows[u]["damage_dealt"])):
        r = unit_rows[unit]
        print(f"  {unit:9s} {str(r['ge_cost'] or '-'):>5s} {r['trained']:5d} {r['lost']:5d} "
              f"{r['survival']:5.2f} {r['kills']:5d} {r['kd']:5.2f} "
              f"{r['dmg_per_unit']:8.1f} {str(r['dmg_per_1000ge'] or '-'):>10s}")
    if never_trained:
        print(f"  NEVER TRAINED: {never_trained}")

    print("\n-- building usage --")
    for b in sorted(building_rows, key=lambda x: -building_rows[x]["built"]):
        r = building_rows[b]
        extra = f" dmg={r['damage_dealt']:.0f}" if r["damage_dealt"] else ""
        print(f"  {b:14s} built {r['built']:4d}  lost {r['lost']:4d}{extra}")
    if never_built:
        print(f"  NEVER BUILT: {never_built}")

    print(f"\n-- techs (of {player_slots} player-slots) --")
    for t, n in sorted(tech_counts.items(), key=lambda kv: -kv[1]):
        print(f"  {t:22s} {n:3d}  ({n/max(1,player_slots):.2f})")

    print(f"\n-- healer output: {total_healing:.0f} hp healed across the battery --")

    if worker_killers:  # absent in pre-census datasets — 0 would read as "solved"
        print(f"\n-- worker attrition (F6): {worker_deaths}/{workers_trained} died "
              f"({worker_deaths / workers_trained:.2f}) --")
        for killer, n in sorted(worker_killers.items(), key=lambda kv: -kv[1]):
            print(f"  {killer:14s} {n:5d}  ({n / max(1, worker_deaths):.2f})")

    if args.json:
        summary = {
            "matches": len(matches), "timeouts": timeouts,
            "win_rates": {p: [wins.get(p, 0), appearances[p]] for p in appearances},
            "difficulty_outcomes": difficulty_outcomes,
            "unit_rows": unit_rows, "building_rows": building_rows,
            "never_trained": never_trained, "never_built": never_built,
            "tech_counts": tech_counts, "player_slots": player_slots,
            "total_healing": total_healing,
            "worker_killers": worker_killers, "workers_trained": workers_trained,
        }
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, indent=1)
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
