# CLAUDE.md

Guidance for Claude Code when working with this RTS game codebase.

## Quick Start

```bash
python main.py               # Run game
pip install -r requirements.txt  # Install deps

# Debug mode (writes to debug.dat)
# DEBUG_TO_FILE = True in core/config.py (on by default)

# Headless performance benchmark (4 AI players, no window)
python tools/benchmark_ai_spectator.py --seconds 300 --speed 5
```

## Architecture Overview

### Core Systems
- **Coordinates**: Hex grid (row, col) for tile rendering/terrain (`world/map.py`), World (x, y) for
  smooth movement and combat/collision math.
- **Pathfinding**: Jump Point Search over a separate **square navigation grid**
  (`systems/pathfinding.py`, `GRID_SIZE = 20` world units/cell in `core/config.py`) laid on top
  of the hex render map — not the hex grid itself. Static blockers only (buildings, resources,
  construction sites, terrain) with **incremental** per-object updates
  (`notify_blocker_added/removed`; `mark_dirty()` is the bulk fallback); a static terrain
  bitmap + connected-components reject unreachable goals O(1). Tight budgets
  (`PATHFINDING_FRAME_BUDGET_MS=10`, `PATHFINDING_MAX_REQUEST_MS=12`) with a **cross-frame
  command queue** (over-budget commands defer, never silently fail); a queued search that
  outruns its time slice **suspends its frontier and resumes** next retry, so cross-map
  paths complete over several frames without any single frame paying for the whole search. Group moves of 8+ units
  ride one shared **flow field** (`systems/flow_field.py`). Unit-unit avoidance is context
  steering + right-of-way in the collision/movement systems, not baked into the search.
- **Combat**: Type effectiveness via `strong_against`/`weak_against` tags + Slash/Pierce/Siege
  multipliers (`systems/combat_rules.py`); auto-approach to attack range; tech upgrades modify
  effective stats (`systems/upgrade_effects.py`).
- **Resources**: Gold/Stone 1/s, Wood 2/s, Food 3/s gathering rates (`GATHERING_RATES`).
- **Collision**: 96px spatial-bucketed unit/static index (`systems/collision_system.py`), ~2-unit
  buffer, sliding along obstacles plus explicit pairwise separation push. A stuck-unit watchdog
  (`systems/unit_watchdog.py`) recovers units that make no progress for several seconds.

## File Structure

```
core/           - game.py (main loop), config.py, game_state.py
entities/       - game_object.py (base), unit.py, building.py, resource.py,
                  construction_site.py, player.py, data_loader.py (JSON -> objects)
systems/        - pathfinding, movement, collision, combat, combat_rules, building,
                  gathering_manager, production_manager, research_manager,
                  upgrade_effects, projectile_system, fog_of_war, rendering_system,
                  unit_watchdog, worker_task_system, ai/ (see below)
systems/ai/     - military_brain.py, worker_brain.py, scout_brain.py,
                  building_placer.py, economy_helpers.py
systems/ai/utility/ - ai.py (orchestrator), context.py (per-tick snapshot),
                  goal.py, personality.py, goals/{economy,military,tactical}.py
managers/       - selection_manager.py, sprite_manager.py, sound_manager.py, save_manager.py
ui/             - ui_manager.py (delegates to ui/components/*), minimap.py,
                  floating_ui.py, ai_debug_panel.py
world/          - map.py (hex terrain + coordinate conversion), camera.py
data/           - units.json, buildings.json, techs.json (content, not code)
tools/          - benchmark_ai_spectator.py (headless perf benchmark), sprite pipeline scripts
```

## Content

- **Units** (`data/units.json`): worker, warrior, archer, spearman, cavalry, ram, healer.
  `healer` (requires `temple`) is fully live: it auto-heals the most-wounded nearby ally
  (`combat_system._update_healer`); the AI trains it via `TrainHealerGoal` and keeps it
  trailing the army, never in combat commands (`military_brain`).
- **Buildings** (`data/buildings.json`): castle, barracks, farm, house, lumbermill, mine, quarry,
  watchtower, stable, blacksmith, siege_workshop, temple (trains the healer; the AI builds
  it via `BuildTempleGoal`, category "support").
  `wall`/`wooden_wall`/`gate` are **fully implemented** (drag-line placement, AI walling, gate
  toggle, nav sealing) but currently **disabled via `buildable: false`** pending
  orientation-aware sprites — flip the flags to re-enable (see MASTER_PLAN §8.10).
- **Tech tree** (`data/techs.json`): 6 blacksmith upgrades (gather rate, armor, melee/ranged
  damage, siege damage) applied via `systems/upgrade_effects.py` and researched through
  `systems/research_manager.py`. AI research goals live in
  `systems/ai/utility/goals/military.py`.
- **AI personalities**: rusher / boomer / turtle / balanced (`systems/ai/utility/personality.py`).

## AI Architecture (Utility AI)

`systems/ai/utility/ai.py` is the orchestrator. Each AI player ticks independently on a staggered
0.5s interval (`UtilityAISystem.TICK_INTERVAL`):

1. Build a `GoalContext` snapshot (`context.py`) — workers, military, buildings, construction
   sites, resources, pop, cost/tech data.
2. Score every `Goal` in `goals/{economy,military,tactical}.py` against the snapshot, weight by
   personality category (`personality.py`), sort descending.
3. Execute goals top-down until one succeeds (a goal may no-op and fall through, e.g. no idle
   worker available).
4. Always run the sub-brains: `scout_brain` (exploration), `worker_brain` (idle worker
   assignment), `military_brain` (defense/micro/attack commands — attacks only if the chosen
   goal was `AttackGoal`).

Per-goal and per-brain calls are individually wrapped in try/except so one broken goal can't take
the rest of the tick down — failures log to `debug.dat` under category `AI`.

The blackboard contract is enforced: goals and sub-brains read only the `GoalContext`
snapshot (never `game.units`/`game.buildings` directly) — `tests/test_ai_contract.py`
fails on violations. AI ticks run with deferred pathfinding: path commands enqueue into
the cross-frame queue instead of searching inside the tick.

## Debug Keys
- **F1**: Select/cycle idle workers (centers camera; top-bar badge shows count)
- **F3**: Pathfinding/coordinate overlay
- **F4**: AI debug panel (shows chosen goal + top-5 scores per AI player)
- **F5 / F9**: Save / load (slot 0) — partial state only, see Known Gaps below
- **F6**: Toggle fog of war
- **[ / ]**: Decrease/increase game speed (1x-5x)

## Key Configuration (core/config.py)
```python
MAP_WIDTH = 70; MAP_HEIGHT = 70        # hex tiles
TILE_WIDTH = 64; TILE_HEIGHT = 56

GRID_SIZE = 20                          # nav-grid cell size, world units
PATHFINDING_MAX_EXPANSIONS = 12000
PATHFINDING_MAX_REQUEST_MS = 12         # ceiling for one inline path request
PATHFINDING_FRAME_BUDGET_MS = 10        # ceiling for inline pathfinding per frame
PATHFINDING_QUEUE_FRAME_MS = 10         # ceiling for the queue drain per frame;
                                        # over-budget searches suspend + resume
PATH_CACHE_MAX_ENTRIES = 4096

GATHERING_RATES = {"gold": 1, "stone": 1, "wood": 2, "food": 3}
WORKER_CAPACITY = {"gold": 10, "stone": 10, "wood": 20}

DEBUG_TO_FILE = True                    # writes to debug.dat
PERF_STATS_ENABLED = False              # flip on for utils/perf_stats counters

DEFAULT_GAME_SPEED = 1.0; MAX_GAME_SPEED = 5.0
```

## Current Status & Active Plan

Core gameplay (selection, movement, combat, gathering, building, production, save/load-lite,
fog of war, formations, control groups, unit stances) works end to end. Content is a full
7-unit / 13-building / 6-tech roster with a personality-driven utility AI.

**The active, single source of truth for what's being worked on next is
[MASTER_PLAN.md](MASTER_PLAN.md).** It covers, with measured profiling evidence:
- Why the game stutters at scale (pathfinding ~48% of CPU, O(n²) target/LOS/collision scans, a
  full nav-grid + path-cache rebuild on every world change, fog of war walking the full grid every
  frame) and the phased fix (cheap local wins → incremental nav + JPS → local steering rework →
  AI shared-perception/LOD/squads → flow fields for group orders).
- The preserved non-performance backlog (healer healing, wall-as-gate, save/load completeness,
  defensive-stance freeze bug, sound coverage, test coverage).

Do not maintain a second roadmap or changelog in this file — update MASTER_PLAN.md instead, and
rely on `git log` for history.

## Known Gaps (stable, not currently being worked)
- **Save/Load** is save format **v3** (`managers/save_manager.py`, still loads v1/v2):
  terrain, units, buildings, construction sites, resources, production/research queues,
  rally points, gates, stances, fog (explored), sim clock, stats, and tree timers all
  persist. Reachable from the pause menu, the main menu (multi-slot screen), and F5/F9
  (slot 0). Deliberately **not** saved — each self-heals within an AI tick of resuming:
  AI brain state, worker task/gather targets, combat targets, in-flight paths.
- Units can still get stuck at tight spots between static obstacles in rare cases; the
  `unit_watchdog` recovers them (teleport-to-safe-position) after several seconds rather than
  routing around cleanly — see MASTER_PLAN.md's local-steering phase for the real fix.
