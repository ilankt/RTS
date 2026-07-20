"""Instrumented single AI-vs-AI match for behavior diagnosis (§7 AI depth).

Beyond tools/balance_sim.py this records:
  - chosen-goal histogram per player (hooks UtilityAISystem._tick)
  - top-goal-vs-chosen fallthrough counts (top-scored goal failed to execute)
  - every N sim-seconds: army comp, buildings, resources, fountain control,
    ram escort distance, archer/melee distance-to-enemy (formation proxy)

One diagnostic run beats a 12-match battery for finding WHY (see the
2026-07-14 instrumentation lesson in PLAN_ARCHIVE). For a full battery use
tools/launch_behavior_battery.py, then tools/analyze_behavior_battery.py.

Usage:
  python tools/instrumented_match.py --seed 2001 --players 2 \
      --personalities rusher,turtle --seconds 2400 --output run_2001.json
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
os.chdir(ROOT)  # asset loads use repo-relative paths

MELEE_FRONT = {"warrior", "spearman"}
RANGED = {"archer"}
ENGAGE_DIST = 500.0
FOUNTAIN_RADIUS = 220.0  # keep in sync with systems/fountain_system.py


def parse_args():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--players", type=int, default=2)
    p.add_argument("--map-w", type=int, default=70)
    p.add_argument("--map-h", type=int, default=70)
    p.add_argument("--personalities", type=str, default=None,
                   help="comma list, one per player, e.g. rusher,turtle")
    p.add_argument("--difficulties", type=str, default=None,
                   help="comma list, one per player, e.g. hard,normal (default normal)")
    p.add_argument("--seconds", type=float, default=2400.0)
    p.add_argument("--speed", type=float, default=5.0)
    p.add_argument("--dt", type=float, default=1 / 60)
    p.add_argument("--sample-every", type=float, default=30.0)
    p.add_argument("--output", type=str, required=True)
    return p.parse_args()


def sample_state(game, sim_time):
    """One tactical snapshot per player."""
    snap = {"t": round(sim_time, 1), "players": {}}
    fountains = list(getattr(game, "fountains", ()))

    units_by_player = {}
    for u in game.units:
        if u.hp <= 0 or u.player is None:
            continue
        units_by_player.setdefault(u.player, []).append(u)

    for player in game.players:
        mine = units_by_player.get(player, [])
        unit_counts = {}
        for u in mine:
            unit_counts[u.name] = unit_counts.get(u.name, 0) + 1

        bld_counts = {}
        for b in game.buildings:
            if b.player is player and b.hp > 0:
                bld_counts[b.name] = bld_counts.get(b.name, 0) + 1

        enemies = [u for pl, ulist in units_by_player.items()
                   if pl is not player for u in ulist
                   if u.name != "worker"]

        def nearest_enemy_dist(u):
            best = None
            for e in enemies:
                d = math.hypot(u.x - e.x, u.y - e.y)
                if best is None or d < best:
                    best = d
            return best

        # Formation proxy: when engaged (<ENGAGE_DIST of an enemy), how far
        # do archers vs front-line melee stand from the nearest enemy?
        melee_d, ranged_d = [], []
        for u in mine:
            if u.name in MELEE_FRONT or u.name in RANGED:
                d = nearest_enemy_dist(u)
                if d is not None and d < ENGAGE_DIST:
                    (melee_d if u.name in MELEE_FRONT else ranged_d).append(d)

        # Ram escort: distance from each ram to nearest friendly fighter
        ram_escort = []
        friends = [u for u in mine if u.name not in ("worker", "ram")]
        for u in mine:
            if u.name != "ram":
                continue
            best = None
            for f in friends:
                d = math.hypot(u.x - f.x, u.y - f.y)
                if best is None or d < best:
                    best = d
            if best is not None:
                ram_escort.append(round(best, 1))

        near_fountain = 0
        for u in mine:
            for f in fountains:
                if math.hypot(u.x - f.x, u.y - f.y) <= FOUNTAIN_RADIUS:
                    near_fountain += 1
                    break

        snap["players"][player.name] = {
            "units": unit_counts,
            "buildings": bld_counts,
            "resources": {k: int(v) for k, v in player.resources.items()},
            "melee_engaged_dists": [round(d, 1) for d in melee_d],
            "ranged_engaged_dists": [round(d, 1) for d in ranged_d],
            "ram_escort_dists": ram_escort,
            "units_near_fountain": near_fountain,
        }
    return snap


def main():
    args = parse_args()
    import random
    random.seed(args.seed)

    from core.game import Game

    game = Game(mode="ai_spectator", player_count=args.players,
                map_size=(args.map_w, args.map_h))
    game.game_speed = args.speed

    if args.personalities:
        wanted = [s.strip() for s in args.personalities.split(",")]
        for player, pers in zip(game.players, wanted):
            player.ai_personality = pers

    if args.difficulties:
        wanted = [s.strip() for s in args.difficulties.split(",")]
        for player, diff in zip(game.players, wanted):
            player.ai_difficulty = diff

    # Hook goal selection (personality is read lazily per tick, and
    # last_chosen*/last_scores are refreshed by every _tick call).
    # Two-lane AI (§7 P2): both the behavior (mode) and action (spend) goals
    # are recorded per tick, and fallthrough is measured on the ACTION lane —
    # "the top-scored spend goal failed to execute" is the starvation signal.
    goal_chosen = {}       # (player_name, goal_name|none) -> count
    goal_top = {}          # (player_name, top_action_goal_name) -> count
    goal_fallthrough = {}  # (player_name, top_action_goal_name) -> count when it didn't fire
    ai = game.ai_system
    orig_tick = ai._tick
    kind_by_name = {g.name: getattr(g, "kind", "action") for g in ai.goals}
    two_lane = hasattr(ai, "last_chosen_action")

    def bump(counter, player_name, goal_name):
        counter[(player_name, goal_name)] = counter.get((player_name, goal_name), 0) + 1

    def tick_hook(player):
        orig_tick(player)
        if two_lane:
            behavior = ai.last_chosen_behavior.get(player)
            action = ai.last_chosen_action.get(player)
            if behavior is None and action is None:
                bump(goal_chosen, player.name, "none")
            for g in (behavior, action):
                if g is not None:
                    bump(goal_chosen, player.name, g.name)
            action_name = action.name if action else "none"
        else:
            chosen = ai.last_chosen.get(player)
            bump(goal_chosen, player.name, chosen.name if chosen else "none")
            action_name = chosen.name if chosen else "none"
        scores = ai.last_scores.get(player) or []
        top_action = next(
            (name for _, _, name in scores
             if kind_by_name.get(name, "action") == "action"), None)
        if top_action is not None:
            bump(goal_top, player.name, top_action)
            if top_action != action_name:
                bump(goal_fallthrough, player.name, top_action)

    ai._tick = tick_hook

    sim_per_frame = args.dt * game.game_speed
    total_frames = max(1, int(math.ceil(args.seconds / sim_per_frame)))
    sim_time = 0.0
    next_sample = 0.0
    samples = []

    for _ in range(total_frames):
        game.update(delta_time_override=args.dt)
        sim_time += sim_per_frame
        if sim_time >= next_sample:
            try:
                samples.append(sample_state(game, sim_time))
            except Exception as e:  # a broken sample must not kill the match
                samples.append({"t": round(sim_time, 1), "error": repr(e)})
            next_sample += args.sample_every
        if game.game_over_state:
            break

    winner = game.winning_player
    personalities = {p.name: p.ai_personality for p in game.players}
    difficulties = {p.name: getattr(p, "ai_difficulty", "normal") for p in game.players}

    def flat(d):
        return {f"{k[0]}|{k[1]}": v for k, v in d.items()}

    result = {
        "config": {
            "seed": args.seed, "players": args.players,
            "map": [args.map_w, args.map_h],
            "personalities": personalities,
            "difficulties": difficulties,
            "seconds_cap": args.seconds,
        },
        "winner_name": winner.name if winner else None,
        "winner_personality": personalities.get(winner.name) if winner else None,
        "completed": game.game_over_state is not None,
        "sim_seconds": round(sim_time, 1),
        "units_trained": flat(game.stats_units_trained),
        "buildings_built": flat(game.stats_buildings_built),
        # §8.15 combat economics (per player|type)
        "damage_dealt": {k: round(v, 1) for k, v in flat(game.stats_damage_dealt).items()},
        "damage_taken": {k: round(v, 1) for k, v in flat(game.stats_damage_taken).items()},
        "kills": flat(game.stats_kills),
        "units_lost": flat(game.stats_units_lost),
        "buildings_lost": flat(game.stats_buildings_lost),
        "healing": {k: round(v, 1) for k, v in game.stats_healing.items()},
        "worker_killers": dict(getattr(game, "stats_worker_killers", {})),
        "resources_gathered": dict(game.stats_resources_gathered),
        "goal_chosen": flat(goal_chosen),
        "goal_top": flat(goal_top),
        "goal_fallthrough": flat(goal_fallthrough),
        "final_upgrades": {p.name: sorted(getattr(p, "upgrades", {}).keys()) for p in game.players},
        "samples": samples,
    }
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=1)
    print(f"done seed={args.seed} winner={result['winner_personality']} t={result['sim_seconds']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
