"""Population cap — the ONE authority.

2026-07-25 battery finding: the cap was never engine-enforced —
production_manager checked only costs, the human top bar displayed
20 + 5×houses as pure decoration, and the AI self-limited on a DIFFERENT
formula (5 + 5×houses) in its goal context. Now `start_production` enforces
this module's numbers for everyone, and every consumer (UI, AI context)
reads them from here.
"""

POP_BASE = 10   # 20 → 10 (2026-07-25 balance package: at base 20 the first
                # house decision landed at ~minute 14 and 56% of AI seats
                # never hit the cap in 36 min — housing wasn't a decision)
POP_PER_HOUSE = 5


def population_cap(game, player):
    """POP_BASE plus POP_PER_HOUSE per completed, standing house."""
    houses = sum(1 for b in game.buildings
                 if b.player is player and b.name == "house" and b.hp > 0)
    return POP_BASE + POP_PER_HOUSE * houses


def population_usage(game, player):
    """Live units + garrisoned units + units already ORDERED (in production
    or queued). The training gate checks this number, so a full queue can
    never overshoot the cap when it drains."""
    usage = sum(1 for u in game.units if u.player is player and u.hp > 0)
    for b in game.buildings:
        if b.player is player and b.hp > 0:
            usage += len(getattr(b, "garrison", ()) or ())
            if getattr(b, "current_production", None):
                usage += 1
            usage += len(getattr(b, "production_queue", ()) or ())
    return usage
