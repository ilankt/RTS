"""Base Goal class for the utility AI.

Each tick the orchestrator scores every goal against a snapshot of the game
state, then fires up to one goal per LANE (§7 P2): the best-scoring
`kind="behavior"` goal sets the army's mode (defend/attack/scout), and the
best-scoring `kind="action"` goal that succeeds spends the economy (build/
train/research/trade). Splitting the lanes ended the score war where
AttackGoal's always-succeeding floor starved production (stable lost 557/560
scored ticks to it pre-split).

Goals are stateless — their score is recomputed fresh from `ctx` each tick.
Anything that needs to persist (in-progress construction, queued production)
is read off the game objects via `ctx`.
"""


class Goal:
    """A scoreable, executable AI decision."""

    name = "<unset>"
    category = "economy"  # economy | military | tactical | support
    kind = "action"       # action (spends economy) | behavior (sets army mode)

    def score(self, ctx) -> float:
        """Return urgency in [0, +inf). 0 means do not run.

        Higher beats lower after personality weighting. Numbers are arbitrary
        but should be roughly comparable across goals — see AI_UTILITY_DESIGN.md
        for the initial calibration table.
        """
        return 0.0

    def execute(self, ctx) -> bool:
        """Take the action. Return True if the world changed (build started,
        unit queued, attack mode entered). Return False to fall through to the
        next-best goal (e.g. we wanted to build but no idle worker is free).
        """
        return False

    def __repr__(self):
        return f"<{self.__class__.__name__} name={self.name!r}>"
