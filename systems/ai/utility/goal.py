"""Base Goal class for the utility AI.

Each tick the orchestrator scores every goal against a snapshot of the game
state. The highest-scoring goal whose `execute` succeeds is the AI's action
for that tick.

Goals are stateless — their score is recomputed fresh from `ctx` each tick.
Anything that needs to persist (in-progress construction, queued production)
is read off the game objects via `ctx`.
"""


class Goal:
    """A scoreable, executable AI decision."""

    name = "<unset>"
    category = "economy"  # economy | military | tactical | support

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
