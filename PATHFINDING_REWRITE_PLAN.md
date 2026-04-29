# P2 (Revised): Scrap Pathfinding, Start Fresh

## Why the Incremental Fix Failed

The gathering congestion fix (spread positions + right-of-way collisions) made workers get stuck worse than before. The root problem isn't just gathering — the **entire pathfinding + collision + movement pipeline is fragile**. Layering more special cases on top of a brittle system creates new failure modes faster than it fixes old ones.

Core issues that can't be fixed incrementally:

1. **Movement system is a patchwork** — LOS, A*, fallback direct, sliding, escape directions, separation forces, stuck detection, watchdog recovery — each added to fix the previous one's failures. They interact in unpredictable ways.
2. **Collision and pathfinding fight each other** — A* plans a path, then the collision system deflects the unit off it, then the unit looks stuck, then the watchdog teleports it. None of these systems know what the others are doing.
3. **State management is scattered** — `is_engaging`, `is_gathering`, `is_dropping_off`, `gathering_target`, `previous_gathering_target`, `destination`, `path`, `path_target`, `has_los`, `is_fallback_movement`, `_needs_separation`, `_stuck_detector` — too many flags, too many places that read/write them, too many edge cases where they desync.
4. **No separation of concerns** — Pathfinding, steering, collision avoidance, and task management are all entangled across `pathfinding.py`, `movement_system.py`, `collision_system.py`, `gathering_manager.py`, and `selection_manager.py`.

## Strategy: Replace with a Clean 3-Layer Architecture

```
Layer 1: PATHFINDING  (strategic)  — A* on static grid, returns waypoints
Layer 2: STEERING     (tactical)   — Follows waypoints, local obstacle avoidance
Layer 3: TASKS        (behavioral) — Gather, build, attack, drop-off state machines
```

Each layer has a single responsibility. No layer reaches into another's state.

---

## Layer 1: Pathfinding (static A*)

**File**: `systems/pathfinding.py` (rewrite)

- A* on a **static obstacle grid only** (buildings, resources, terrain)
- Grid cell size = 20 (current GRID_SIZE from config)
- **Input**: `(start_x, start_y)`, `(goal_x, goal_y)`, `unit_radius`, optional `ignore_targets` list
- **Output**: list of `(x, y)` waypoints, or `None` if unreachable
- **No unit-unit awareness** — units are dynamic, not static obstacles
- **Dirty flag** — only rebuild spatial grid when buildings/resources change
- **No caching** — paths are cheap at grid_size=20 and world state changes constantly
- **Goal relaxation** — if exact goal is inside a static obstacle, find nearest walkable cell and return path to that
- Drop all special-case kwargs (`gathering_target`, `building_target`, `drop_off_target`) — instead accept a simple `ignore_objects: list` that are excluded from collision checks

### Key simplifications vs current:
- Remove `_find_closest_reachable_position` (goal relaxation handles it)
- Remove `_is_position_permanently_blocked` (just try pathfinding, if it fails, it fails)
- Remove path caching (rebuild is cheap, stale cache causes bugs)
- Remove LOS sampling from pathfinder (that's Layer 2's job)

---

## Layer 2: Steering (new file)

**File**: `systems/steering.py` (new)

A single `update(unit, delta_time)` function that runs every frame for every moving unit.

### State machine per unit (3 states):
```
FOLLOWING_PATH → arrived at final waypoint → ARRIVED
FOLLOWING_PATH → path blocked by unit      → LOCAL_AVOIDANCE
LOCAL_AVOIDANCE → clear ahead               → FOLLOWING_PATH
```

### FOLLOWING_PATH
- Move toward current waypoint at `movement_speed`
- When within `waypoint_tolerance` (8px), advance to next waypoint
- **Lookahead**: check if next movement step would collide with another unit
  - If yes → enter LOCAL_AVOIDANCE
  - If no → proceed

### LOCAL_AVOIDANCE
- Use **simple velocity obstacle** approach:
  - Compute desired velocity (toward waypoint)
  - For each nearby unit (spatial hash lookup), compute avoidance force
  - Blend desired + avoidance = actual velocity
- **Priority rules** (who yields):
  - Carriers (resource_amount > 0) never yield — highest priority
  - Units on a path yield to stationary/gathering units
  - Same priority → unit with lower entity ID wins (deterministic)
- **Timeout**: if stuck in avoidance for >2s, request repath from Layer 1
- **No sliding along buildings** — that's what paths are for. If a unit hits a building, it's a bad path → repath.

### Key simplifications vs current:
- Remove `collision_system.py` entirely (or reduce to building-only checks)
- Remove `_calculate_slide_position`, `_find_escape_direction`, `separate_overlapping_units`, `apply_separation_to_unit`
- Remove `unit_watchdog.py` — steering handles stuck detection inherently
- Remove `has_los`, `is_fallback_movement`, `_needs_separation` from unit state

### Spatial hash for units:
- Cell size = 48 (already exists in collision_system, move to steering)
- Rebuilt once per frame
- `get_nearby(x, y, radius)` returns units within range

---

## Layer 3: Tasks (state machines)

**File**: Refactor into `systems/task_system.py` (new) or clean up existing files

Each task is a simple state machine. Tasks set `unit.path` by calling Layer 1, then Layer 2 follows the path. Tasks check arrival and transition states.

### Gather task:
```
MOVING_TO_RESOURCE → within gather_distance → GATHERING
GATHERING          → inventory full         → MOVING_TO_DROPOFF
MOVING_TO_DROPOFF  → within dropoff_distance → DROPPING_OFF
DROPPING_OFF       → timer elapsed          → MOVING_TO_RESOURCE (loop)
```

- **Spread positions**: computed at MOVING_TO_RESOURCE entry (same `reserve_gathering_position` idea, but simpler — just offset the pathfind goal)
- **Resource depletion**: if target depleted during GATHERING → go idle or find next

### Build task:
```
MOVING_TO_SITE → within build_distance → BUILDING
BUILDING       → construction complete → IDLE
```

### Attack task:
```
MOVING_TO_TARGET → within attack_range → ATTACKING
ATTACKING        → target moves away   → MOVING_TO_TARGET
ATTACKING        → target dead         → IDLE
```

### Key simplifications vs current:
- Remove `is_engaging` flag — replaced by task state
- Remove `previous_gathering_target` — task machine handles the loop
- Remove `last_task` — task machine IS the task
- `unit.stop()` and `clear_all_movement_state()` become `unit.cancel_task()` — one method, one behavior

---

## Unit State (simplified)

Replace current 15+ flags with:

```python
class Unit:
    # Movement (owned by Layer 2 - steering)
    path: list          # Waypoints from pathfinder
    path_index: int     # Current waypoint
    velocity: Vector2   # Current movement velocity

    # Task (owned by Layer 3 - tasks)
    task: Task | None   # Current task object (GatherTask, BuildTask, AttackTask, MoveTask)

    # Combat (kept as-is, works fine)
    attack_range, attack_speed, damage, etc.

    # Inventory (kept as-is)
    resource_type, resource_amount, max_capacity
```

Everything else (`is_engaging`, `is_gathering`, `is_dropping_off`, `gathering_target`, `drop_off_target`, `building_target`, `has_los`, `is_fallback_movement`, `in_combat`, `_needs_separation`, `_stuck_detector`, etc.) moves into the Task objects or disappears entirely.

---

## Files to Create/Modify/Delete

| Action | File | Notes |
|--------|------|-------|
| **Rewrite** | `systems/pathfinding.py` | Clean A* with goal relaxation, no special cases |
| **New** | `systems/steering.py` | Waypoint following + local avoidance + spatial hash |
| **New** | `systems/tasks.py` | Task state machines (Gather, Build, Attack, Move) |
| **Simplify** | `entities/unit.py` | Remove flag soup, add `task` field |
| **Simplify** | `systems/movement_system.py` | Becomes thin wrapper calling `steering.update()` |
| **Delete** | `systems/collision_system.py` | Absorbed into steering.py |
| **Delete** | `systems/unit_watchdog.py` | Steering handles stuck detection |
| **Simplify** | `systems/gathering_manager.py` | Keep farm ticking, move gather logic to GatherTask |
| **Simplify** | `managers/selection_manager.py` | Commands create Task objects instead of setting flags |
| **Simplify** | `systems/ai/worker_brain.py` | Commands create Task objects |

---

## Implementation Order

### Phase 1: Pathfinding rewrite (standalone, testable)
1. Rewrite `systems/pathfinding.py` with clean A* + goal relaxation
2. Add `ignore_objects` parameter instead of `gathering_target`/`building_target`/`drop_off_target`
3. Verify: paths are found, grid rebuilds on dirty flag

### Phase 2: Steering system (replaces collision + movement)
1. Create `systems/steering.py` with spatial hash + waypoint following + local avoidance
2. Wire into game loop (replace movement_system.update + collision calls)
3. Verify: units follow paths, avoid each other, don't get stuck

### Phase 3: Task system (replaces flag soup)
1. Create task classes: `MoveTask`, `GatherTask`, `BuildTask`, `AttackTask`
2. Refactor `Unit` to use `task` field
3. Update `selection_manager` commands to create tasks
4. Update `worker_brain` to create tasks
5. Verify: full gather cycle works, build works, attack works

### Phase 4: Cleanup
1. Delete `collision_system.py`, `unit_watchdog.py`
2. Remove dead code from `gathering_manager.py`, `movement_system.py`
3. Update CLAUDE.md

---

## Rollback Plan

Before starting, create a git branch `pathfinding-rewrite` off current `ai-v2`. If the rewrite breaks things worse, we can always go back. Each phase should be a separate commit so we can bisect.

---

## Open Questions

1. **Movement system**: Does `movement_system.py` do anything besides calling collision + moving toward destination? If so, what needs to be preserved?
2. **Formation movement**: Group right-click uses hexagonal offsets — should this become a `FormationMoveTask` or stay as offset calculation in selection_manager?
3. **Combat re-engagement**: When a target moves out of range during ATTACKING, should the unit chase indefinitely or give up after some distance?
4. **AI integration**: `simple_ai.py` calls `worker_brain` which calls `selection_manager._gather_from_target`. With the task system, AI would create tasks directly — is that cleaner or do we want to keep the indirection?
