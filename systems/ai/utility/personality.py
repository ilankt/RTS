"""Personality weights for the utility AI.

Weighted score = base_score * PERSONALITY_WEIGHTS[personality][goal.category].
"""

PERSONALITY_WEIGHTS = {
    "rusher":   {"economy": 0.7, "military": 1.5, "tactical": 1.4, "support": 0.5},
    "boomer":   {"economy": 1.5, "military": 0.8, "tactical": 0.8, "support": 1.2},
    "turtle":   {"economy": 1.0, "military": 1.0, "tactical": 0.7, "support": 1.5},
    "balanced": {"economy": 1.0, "military": 1.0, "tactical": 1.0, "support": 1.0},
}


def get_weight(personality: str, category: str) -> float:
    """Look up the multiplier for `category` under the given personality.

    Unknown personality falls back to balanced; unknown category falls back to 1.0.
    """
    weights = PERSONALITY_WEIGHTS.get(personality, PERSONALITY_WEIGHTS["balanced"])
    return weights.get(category, 1.0)
