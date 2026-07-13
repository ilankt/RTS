"""§8.3 validation: income vs worker count, one node vs two (worker saturation).

Charts the effective total gather rate of a resource node as workers stack
onto it, using the exact saturation math the game runs. The payoff line for
the risk/reward economy (§7.3): past the cap, a second node (an expansion)
is the only way income keeps growing.

Usage:
    python tools/chart_worker_saturation.py [--output tools/saturation_curve.json]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=str, default=None)
    parser.add_argument("--max-workers", type=int, default=10)
    args = parser.parse_args()

    from core.config import (GATHERING_RATES, WORKER_SATURATION_CAP,
                             WORKER_SATURATION_ENABLED, PLAYER_GATHERING_MULTIPLIER)
    from systems.gathering_manager import saturation_multiplier

    default_player_multiplier = PLAYER_GATHERING_MULTIPLIER

    curves = {}
    for resource, base in sorted(GATHERING_RATES.items()):
        if resource == "food":
            continue  # farms, not nodes
        per_worker = base * default_player_multiplier
        one_node = []
        two_nodes = []
        for n in range(1, args.max_workers + 1):
            total_one = n * per_worker * saturation_multiplier(n)
            # Two nodes: split as evenly as possible
            a, b = (n + 1) // 2, n // 2
            total_two = (a * per_worker * saturation_multiplier(a)
                         + b * per_worker * saturation_multiplier(b))
            one_node.append(round(total_one, 2))
            two_nodes.append(round(total_two, 2))
        curves[resource] = {"one_node_total_per_s": one_node,
                            "two_nodes_total_per_s": two_nodes}

    summary = {
        "saturation_enabled": WORKER_SATURATION_ENABLED,
        "cap_per_node": WORKER_SATURATION_CAP,
        "workers_axis": list(range(1, args.max_workers + 1)),
        "curves": curves,
        "reading": (
            "one_node totals go flat at the cap; two_nodes keeps climbing - "
            "expanding is the only way to grow income past cap workers"
        ),
    }
    print(json.dumps(summary, indent=2))
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            json.dump(summary, handle, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
