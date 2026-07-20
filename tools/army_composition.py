"""Late-game army composition from a balance-matrix dir (the ram-share gate).

Reads each match's LAST 30s state sample and aggregates military unit counts
across all players — the same "last sample, all matches" definition the
2026-07-19 report's F1/change-6 gates used.

Usage: python tools/army_composition.py tools/balance_matrix_2026-07-20_v5
"""
import glob
import json
import os
import sys

MILITARY = ("warrior", "archer", "spearman", "cavalry", "ram", "healer")


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        return 1
    counts = {}
    for path in sorted(glob.glob(os.path.join(sys.argv[1], "match_*.json"))):
        with open(path, encoding="utf-8") as fh:
            match = json.load(fh)
        samples = [s for s in match.get("samples", []) if "players" in s]
        if not samples:
            continue
        for pdata in samples[-1]["players"].values():
            for name, n in pdata.get("units", {}).items():
                if name in MILITARY:
                    counts[name] = counts.get(name, 0) + n
    total = sum(counts.values())
    print(f"late-game armies ({total} units across last samples):")
    for name in sorted(counts, key=lambda k: -counts[k]):
        print(f"  {name:9s} {counts[name]:5d}  ({counts[name] / max(1, total):.2f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
