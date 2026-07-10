"""Balance simulator (MASTER_PLAN §8.8).

Runs N headless AI-vs-AI matches and reports per-personality win rates,
match lengths, and unit/building production histograms — the empirical basis
for tuning §8.3 (resource model) and §8.4 (combat/RPS), and the audit for the
§9 "does the AI actually use everything?" backlog item.

Usage:
    python tools/balance_sim.py --matches 5 --players 2 --seconds 2400
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
    parser = argparse.ArgumentParser(description="Batch AI-vs-AI balance simulation.")
    parser.add_argument("--matches", type=int, default=5)
    parser.add_argument("--players", type=int, default=2)
    parser.add_argument("--seconds", type=float, default=2400.0, help="Max simulated seconds per match.")
    parser.add_argument("--speed", type=float, default=5.0)
    parser.add_argument("--dt", type=float, default=1 / 60)
    parser.add_argument("--seed-base", type=int, default=1000)
    parser.add_argument("--output", type=str, default=None, help="Write the summary JSON here too.")
    return parser.parse_args()


def run_match(args, match_index):
    import random

    random.seed(args.seed_base + match_index)

    from core.game import Game

    game = Game(mode="ai_spectator", player_count=args.players)
    game.game_speed = args.speed

    sim_per_frame = args.dt * game.game_speed
    total_frames = max(1, int(math.ceil(args.seconds / sim_per_frame)))
    sim_time = 0.0
    for _ in range(total_frames):
        game.update(delta_time_override=args.dt)
        sim_time += sim_per_frame
        if game.game_over_state:
            break

    personalities = {p.name: p.ai_personality for p in game.players}
    winner = game.winning_player
    return {
        "seed": args.seed_base + match_index,
        "personalities": personalities,
        "winner_name": winner.name if winner else None,
        "winner_personality": personalities.get(winner.name) if winner else None,
        "completed": game.game_over_state is not None,
        "sim_seconds": round(sim_time, 1),
        "units_trained": {f"{k[0]}|{k[1]}": v for k, v in game.stats_units_trained.items()},
        "buildings_built": {f"{k[0]}|{k[1]}": v for k, v in game.stats_buildings_built.items()},
    }


def main():
    args = parse_args()
    matches = []
    for i in range(args.matches):
        print(f"match {i + 1}/{args.matches}...", file=sys.stderr, flush=True)
        matches.append(run_match(args, i))

    # Aggregate per personality
    appearances = {}
    wins = {}
    unit_usage_by_personality = {}
    building_usage_by_personality = {}
    unit_usage_total = {}
    building_usage_total = {}
    durations = []
    timeouts = 0

    for match in matches:
        if match["completed"]:
            durations.append(match["sim_seconds"])
        else:
            timeouts += 1
        name_to_personality = match["personalities"]
        for personality in name_to_personality.values():
            appearances[personality] = appearances.get(personality, 0) + 1
        if match["winner_personality"]:
            wins[match["winner_personality"]] = wins.get(match["winner_personality"], 0) + 1
        for key, count in match["units_trained"].items():
            player_name, unit_type = key.split("|")
            personality = name_to_personality.get(player_name, "?")
            unit_usage_total[unit_type] = unit_usage_total.get(unit_type, 0) + count
            bucket = unit_usage_by_personality.setdefault(personality, {})
            bucket[unit_type] = bucket.get(unit_type, 0) + count
        for key, count in match["buildings_built"].items():
            player_name, building_type = key.split("|")
            personality = name_to_personality.get(player_name, "?")
            building_usage_total[building_type] = building_usage_total.get(building_type, 0) + count
            bucket = building_usage_by_personality.setdefault(personality, {})
            bucket[building_type] = bucket.get(building_type, 0) + count

    # §9 completeness audit: what does the AI never produce?
    from entities import load_game_data

    data = load_game_data()
    buildable_units = sorted(
        name for name, t in data["units"].items() if getattr(t, "buildable", True) and name != "worker"
    )
    buildable_buildings = sorted(
        name for name, t in data["buildings"].items() if getattr(t, "buildable", True) and name != "castle"
    )
    never_trained = [u for u in buildable_units if u not in unit_usage_total]
    never_built = [b for b in buildable_buildings if b not in building_usage_total]

    summary = {
        "matches": len(matches),
        "players_per_match": args.players,
        "timeouts": timeouts,
        "avg_match_sim_seconds": round(sum(durations) / len(durations), 1) if durations else None,
        "win_rate_by_personality": {
            p: {"appearances": appearances[p], "wins": wins.get(p, 0), "win_rate": round(wins.get(p, 0) / appearances[p], 2)}
            for p in sorted(appearances)
        },
        "unit_usage_total": dict(sorted(unit_usage_total.items())),
        "building_usage_total": dict(sorted(building_usage_total.items())),
        "unit_usage_by_personality": unit_usage_by_personality,
        "building_usage_by_personality": building_usage_by_personality,
        "never_trained": never_trained,
        "never_built": never_built,
        "matches_detail": [
            {k: match[k] for k in ("seed", "personalities", "winner_personality", "completed", "sim_seconds")}
            for match in matches
        ],
    }
    print(json.dumps(summary, indent=2))
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            json.dump(summary, handle, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
