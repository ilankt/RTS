"""Personality weights for the utility AI.

Weighted score = base_score * PERSONALITY_WEIGHTS[personality][goal.category].
"""

PERSONALITY_WEIGHTS = {
    "rusher":   {"economy": 0.7, "military": 1.5, "tactical": 1.4, "support": 0.5},
    "boomer":   {"economy": 1.5, "military": 0.8, "tactical": 0.8, "support": 1.2},
    "turtle":   {"economy": 1.0, "military": 1.0, "tactical": 0.7, "support": 1.5},
    "balanced": {"economy": 1.0, "military": 1.0, "tactical": 1.0, "support": 1.0},
}

# Army size at which AttackGoal starts firing (§7.2 "attack-trigger army size").
# EXPERIMENT LOG (2026-07-10): {rusher 4, boomer/turtle 8} was tried after
# rusher went 1-4 vs boomer in the corrected 20-match run — and FAILED
# validation on the same seeds (rusher 4/13 -> 3/13, head-to-head 0-5):
# attacking earlier with a smaller army into full-DPS defenses compounds the
# deficit — BECAUSE attacks then beelined the castle.
# RETRY (2026-07-13): with §7.3 raid targeting, a small army no longer
# marches into castle DPS — it hits undefended expansions. That flips the
# early-attack math, so rusher gets its early trigger back alongside raids.
# AGGRESSION RE-TUNE (2026-07-14): boomer commits LATE (9) — its identity
# is boom-then-overwhelm, and attacking at the shared threshold 6 with a
# superior economy made it the best rusher too (86 % win rate after the
# §8.12 defender buffs). The gap is the rusher's timing window.
# Rusher's early trigger (4) removed 2026-07-14: with §8.11 emergency
# defense + §8.12 awareness, a 4-5 unit push into a mobilized base is a
# guaranteed wipe (instrumented seed 1001: 5 units died without scratching
# the castle, then the counterattack ended the game). Rusher's identity is
# warrior-heavy pressure + relentless raids, not suicide timing.
ATTACK_ARMY_THRESHOLDS = {
    "boomer": 9,
}


def get_weight(personality: str, category: str) -> float:
    """Look up the multiplier for `category` under the given personality.

    Unknown personality falls back to balanced; unknown category falls back to 1.0.
    """
    weights = PERSONALITY_WEIGHTS.get(personality, PERSONALITY_WEIGHTS["balanced"])
    return weights.get(category, 1.0)


def attack_army_threshold(personality: str) -> int:
    """Minimum army size before this personality launches attacks."""
    return ATTACK_ARMY_THRESHOLDS.get(personality, 6)


# §7.3 risk/reward: up to this army size an attack prefers raiding soft
# enemy expansions over marching into castle defenses. Rusher raids longer
# (its identity); past the limit armies go for the kill.
RAID_ARMY_LIMITS = {
    "rusher": 12,
}


def raid_army_limit(personality: str) -> int:
    return RAID_ARMY_LIMITS.get(personality, 7)


# Signature build orders (§7.2): personalities differ in *how they get to an
# army*, not just in category weights. Worker target shapes the opening
# (rusher cuts economy to field units sooner; boomer over-invests), and the
# composition targets give each a recognizable army identity.
# Rusher 4→5→6→8 (2026-07-14 aggression re-tune, instrumented-match
# diagnosis): under the lean economy every army unit costs gold and gold
# costs worker-seconds — a light-worker rusher structurally cannot field
# the early army its identity promises (6 workers produced 4 spearmen by
# t=210 vs boomer's 13 military). Rusher's identity lives in its early
# trigger + raids + warrior-heavy comp; its economy must be near-parity.
# Near-parity economies (2026-07-14 re-tune): with gold income capped by
# node saturation + haul time, worker count was the only macro that
# mattered and boomer's 9 beat everything (71-86% win rate). Identities
# now live in attack thresholds, compositions, raids, and support spend.
WORKER_TARGETS = {
    "rusher": 8,
    "balanced": 7,
    "turtle": 7,
    "boomer": 8,
}

# Cavalry included since 2026-07-13: it was absent from every table, and with
# composition-driven training it never got trained at all (0 across 24 sim
# matches post-lean-economy). Raid-minded personalities lean into it.
COMPOSITION_TARGETS = {
    "rusher":   {"warrior": 0.45, "archer": 0.15, "spearman": 0.25, "cavalry": 0.15},
    "boomer":   {"warrior": 0.25, "archer": 0.35, "spearman": 0.30, "cavalry": 0.10},
    "turtle":   {"warrior": 0.25, "archer": 0.40, "spearman": 0.30, "cavalry": 0.05},
    "balanced": {"warrior": 0.35, "archer": 0.25, "spearman": 0.25, "cavalry": 0.15},
}


def worker_target(personality: str) -> int:
    """How many workers this personality's opening aims for."""
    return WORKER_TARGETS.get(personality, 6)


def composition_target(personality: str, unit_name: str) -> float:
    """Target fraction of the army for a barracks unit type."""
    table = COMPOSITION_TARGETS.get(personality, COMPOSITION_TARGETS["balanced"])
    return table.get(unit_name, 0.33)


# §8.10: how many watchtowers each personality is willing to maintain.
TOWER_CAPS = {
    "turtle": 3,
    "balanced": 2,
    "boomer": 2,
    "rusher": 1,
}


def tower_cap(personality: str) -> int:
    return TOWER_CAPS.get(personality, 1)


# §8.10 AI walling: how many wall-line slots (walls + one gate) each
# personality maintains across the threat bearing. 0 = never walls.
WALL_SEGMENT_TARGETS = {
    "turtle": 11,
    "balanced": 0,
    "boomer": 0,
    "rusher": 0,
}


def wall_segments(personality: str) -> int:
    return WALL_SEGMENT_TARGETS.get(personality, 0)


# §7.2 honest difficulty tiers: scale *decision quality* levers - reaction
# time (strategic tick cadence), attack commitment, and worker micro - never
# stats or resources (the §7.1 fairness guardrail).
DIFFICULTY_MODS = {
    "easy":   {"tick_interval": 1.0,  "attack_threshold_delta": 3,  "worker_assignments": 1},
    "normal": {"tick_interval": 0.5,  "attack_threshold_delta": 0,  "worker_assignments": 2},
    "hard":   {"tick_interval": 0.35, "attack_threshold_delta": -1, "worker_assignments": 3},
}


def difficulty_mods(difficulty: str) -> dict:
    return DIFFICULTY_MODS.get(difficulty, DIFFICULTY_MODS["normal"])
