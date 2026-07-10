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
# deficit. Rusher's real gap is fielding an army *faster* (signature build
# orders, §7.2), not attacking sooner with less. Thresholds stay flat until
# that lands; the per-personality mechanism remains for difficulty tiers.
ATTACK_ARMY_THRESHOLDS = {}


def get_weight(personality: str, category: str) -> float:
    """Look up the multiplier for `category` under the given personality.

    Unknown personality falls back to balanced; unknown category falls back to 1.0.
    """
    weights = PERSONALITY_WEIGHTS.get(personality, PERSONALITY_WEIGHTS["balanced"])
    return weights.get(category, 1.0)


def attack_army_threshold(personality: str) -> int:
    """Minimum army size before this personality launches attacks."""
    return ATTACK_ARMY_THRESHOLDS.get(personality, 6)
