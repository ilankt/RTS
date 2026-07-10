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
# Tuned from the corrected 20-match balance run (2026-07-10): with a shared
# threshold of 6, rusher went 1-4 against boomer — its "rush" arrived after
# the boom economy had already compounded. Rushers now commit earlier; turtles
# and boomers deliberately later.
ATTACK_ARMY_THRESHOLDS = {
    "rusher": 4,
    "balanced": 6,
    "boomer": 8,
    "turtle": 8,
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
