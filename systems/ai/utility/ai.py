"""Utility-AI orchestrator.

Each tick:

  1. Build a GoalContext snapshot.
  2. Score every goal, weight by personality, sort.
  3. Try execute() top-down until one returns True (that's the chosen action).
  4. Run scout_brain, worker_brain (always), then military_brain with
     should_attack=True iff the chosen goal was AttackGoal.

Per-goal and per-brain failures are logged but never propagate. A broken goal
or sub-brain logs a clear traceback instead of disabling the rest of the AI
tick.
"""
import traceback
from typing import Optional

from utils.debug_logger import debug_log

from systems.ai.worker_brain import WorkerBrain
from systems.ai.military_brain import MilitaryBrain
from systems.ai.scout_brain import ScoutBrain
from systems.ai.building_placer import BuildingPlacer

from .context import GoalContext
from .personality import get_weight
from .goals import ALL_GOALS
from .goals.tactical import AttackGoal
from utils.perf_stats import perf_stats


class UtilityAISystem:
    TICK_INTERVAL = 0.5  # seconds between strategic decisions per AI player

    def __init__(self, game):
        self.game = game
        self.ai_players = [p for p in game.players if not p.human]

        self.worker_brain = WorkerBrain(game)
        self.military_brain = MilitaryBrain(game)
        self.scout_brain = ScoutBrain(game)
        self.building_placer = BuildingPlacer(game)

        self.goals = [cls() for cls in ALL_GOALS]

        player_count = max(1, len(self.ai_players))
        self.tick_timer = {
            player: (index * self.TICK_INTERVAL / player_count)
            for index, player in enumerate(self.ai_players)
        }
        self.last_chosen = {p: None for p in self.ai_players}
        self.last_scores = {p: [] for p in self.ai_players}  # [(weighted, base, name), ...]
        # §7 P2 two-lane selection: the mode goal and the spend goal per tick
        self.last_chosen_behavior = {p: None for p in self.ai_players}
        self.last_chosen_action = {p: None for p in self.ai_players}
        self._tick_counter = {p: 0 for p in self.ai_players}

    # --- Public interface (called by core/game.py and ui/ai_debug_panel.py) ---

    def refresh_players(self):
        """Re-sync the cached AI roster with game.players (§8.14.12:
        loading a save can add or remove players mid-session, and this
        cache otherwise never sees them — appended AIs would simply never
        think). Existing per-player state survives; new players get fresh
        staggered timers; departed players are pruned."""
        self.ai_players = [p for p in self.game.players if not p.human]
        player_count = max(1, len(self.ai_players))
        for index, player in enumerate(self.ai_players):
            self.tick_timer.setdefault(player, index * self.TICK_INTERVAL / player_count)
            self.last_chosen.setdefault(player, None)
            self.last_scores.setdefault(player, [])
            self.last_chosen_behavior.setdefault(player, None)
            self.last_chosen_action.setdefault(player, None)
            self._tick_counter.setdefault(player, 0)
        current = set(self.ai_players)
        for mapping in (self.tick_timer, self.last_chosen, self.last_scores,
                        self.last_chosen_behavior, self.last_chosen_action,
                        self._tick_counter):
            for player in [p for p in mapping if p not in current]:
                del mapping[player]

    def update(self, delta_time: float):
        from .personality import difficulty_mods

        for player in self.ai_players:
            self.tick_timer[player] += delta_time
            # Difficulty scales reaction time (§7.2): easy AIs think slower.
            interval = difficulty_mods(getattr(player, "ai_difficulty", "normal"))["tick_interval"]
            interval *= self._dda_multiplier(player)
            if self.tick_timer[player] < interval:
                continue
            self.tick_timer[player] = 0.0
            with perf_stats.time_ai_tick():
                pathfinder = getattr(self.game, "pathfinder", None)
                if pathfinder is not None and hasattr(pathfinder, "deferred_paths"):
                    # AI commands enqueue their paths; the per-frame queue
                    # drain does the searches. Kills the AI-tick path spike.
                    with pathfinder.deferred_paths():
                        self._tick(player)
                else:
                    self._tick(player)

    # §7.2 covert DDA (opt-in via the adaptive_difficulty setting): nudge AI
    # *reaction time* — never stats or resources — within the chosen tier.
    # A struggling human faces a slower-thinking AI; a dominant one, sharper.
    DDA_BEHIND_RATIO = 0.5   # human below half the AI's score → AI thinks slower
    DDA_AHEAD_RATIO = 2.0    # human above double → AI thinks faster
    DDA_SLOW = 1.5           # tick-interval multipliers (higher = slower AI)
    DDA_FAST = 0.75

    def _dda_multiplier(self, player):
        if not getattr(self.game, "adaptive_difficulty", False):
            return 1.0
        human = next((p for p in self.game.players if getattr(p, "human", False)), None)
        if human is None:
            return 1.0
        score = getattr(self.game, "_score", None)
        if score is None:
            return 1.0
        ai_score = max(1, score(player))
        ratio = score(human) / ai_score
        if ratio < self.DDA_BEHIND_RATIO:
            return self.DDA_SLOW
        if ratio > self.DDA_AHEAD_RATIO:
            return self.DDA_FAST
        return 1.0

    def invalidate_memory_cache(self, player=None):
        """Compatibility shim — the snapshot is rebuilt from scratch each tick,
        so there's no cache to invalidate. Kept for game.py callers."""
        pass

    def get_ai_debug_info(self, player) -> Optional[dict]:
        if player not in self.tick_timer:
            return None

        ctx = GoalContext.build(self.game, player)
        idle, gathering, building = self.worker_brain.get_worker_counts(ctx)

        military_breakdown = {}
        for u in ctx.military:
            military_breakdown[u.name] = military_breakdown.get(u.name, 0) + 1

        production_parts = []
        for name, blist in ctx.buildings.items():
            for b in blist:
                if getattr(b, "current_production", None):
                    production_parts.append(f"{name}: {b.current_production['unit_type']}")
                for q in getattr(b, "production_queue", []):
                    production_parts.append(f"{name}: {q}")

        priority_resource = min(ctx.resources, key=ctx.resources.get) if ctx.resources else "None"

        behavior = self.last_chosen_behavior.get(player)
        action = self.last_chosen_action.get(player)
        chosen_name = " + ".join(
            g.name for g in (behavior, action) if g is not None) or "—"
        top_goals = self.last_scores.get(player, [])[:5]
        goals_summary = ", ".join(f"{name}:{score:.0f}" for score, _, name in top_goals)

        return {
            "game_phase": f"{chosen_name} | top: {goals_summary}",
            "formations": 0,
            "priority_resource": priority_resource,
            "decision_timer": max(0.0, self.TICK_INTERVAL - self.tick_timer.get(player, 0)),
            "idle_workers": idle,
            "gathering_workers": gathering,
            "building_workers": building,
            "military_units": len(ctx.military),
            "military_breakdown": military_breakdown,
            "buildings": {
                "total": sum(len(v) for v in ctx.buildings.values()),
                "castle": 1 if ctx.castle else 0,
                "barracks": len(ctx.buildings.get("barracks", [])),
                "stable": len(ctx.buildings.get("stable", [])),
                "blacksmith": len(ctx.buildings.get("blacksmith", [])),
                "siege_workshop": len(ctx.buildings.get("siege_workshop", [])),
                "watchtowers": len(ctx.buildings.get("watchtower", [])),
                "houses": len(ctx.buildings.get("house", [])),
            },
            "upgrades": ", ".join(getattr(player, "upgrades", {}).keys()) or "None",
            "production_queue": ", ".join(production_parts) if production_parts else "None",
            "current_tasks": [],
        }

    # --- Internals ---

    def _tick(self, player):
        ctx = GoalContext.build(self.game, player)
        personality = getattr(player, "ai_personality", "balanced")

        # 1) Score goals
        scored = []
        for goal in self.goals:
            try:
                base = goal.score(ctx)
            except Exception as e:
                debug_log.log(
                    f"AI {player.name}: goal {goal.name}.score raised: {e}\n{traceback.format_exc()}",
                    "AI",
                )
                continue
            if base > 0:
                weighted = base * get_weight(personality, goal.category)
                scored.append((weighted, base, goal))

        scored.sort(key=lambda x: x[0], reverse=True)
        self.last_scores[player] = [(w, b, g.name) for w, b, g in scored]

        # 2) Two lanes (§7 P2): the best behavior goal (defend/attack/scout)
        # sets the army's mode, and — independently — the best action goal
        # that succeeds spends the economy. Pre-split, one slot per tick meant
        # AttackGoal's always-succeeding floor starved build/train goals
        # (stable lost 557/560 scored ticks; battery showed it was systemic).
        chosen_behavior = None
        chosen_action = None
        for weighted, base, goal in scored:
            lane_is_behavior = getattr(goal, "kind", "action") == "behavior"
            if lane_is_behavior:
                if chosen_behavior is not None:
                    continue
            elif chosen_action is not None:
                continue
            try:
                if goal.execute(ctx):
                    if lane_is_behavior:
                        chosen_behavior = goal
                    else:
                        chosen_action = goal
            except Exception as e:
                debug_log.log(
                    f"AI {player.name}: goal {goal.name}.execute raised: {e}\n{traceback.format_exc()}",
                    "AI",
                )
            if chosen_behavior is not None and chosen_action is not None:
                break
        self.last_chosen_behavior[player] = chosen_behavior
        self.last_chosen_action[player] = chosen_action
        # Panel/back-compat "the" chosen goal: the spend if one fired, else the mode
        chosen = chosen_action or chosen_behavior
        self.last_chosen[player] = chosen

        # 3) Sub-brains run regardless, reading the same snapshot. Each in its
        #    own try so one failure can't take the others down with it.
        self._tick_counter[player] = self._tick_counter.get(player, 0) + 1

        # LOD: scouting only needs to react every other strategic tick (1 s).
        if self._tick_counter[player] % 2 == 0:
            try:
                self.scout_brain.update(player, self.tick_timer[player])
            except Exception as e:
                debug_log.log(
                    f"AI {player.name}: scout_brain.update raised: {e}\n{traceback.format_exc()}",
                    "AI",
                )

        try:
            self.worker_brain.assign_idle_workers(ctx)
        except Exception as e:
            debug_log.log(
                f"AI {player.name}: worker_brain.assign_idle_workers raised: {e}\n{traceback.format_exc()}",
                "AI",
            )

        try:
            should_attack = isinstance(chosen_behavior, AttackGoal)
            self.military_brain.update(ctx, should_attack=should_attack)
        except Exception as e:
            debug_log.log(
                f"AI {player.name}: military_brain.update raised: {e}\n{traceback.format_exc()}",
                "AI",
            )
