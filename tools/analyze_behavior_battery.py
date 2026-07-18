"""Aggregate a directory of instrumented_match battery_*.json files into the
AI-behavior diagnosis dimensions (§7 AI depth): healers/temples, cavalry,
expansion, formation, ram escort, fountain presence, goal fallthrough.

Usage:
  python tools/analyze_behavior_battery.py <dir-with-battery_*.json>
"""
import glob
import json
import os
import statistics as st
import sys

RAM_ALONE_PX = 150   # a ram farther than this from any fighter is "alone"
BEHIND_MARGIN = 20   # archers count as "behind" when this much farther out


def main(directory):
    files = sorted(glob.glob(os.path.join(directory, "battery_*.json")))
    if not files:
        print(f"no battery_*.json under {directory}")
        return 1

    wins, appear = {}, {}
    durations, timeouts = [], 0
    temples = []       # (seed, player, personality, temples, healers)
    cavalry_rows = []  # (seed, player, personality, cavalry, combat_total)
    ram_alone, ram_total = [], 0
    formation = {"behind": 0, "mixed": 0, "melee": [], "ranged": []}
    fountain = {}      # personality -> [samples_with_presence, total, peak]
    expansions = []    # (seed, player, personality, castles_built)
    fallthrough = {}
    chosen, chosen_ticks = {}, {}

    for path in files:
        d = json.load(open(path))
        seed = d["config"]["seed"]
        pers = d["config"]["personalities"]
        if d["completed"]:
            durations.append(d["sim_seconds"])
        else:
            timeouts += 1
        for p in pers.values():
            appear[p] = appear.get(p, 0) + 1
        if d["winner_personality"]:
            wins[d["winner_personality"]] = wins.get(d["winner_personality"], 0) + 1

        trained, built = {}, {}
        for key, n in d["units_trained"].items():
            pl, ut = key.split("|")
            trained.setdefault(pl, {})[ut] = n
        for key, n in d["buildings_built"].items():
            pl, bt = key.split("|")
            built.setdefault(pl, {})[bt] = n

        for pl, p in pers.items():
            temples.append((seed, pl, p, built.get(pl, {}).get("temple", 0),
                            trained.get(pl, {}).get("healer", 0)))
            combat = sum(n for ut, n in trained.get(pl, {}).items() if ut != "worker")
            cavalry_rows.append((seed, pl, p, trained.get(pl, {}).get("cavalry", 0), combat))
            expansions.append((seed, pl, p, built.get(pl, {}).get("castle", 0)))

        for key, n in d["goal_fallthrough"].items():
            pl, goal = key.split("|")
            fallthrough[(pers[pl], goal)] = fallthrough.get((pers[pl], goal), 0) + n
        for key, n in d["goal_chosen"].items():
            pl, goal = key.split("|")
            chosen[(pers[pl], goal)] = chosen.get((pers[pl], goal), 0) + n
            chosen_ticks[pers[pl]] = chosen_ticks.get(pers[pl], 0) + n

        for s in d["samples"]:
            if "error" in s:
                continue
            for pl, pdata in s["players"].items():
                p = pers[pl]
                for dist in pdata["ram_escort_dists"]:
                    ram_total += 1
                    if dist > RAM_ALONE_PX:
                        ram_alone.append(dist)
                md, rd = pdata["melee_engaged_dists"], pdata["ranged_engaged_dists"]
                if md and rd:
                    m, r = st.mean(md), st.mean(rd)
                    formation["melee"].append(m)
                    formation["ranged"].append(r)
                    formation["behind" if r > m + BEHIND_MARGIN else "mixed"] += 1
                f = fountain.setdefault(p, [0, 0, 0])
                f[1] += 1
                if pdata["units_near_fountain"] >= 1:
                    f[0] += 1
                f[2] = max(f[2], pdata["units_near_fountain"])

    print("=== MATCHES ===")
    print(f"files: {len(files)}  timeouts: {timeouts}  avg duration (completed): "
          f"{round(st.mean(durations)) if durations else '-'} sim-s")
    print("win rate:", {p: f"{wins.get(p, 0)}/{appear[p]}" for p in sorted(appear)})

    print("\n=== HEALERS / TEMPLES (seed, player, personality, temples, healers) ===")
    for row in temples:
        print(row)

    print("\n=== CAVALRY (seed, player, personality, cavalry, combat_total) ===")
    for row in cavalry_rows:
        frac = f"{row[3] / row[4]:.0%}" if row[4] else "-"
        print(row, frac)

    print("\n=== EXPANSION: castles BUILT during match (0 = never expanded) ===")
    built_any = [r for r in expansions if r[3] > 0]
    print(f"players who built a castle: {len(built_any)}/{len(expansions)}")
    for row in built_any:
        print(row)

    print("\n=== FORMATION (samples where both archers+melee engaged) ===")
    tot = formation["behind"] + formation["mixed"]
    if tot:
        print(f"archers clearly behind melee: {formation['behind']}/{tot} "
              f"({formation['behind'] / tot:.0%})")
        print(f"mean melee dist-to-enemy: {st.mean(formation['melee']):.0f}px, "
              f"mean archer dist-to-enemy: {st.mean(formation['ranged']):.0f}px")

    print("\n=== RAM ESCORT ===")
    print(f"ram-samples: {ram_total}, alone (>{RAM_ALONE_PX}px from nearest fighter): "
          f"{len(ram_alone)} ({(len(ram_alone) / ram_total) if ram_total else 0:.0%})")
    if ram_alone:
        print(f"alone distances: mean {st.mean(ram_alone):.0f}px, max {max(ram_alone):.0f}px")

    print("\n=== FOUNTAIN PRESENCE (personality: samples-with-any-unit / total, peak) ===")
    for p, (present, total, peak) in sorted(fountain.items()):
        print(f"  {p}: {present}/{total} ({present / total:.0%}), peak {peak}")

    print("\n=== TOP FALLTHROUGH (top-scored goal failed to execute) ===")
    for (p, goal), n in sorted(fallthrough.items(), key=lambda x: -x[1])[:12]:
        print(f"  {p:9s} {goal:22s} {n}")

    print("\n=== GOAL CHOSEN SHARE BY PERSONALITY (top 8 each) ===")
    for p in sorted(chosen_ticks):
        total = chosen_ticks[p]
        rows = sorted(((g, n) for (pp, g), n in chosen.items() if pp == p),
                      key=lambda x: -x[1])[:8]
        print(f"  {p} ({total} ticks): " + ", ".join(f"{g}:{n / total:.0%}" for g, n in rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "."))
