"""Headless smoke runner for strategy-slice game modes."""
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

from core.game import Game  # noqa: E402
from utils.debug_logger import debug_log  # noqa: E402


def parse_args():
    parser = argparse.ArgumentParser(description="Run a headless RTS strategy-slice smoke simulation.")
    parser.add_argument("--mode", default="human_1v1", choices=["human_1v1", "ai_spectator"])
    parser.add_argument("--players", type=int, default=None)
    parser.add_argument("--seconds", type=float, default=60.0)
    parser.add_argument("--speed", type=float, default=5.0)
    parser.add_argument("--dt", type=float, default=1 / 60)
    return parser.parse_args()


def run(args):
    player_count = args.players
    if player_count is None:
        player_count = 4 if args.mode == "ai_spectator" else 2
    game = Game(mode=args.mode, player_count=player_count)
    game.game_speed = args.speed

    simulated_per_frame = args.dt * game.game_speed
    frames = max(1, int(math.ceil(args.seconds / simulated_per_frame)))
    for _ in range(frames):
        game.update(delta_time_override=args.dt)
        if game.game_over_state:
            break

    buildings_by_player = {}
    units_by_player = {}
    upgrades_by_player = {}
    resources_by_player = {}
    for player in game.players:
        buildings_by_player[player.name] = {}
        units_by_player[player.name] = {}
        upgrades_by_player[player.name] = sorted(getattr(player, "upgrades", {}).keys())
        resources_by_player[player.name] = dict(player.resources)

    for building in game.buildings:
        owner = building.player.name if building.player else "Neutral"
        buildings_by_player.setdefault(owner, {})
        buildings_by_player[owner][building.name] = buildings_by_player[owner].get(building.name, 0) + 1

    for unit in game.units:
        owner = unit.player.name if unit.player else "Neutral"
        units_by_player.setdefault(owner, {})
        units_by_player[owner][unit.name] = units_by_player[owner].get(unit.name, 0) + 1

    return {
        "mode": args.mode,
        "players": len(game.players),
        "human_players": sum(1 for p in game.players if p.human),
        "ai_players": sum(1 for p in game.players if not p.human),
        "buildings_by_player": buildings_by_player,
        "units_by_player": units_by_player,
        "upgrades_by_player": upgrades_by_player,
        "resources_by_player": resources_by_player,
        "game_over_state": game.game_over_state,
        "tree_regrowth_enabled": game.tree_regrowth_enabled,
    }


def main():
    args = parse_args()
    try:
        summary = run(args)
    finally:
        debug_log.close()
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
