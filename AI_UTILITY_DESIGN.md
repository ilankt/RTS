# AI Rewrite — Utility AI Design

The old 4-phase state machine has been replaced with a goal-scored utility AI.

## Why

The existing AI's "adaptive build order" is a fixed priority list. Personalities are threshold tweaks, not real strategic differences. The orchestrator hard-codes which units can be trained from which buildings. A broad `try/except` masked a missing-import bug for an unknown duration.

A utility AI fixes all of these:
- **Reactive**: each tick re-scores everything against current state. If something changes (we lose workers, an enemy approaches, gold runs out), the next chosen action reflects that.
- **Personality-driven**: weights on goal *categories* mean a "rusher" naturally builds barracks earlier, and a "boomer" naturally trains more workers, without per-personality `if`-ladders.
- **Content-extensible**: a new unit type = a new goal class. No orchestrator surgery.
- **Observable**: every tick we know which goals scored what, so the F4 debug panel can show the AI's "thought process."
- **Robust**: per-goal try/except. One broken goal doesn't kill the others.

## Architecture

```
systems/ai/utility/
    ai.py            — UtilityAISystem (orchestrator)
    context.py       — GoalContext (per-tick game-state snapshot)
    goal.py          — Goal base class
    personality.py   — category weights per personality
    goals/
        economy.py   — worker / farm / house / mine / quarry / lumbermill
        military.py  — barracks / stable / warrior / archer / spearman / cavalry
        tactical.py  — scout / defend / attack
```

Existing modules carry over unchanged:
- `worker_brain.py` — assigns idle workers each tick
- `military_brain.py` — handles per-unit micro (retreat, kite, focus-fire, attack moves)
- `scout_brain.py` — exploration tracking + scout assignment
- `building_placer.py` — finds positions for new buildings

## Roles

The orchestrator picks **strategic decisions**: "should we start a barracks now?", "should we train a cavalry now?", "should we send the army to attack?"

The sub-brains do **continuous execution**: an idle worker gets a job every tick regardless of which goal won; military units micro themselves; the scout keeps exploring.

So a goal usually emits a *single command* (start producing X, place a construction site, switch to attack mode). The brains keep the world ticking.

## Control flow per AI tick

```
1. Build GoalContext snapshot (workers, military, buildings, construction sites,
   resources, pop, cost_data, helpers).
2. For each goal: base_score = goal.score(ctx); weighted = base_score * personality_weight[category].
3. Sort by weighted score, descending.
4. For each goal in order: if execute(ctx) returns True, that's our action; stop.
   (Fall through on False — e.g., no idle worker available — to the next-best goal.)
5. Run scout_brain.update(), worker_brain.assign_idle_workers().
6. Run military_brain.update(player, should_attack=isinstance(chosen, AttackGoal)).
7. Stash chosen goal + scores for debug panel.
```

Each step (2, 4, 5, 6) is wrapped in its own try/except so a single broken goal or brain doesn't kill the rest. Exceptions are logged with traceback to `debug.dat`.

## Goal interface

```python
class Goal:
    name = "<unset>"           # short identifier
    category = "economy"       # economy | military | tactical | support

    def score(self, ctx: GoalContext) -> float:
        """Urgency right now. 0 means 'don't run'. Higher beats lower."""
        return 0.0

    def execute(self, ctx: GoalContext) -> bool:
        """Take the action. Return True if something happened, False to fall
        through to the next-highest-scoring goal."""
        return False
```

Goals are stateless — score is recomputed fresh from `ctx` every tick. State that matters (already-in-progress construction, queued production) lives on the game objects and is read via `ctx`.

## GoalContext

Built once per tick per player. Used by every goal that tick.

Fields:
- `game`, `player`
- `workers`, `military`, `castle`
- `buildings: dict[name -> list[Building]]`
- `construction_sites: list[ConstructionSite]` (this player's only)
- `site_types: set[str]` (e.g. `{"barracks", "house"}`)
- `resources: dict[str, int]` (snapshot, not the live dict)
- `cost_data: dict[str, dict]` (game.game_data["costs"])
- `pop_current`, `pop_max`

Helpers:
- `can_afford(item_name) -> bool`
- `has_pop_space() -> bool`
- `has_construction_in_progress(building_name) -> bool`
- `find_idle_worker() -> Unit | None`

## Personality weights

```python
PERSONALITY_WEIGHTS = {
    "rusher":   {"economy": 0.7, "military": 1.5, "tactical": 1.4, "support": 0.5},
    "boomer":   {"economy": 1.5, "military": 0.8, "tactical": 0.8, "support": 1.2},
    "turtle":   {"economy": 1.0, "military": 1.0, "tactical": 0.7, "support": 1.5},
    "balanced": {"economy": 1.0, "military": 1.0, "tactical": 1.0, "support": 1.0},
}
```

`weighted_score = base_score * PERSONALITY_WEIGHTS[personality][goal.category]`.

A rusher's `BuildBarracksGoal` (military, base 90) beats their `BuildHouseGoal` (economy, base 70) at 90×1.5=135 vs 70×0.7=49. A boomer flips it: 90×0.8=72 vs 70×1.5=105.

## Initial goal catalog

### Economy
- **TrainWorker** — base 100 when zero, ramping down. Score = `max(0, 6 - workers) * 20 + 30` while pop space available. 0 if castle is already producing.
- **BuildFarm** — 80 if no farm, 40 if food < 100 and farms < 3, else 0. 0 if farm in construction.
- **BuildHouse** — 90 if pop_max - pop_current ≤ 1, 50 if ≤ 3, else 0.
- **BuildLumbermill** — 35 if no lumbermill and we have ≥ 3 workers and gold > 100.
- **BuildMine** — 35 if no mine and we have gold workers (or want them).
- **BuildQuarry** — 30 if no quarry and stone < 100.

### Military
- **BuildBarracks** — 90 if no barracks and we have ≥ 2 workers, 0 once one exists or in progress.
- **BuildStable** — 50 if has_barracks and no stable and we have ≥ 4 workers.
- **TrainWarrior** — 50 if barracks idle and warrior fraction < 0.4.
- **TrainArcher** — 50 if barracks idle and archer fraction < 0.3.
- **TrainSpearman** — 50 if barracks idle and spearman fraction < 0.3.
- **TrainCavalry** — 50 if stable idle and cavalry < 3.

### Tactical
- **DefendBase** — 200 if any enemy within DEFENSE_RADIUS of castle. (Highest priority — overrides everything.)
- **Attack** — 70 if we have ≥ 6 military, scaling up with army size. Triggers `military_brain.update(should_attack=True)`.
- **Scout** — 20 if exploration < 50%, 0 otherwise. (Mostly handled by `scout_brain` already; this goal is a no-op shell to keep the panel honest.)

Numbers above are first-pass; expect them to need tuning once we see games play out.

## Migration

Status: complete. `core/game.py` imports `UtilityAISystem`, and the old `simple_ai.py` module has been deleted.

The current AI public interface remains `update(delta_time)`, `get_ai_debug_info(player)`, and `invalidate_memory_cache(player=None)`.

## Testing

Tests live in `tests/test_utility_ai.py`. Initial coverage:
- `BuildFarmGoal.score()` returns 80 when no farm exists, 0 when one is being built.
- `TrainWorkerGoal.score()` returns 0 when castle is producing.
- Personality weighting: BuildBarracksGoal weighted-score for rusher > balanced > boomer.
- **Integration**: instantiate a real Game, run UtilityAISystem for N ticks, assert that a barracks gets built.

The integration test is the one the original test suite was missing.

## Out of scope

- Tech research (will be added as a `ResearchTechGoal` after the tech system is wired)
- Healer healing logic (separate feature)
- Save/load round-trips (depends on stable AI state shape; deferred)
- Goal cooldowns (handled implicitly via "is in progress" checks; revisit if oscillation appears)
