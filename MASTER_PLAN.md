# RTS Master Plan — Pathfinding & AI Performance Overhaul

> Single source of truth for the game's technical direction. Focus: make the sim
> fast and smooth at scale (hundreds of units), and make the AI both cheaper and
> better. Supersedes and replaces the old `IMPROVEMENT_PLAN.md` and
> `AI_UTILITY_DESIGN.md` (deleted). Status: **planning**, written 2026-07-09.

---

## 1. The problem, in one line

The game stutters and feels sluggish — multi-hundred-millisecond hitches, worst
when many units exist — because pathfinding, the AI brains, collision, and fog
all do **O(n²) or full-world work every frame**, pathfinding is allowed to burn
**180 ms in a single frame**, and the whole navigation grid + path cache is
**rebuilt from scratch on every world change**.

This is not a tuning problem. It is an architecture problem with a clear,
evidence-backed fix path.

---

## 2. Evidence (measured, not guessed)

Headless benchmark (`tools/benchmark_ai_spectator.py`, 4-AI spectator, 300 sim
seconds @ 5× speed) and a `cProfile` pass (150 sim seconds) at just **~45–48
units** — i.e. *before* the "lots of units" regime the user complains about:

| Metric | Value | Meaning |
|---|---|---|
| Update avg | **42.7 ms/frame** | ~23 FPS of pure sim, before any rendering |
| Update p95 | **182 ms/frame** | ~5 FPS at the 95th percentile — the stutter |
| Update max | **492 ms/frame** | ~0.5 s freeze |
| Single AI tick max | **478 ms** | one AI tick = essentially the whole worst frame |
| A* expanded cells | **1,314 / call avg** | fine grid → search explosion |
| A* "too_expensive" | **15 % of calls** | 1-in-7 path requests fail → units stall/retry |
| Full nav rebuilds | **96× in 300 s** (~every 3 s) | each wipes the whole path cache |

**Where the CPU actually goes** (cProfile self-time, 74.5 s total):

| Rank | Function | Self time | Root cause |
|---|---|---|---|
| 1 | `map.world_to_grid` + `grid_to_world` | **~21 s (28 %)** | hex coord conversion, run millions of times by terrain probes; `world_to_grid` does a **9-neighbor refinement** calling `grid_to_world` 9× per call (45 M calls) |
| 2 | Pathfinding total (`find_result`) | **~36 s cumulative (48 %)** | per-unit A* on a 20 px grid; interaction pathing tries up to 33 candidate points |
| 3 | AI total (`ai._tick`) | **~29 s cumulative (41 %)** | almost entirely `military_brain._command_attack` → `_attack_target` → **22 s of pathfinding** (mass path issuance in one tick) |
| 4 | `fog_of_war._mark_visible_around` | **9.8 s (13 %)** | full-grid fade + per-entity circular re-stamp **every frame**, per player |
| 5 | `unit.has_line_of_sight` | **5.0 s** | O(samples × all-obstacles) ray march, obstacle list = `buildings + all units + resources` |
| 6 | `upgrade_effects.effective_*` | **~4.5 s** | effective combat stats recomputed from scratch on every read, uncached |

Two headline conclusions: **pathfinding is ~half the frame and coordinate
conversion is a third of it**, and **the worst single-frame hitches are AI ticks
that issue a whole army's worth of path requests at once.**

---

## 3. Root-cause inventory

Grouped by subsystem. Severity is impact-at-scale. `file:line` are anchors, not
exact after edits.

### A. Pathfinding (`systems/pathfinding.py`, `world/map.py`, `core/config.py`)

| # | Where | Problem | Sev |
|---|---|---|---|
| A1 | `map.world_to_grid` / `grid_to_world` | 9-neighbor hex refinement called millions of times from terrain probes; **28 % of all CPU**. Pathfinding doesn't need hex fidelity — it needs a boolean "is this cell walkable". | **critical** |
| A2 | `NavigationGrid.rebuild` + `Pathfinding.mark_dirty` | Any world change (building destroyed, **resource depleted**, construction site change) rebuilds *all* blocker buckets **and wipes `_walkable_cache`, `_terrain_probe_cache`, and the entire `_path_cache`**. Resources deplete constantly → 96 full wipes / 300 s → path stampede. | **critical** |
| A3 | `config.PATHFINDING_FRAME_BUDGET_MS=180`, `PATHFINDING_MAX_REQUEST_MS=150` | A single frame may legally spend 180 ms on paths; one request 150 ms. This *is* the half-second hitch. Overflow requests are **rejected** (`too_expensive`) rather than queued, so units silently fail to move and fall to the watchdog. | **critical** |
| A4 | `_astar` on 20 px grid | ~1,314 cells/call, 15 % capped. No Jump Point Search, no hierarchy → open-terrain symmetry explosion. | high |
| A5 | `_smooth_path` / `segment_clear` | Path smoothing re-samples segments (11–14 s cumulative); runs on every built path. | high |
| A6 | `issue_interact` → `_find_interaction_path` | Tries up to 33 candidate contact points, each a potential A*. Called per attack/gather/build/dropoff. | high |
| A7 | group move orders | N selected units → **N independent A* searches** to the same destination. No coalescing / flow field. | high |

### B. Local movement, collision & steering (`systems/movement_system.py`, `systems/collision_system.py`, `systems/unit_watchdog.py`)

| # | Where | Problem | Sev |
|---|---|---|---|
| B1 | `movement_system._reevaluate_movement_strategy` / `_use_los_strategy` | Builds `game.buildings + [all engaged units] + game.resources` **per unit** and runs `has_line_of_sight` over it → **O(units²)** when many units fight. | **critical** |
| B2 | `unit.has_line_of_sight` | Samples every 16 px; for each of 3 points/sample iterates the whole obstacle list with a `sqrt`. | high |
| B3 | `movement_system._move_direct` | Seeks the destination with **no arrival/deceleration term** → units overshoot, overlap the target, get shoved out, re-approach → oscillation. The whole push-out block (lines ~417–450) is a missing-arrival workaround. | high |
| B4 | `collision_system` | Position-space slide + separate pairwise push + `_make_static_signature` rebuilt (id-tuple of all objects) **per query**. No arrival, no right-of-way (except a drop-off special case). | high |
| B5 | `unit_watchdog._find_nearby_safe_position` | On stuck, probes 180 candidate positions, each rebuilding `buildings+resources+sites` and running `hypot` over all. Units get stuck in **bursts** (after A2 cache wipes) → all recover in one frame → hitch. Recovery = **teleport across the map** (visible artifact). | high |
| B6 | `game.update` game-speed handling | `delta_time = raw_dt * game_speed` with **no substepping**; at 5× the movement step is 5× larger → tunneling through obstacles / collision misses. | medium |

### C. AI (`systems/ai/…`)

| # | Where | Problem | Sev |
|---|---|---|---|
| C1 | `military_brain.update` | Attack phase commands **all idle military in one tick**; each command pathfinds. This is the 478 ms AI-tick spike. Also full O(units+buildings) enemy scans (`_find_focus_fire_target`, `_find_enemies_near`, `_find_attack_target`) every tick per player. | **critical** |
| C2 | `combat_system.evaluate_combat_targets` | Every idle unit with no target scans **every** enemy unit + building every frame → **O(units²)** target acquisition. Same pattern for defensive-building auto-target and `find_optimal_attack_position` (rebuilds obstacle list 8× + allocates a throwaway class per call). | **critical** |
| C3 | Goals violate the context contract | `context.py` says "goals never re-scan the world," but `DefendBaseGoal`, `AttackGoal`, `TrainRamGoal`, and the `ResearchTechGoal` family read `ctx.game.units` / `ctx.game.buildings` directly every 0.5 s tick, per player. | high |
| C4 | `worker_brain._find_best_resource_to_gather` / `economy_helpers.best_resource_for_dropoff` | Nested O(resources × (buildings+units)) and O(resources²) scans per idle-worker assignment / dropoff scoring, every AI tick. | high |
| C5 | `scout_brain`, `building_placer`, `production_manager._is_valid_spawn_position`, `research_manager` | Per-tick / per-event full-entity list scans and ring searches (O(candidates × all-entities)). | medium |

### D. Rendering & fog (`systems/fog_of_war.py`, `systems/rendering_system.py`, `ui/minimap.py`)

| # | Where | Problem | Sev |
|---|---|---|---|
| D1 | `fog_of_war.update` | Runs **every frame, per player**: full 4,900-tile grid fade + per-entity circular re-stamp with `world_to_grid`+`grid_to_world`+`sqrt` per tile. **13 % of CPU headless**, worse with draw. | **critical** |
| D2 | `rendering_system._draw_fog_overlay` | Allocates a **fresh `pygame.Surface(SRCALPHA)` per fog tile per frame** (alpha only ever 150 or 255). | high |
| D3 | `rendering_system._draw_all_objects` | **No frustum culling**: concatenates + y-sorts *all* objects every frame and fog-checks every one (`get_visible_objects` exists but is unused in the draw path). | high |
| D4 | `rendering_system._render_sprite` | `pygame.transform.scale` per object per frame (map tiles are cached via `scale_tiles`; object sprites are not). | high |
| D5 | `minimap.draw` | Redraws every unit/building/resource dot every frame, unthrottled. | medium |

### E. Cross-cutting Python hygiene

| # | Where | Problem | Sev |
|---|---|---|---|
| E1 | `upgrade_effects.effective_*` (via `unit.can_attack`, `calculate_damage`) | Effective stats recomputed (generator over all upgrades) on every read, even with **zero upgrades**. | high |
| E2 | `worker_task_system._valid_*` | `resource in self.game.resources` etc. = **O(n) list membership** per active worker per frame → O(workers × resources). | high |
| E3 | `debug_logger.log` | f-strings are built eagerly at every call site in the movement/collision hot loops even for disabled categories (`MOVEMENT`/`COLLISION`/`AI` are filtered *after* the string is formatted). | medium |
| E4 | `projectile_system.update` | `list[:]` copy + `list.remove` per dead projectile → O(n²) on volley expiry; per-frame trail/particle dict allocation. | medium |
| E5 | Entities | No `__slots__`; heavy `hasattr`/`getattr` feature-probing on always-present attributes; per-pair `Vector2`/list churn feeding the GC. | medium |
| E6 | `combat_system.attack_trackers` | `dict` keyed by `id()` never purged on death → unbounded growth + `id()` reuse can suppress a new unit's first shot. | low |

---

## 4. Target architecture

Two clean layers, plus a shared-perception AI. Every symptom above maps onto one
of these.

```
                 ┌───────────────────────────────────────────────┐
   AI  ───────►  │ Blackboard (one world scan / tick, published)  │
 (utility +      │  • spatial hash of units   • influence maps    │
  squads +       │  • enemies-near-base       • idle-worker list  │
  LOD ticks)     └───────────────────────────────────────────────┘
                                   │ postures / target regions
                                   ▼
        GLOBAL ROUTING            LOCAL STEERING            EXECUTION
   ┌─────────────────────┐  ┌──────────────────────┐  ┌──────────────┐
   │ • incremental nav    │  │ • context steering    │  │ per-unit HFSM │
   │   (dirty regions)    │─►│ • arrival + stop      │─►│ Idle/Move/    │
   │ • JPS on the grid    │  │ • priority/right-of-way│  │ Attack/Gather │
   │ • flow field per     │  │ • neighbors via ONE   │  │ /Build/Flee   │
   │   group order        │  │   shared spatial hash │  └──────────────┘
   │ • request queue      │  └──────────────────────┘
   └─────────────────────┘
```

**Principles**
- **Global routing decides *where*, local steering decides *how to move this
  frame*.** Flow fields / A* never resolve unit-unit collision; steering never
  does long-range routing. (Every RTS-movement writeup — SC2, AoE — draws this
  line.)
- **Scan the world once per tick, publish, everyone reads.** No system rebuilds a
  neighbor list per unit.
- **Never do O(map) work on an O(1) change.** Nav updates are local/dirty-region.
- **Budget by measured wall-time and *queue* overflow — never freeze the frame.**
- Keep the **utility AI** for strategy (it's the right choice); do **not** migrate
  to behavior trees / GOAP. Add a cheap per-unit state machine for execution.

---

## 5. Execution plan (ordered by ROI ÷ risk)

Each phase is independently shippable and leaves the game working. Land them in
order; re-run the benchmark after each to confirm the win.

### Phase 0 — Make it measurable & safe (0.5 day, prerequisite)
- Add a dev toggle for `PERF_STATS_ENABLED`; wire `py-spy` into the workflow for
  flamegraphs on a real late-game state.
- Extend `tools/benchmark_ai_spectator.py` into a **perf regression gate**: assert
  `frame_max_ms` and `frame_p95_ms` stay under thresholds; run it in CI with
  `--fail-on-stall`.
- Extend the `reference_walkable()` cross-check in `tests/test_navigation.py` — it
  is the safety net for every incremental-nav change in Phase 2.

### Phase 1 — Cheap, high-ROI wins (2–4 days, low risk, no new architecture)
Kills the biggest constant and quadratic costs with local edits.

1. **Static walkable bitmap** (A1). Precompute a boolean walkable array per nav
   revision; `cell_walkable`/terrain probe becomes an array lookup. Drop the
   9-neighbor refinement in `world_to_grid` for pathfinding probes. *Expected:
   removes most of the 28 % coordinate-conversion cost.*
2. **Fog rework** (D1/D2). Throttle fog to ~5 Hz; precompute per-sight-radius
   offset masks; track a per-player set of currently-visible tiles (clear only
   those, not the whole grid); cache two fog surfaces (α=150/255) and blit a
   single cached overlay. *Expected: −13 %+ CPU, big draw win.*
3. **One shared spatial index** (B1/B2/C2/C5). Expose `collision` buckets as
   `query_nearby(x, y, r)` and route through it: `evaluate_combat_targets`,
   building auto-target, `find_optimal_attack_position`, `has_line_of_sight`
   candidate obstacles, `production._is_valid_spawn_position`, watchdog
   safe-position. *Expected: O(n²) → ~O(n) for target/LOS scans.*
4. **Cache effective stats** (E1). Memoize per unit keyed by a
   `player.upgrades_version`; fast-path zero upgrades to return the base value.
5. **Throttle re-acquisition** (C2). Combat units keep their target; re-scan only
   every ~0.25–0.5 s or when the target dies/leaves range.
6. **O(1) worker-task validity** (E2). Replace `x in self.game.<list>` with cheap
   per-object flags (`removed`, `hp <= 0`, `amount_remaining`).
7. **Rendering hygiene** (D3/D4/D5). Frustum-cull to camera bounds before
   sort/draw (use existing `get_visible_objects`); cache scaled sprites keyed by
   `(sprite, zoom)`; throttle minimap dot layer to a few Hz.
8. **Micro-hygiene** (E3/E4/E5/E6). Gate debug f-strings behind the category
   check; single-pass projectile filter; `__slots__` on `Unit`/`Building`/
   `Resource`; squared-distance comparisons in hot loops; `gc.freeze()` after
   `setup_game_objects`; purge `attack_trackers` on death.

### Phase 2 — Pathfinding structure: stop the stampede (3–5 days, medium risk)
1. **Incremental / dirty-region nav** (A2). Batch same-frame `mark_dirty` into one
   pass; add/remove single blockers instead of full rebuild; invalidate only
   `_walkable_cache` entries and `_path_cache` paths whose cells fall in the
   changed blocker's bbox; **never wipe the static-terrain bitmap**. Classify
   blockers static (terrain, completed buildings) vs dynamic (construction sites).
2. **Jump Point Search** in `_astar` (A4). Near-drop-in on the uniform grid;
   preserves optimality; keeps the heap, caches, and no-corner-cut rule. ~10×
   fewer expansions.
3. **Request queue + sane budgets** (A3/A6/C1). Replace "reject as
   `too_expensive`" with a FIFO/priority queue that carries requests across frames
   (player & on-screen first; 0.5 s AI sub-brain rescans last). Lower
   `PATHFINDING_FRAME_BUDGET_MS` to ~6–8 and `PATHFINDING_MAX_REQUEST_MS` to ~2–3
   *once JPS + the queue exist*. Add per-worker jitter to repath cooldowns so a
   cache event doesn't align every worker on one frame.
4. *(Optional multiplier)* Evaluate a **coarser routing grid** decoupled from the
   fine collision layer.

### Phase 3 — Local steering: fix stuck / teleport / bunch-up (3–5 days, medium)
1. **Arrival + stop-on-arrival** (B3). Deceleration slowing radius; arrived units
   stop and become low-priority obstacles. Removes destination pile-ups and the
   push-out oscillation hacks.
2. **Context steering** (B1/B4). 8–16 slot interest/danger map per moving unit;
   danger from the shared spatial hash. Replaces `_calculate_slide_position` /
   `_find_escape_direction` / the `_stuck_detector` machinery. This is the
   specific cure for the force-cancellation local-minimum stall.
3. **Priority / right-of-way** (B4/B5). Generalize the drop-off right-of-way into
   a global `carrier > mover > idle` ordering (id tie-break); the lower-priority
   unit yields. Demote the watchdog teleport to genuine geometry-wedge cases only,
   with a **per-frame recovery cap** and the static list built once.
4. **Substep at high speed** (B6). Cap effective movement dt (substep the movement
   integration) so 5× speed doesn't tunnel.

### Phase 4 — AI: shared perception, LOD, squads (4–6 days, medium)
1. **Blackboard** (C1/C3/C4). Promote `GoalContext` into the single per-tick world
   scan: publish the spatial hash, enemies-near-base + threat, idle-worker list,
   per-resource assignment counts, squad rosters. Make every goal/brain read it —
   enforce that none touch `game.units`/`game.buildings` directly.
2. **LOD / time-sliced ticks**. Round-robin K units/frame; combat units reassess
   fast, idle/gathering workers slowly; dirty-flag urgent re-eval to the front.
   Spread sub-brain work across the frames between 0.5 s ticks.
3. **Squad command layer** (C1). Reason about ~5–15 squads, not hundreds of units;
   `military_brain` issues a posture + target-region per squad, which fans out
   orders. Kills the "command every unit in one tick" spike.
4. **Influence / threat maps**. Coarse per-player grid (~10×10), rebuilt a few
   Hz; drives squad target selection and retreat gradients.

### Phase 5 — Scale play: flow fields + formations (5–8 days, high)
1. **Flow fields** (A7). On a group move/attack order, build **one** BFS/Dijkstra
   integration field over the square nav grid, cached by `(goal_cell, revision)`,
   and fan it to all squad members; keep per-unit JPS for singletons and workers
   with individual resource targets. Rides on Phase 2's dirty-region invalidation.
2. **Minimal formations**. SmartCenter anchor + distinct per-unit slot offsets so a
   group aims at *distinct* points instead of one identical spot (kills
   destination bunching). Enforce slots only when cohesive.

### Phase 6 — Heavy artillery (only if still bottlenecked after 1–5)
HPA* for long cross-map routes · D*-Lite incremental replanning · numpy
structure-of-arrays + Numba `@njit` on the confirmed movement/A* kernel · native
`pyrvo2`/ORCA for guaranteed non-interpenetration. **Not** multiprocessing: the
GIL makes threads useless for pure-Python A*, and shipping the constantly-changing
grid to worker processes fights the whole design. Flow fields deliver the same
relief in-process.

---

## 6. Performance targets

Measured on the headless benchmark. "Now" is the 45-unit reading; the bar is to
hold these at **200 units**.

| Metric | Now (45u) | Target @ 200u |
|---|---|---|
| Update avg | 42.7 ms | **< 8 ms** |
| Update p95 | 182 ms | **< 16 ms** |
| Update max (worst hitch) | 492 ms | **< 33 ms** |
| Single AI tick max | 478 ms | **< 8 ms** |
| A* "too_expensive" rate | 15 % | **< 1 %** |
| Watchdog teleports / min | (high) | **≈ 0** (recovery, not routine) |

Phases 1–3 alone should clear the avg/p95/hitch targets; Phases 4–5 are what let
"200 units" behave like "45 units".

---

## 7. Preserved backlog (non-perf, carried over from the deleted plans)

Do **not** lose these; they are unrelated to the perf work.

- **AI completeness**: verify the utility AI actually trains *every* unit type
  (spearman / cavalry / ram / healer) and builds every building type
  (stable / blacksmith / siege_workshop / watchtower / wall) — the old plan flagged
  training/building gaps.
- **Defensive-stance freeze**: units chasing past `stance_chase_distance` stop in
  the field instead of returning to `stance_home_position`.
- **Healer doesn't heal**: trainable, walks, no healing logic anywhere.
- **Wall is a 1×1 building**: no gate, thin profile, or special placement.
- **Save/Load is a thin slice**: misses terrain seed, AI state, fog grids, scout
  explored tiles, paths, gathering/building/combat targets, production/research
  queues, formation, control groups, stance homes, tree-regrowth tracker. Revisit
  after the AI/movement state shape settles (Phases 3–4).
- **Sound coverage**: `attack`, `select`, `move_order`, `gather`, `build_complete`,
  `alert` are defined but never called.
- **Test coverage**: existing tests assert constants/attributes, not behavior. Add
  integration tests that run the AI for N ticks and assert observable outcomes,
  plus the Phase 0 perf-regression gate.
- **Docs housekeeping**: `CLAUDE.md` / `AGENTS.md` still describe the old 4-phase
  state-machine AI and an 8 px grid (it's a 20 px grid + utility AI now). Refresh
  once this plan lands.

---

## 8. References

**Global pathfinding** — Flow fields: Emerson, "Crowd Pathfinding and Steering
Using Flow Field Tiles," *Game AI Pro* ch. 23
(gameaipro.com/GameAIPro/GameAIPro_Chapter23_Crowd_Pathfinding_and_Steering_Using_Flow_Field_Tiles.pdf);
redblobgames.com/blog/2024-04-27-flow-field-pathfinding; howtorts.github.io.
JPS: Harabor & Grastien, AAAI 2011 (harabor.net/data/papers/harabor-grastien-aaai11.pdf);
JPS+ *Game AI Pro 2* ch. 14. HPA*: Botea/Müller/Schaeffer
(webdocs.cs.ualberta.ca/~mmueller/ps/hpastar.pdf). Incremental replanning:
D*-Lite, Koenig & Likhachev (idm-lab.org/bib/abstracts/papers/aaai02b.pdf);
Recast DetourTileCache. Grid granularity: redblobgames.com/pathfinding/grids/algorithms.html.
Request scheduling: havok.com/blog/asynchronous-navigation-processing.

**Local steering** — Reynolds steering behaviors (red3d.com/cwr/steer);
Context steering: Fray, *Game AI Pro 2* ch. 18
(gameaipro.com/GameAIPro2/GameAIPro2_Chapter18_Context_Steering_Behavior-Driven_Steering_at_the_Macro_Scale.pdf);
ORCA/RVO2 (gamma.cs.unc.edu/RVO2, gamma.cs.unc.edu/ORCA); Continuum Crowds
(grail.cs.washington.edu/projects/crowd-flows); coordinated movement &
right-of-way: Pottinger, gamedeveloper.com/programming/implementing-coordinated-movement
and /group-pathfinding-movement-in-rts-style-games; spatial hashing:
gameprogrammingpatterns.com/spatial-partition.html.

**RTS AI** — Utility AI vs BT/GOAP: gamedeveloper.com/programming/are-behavior-trees-a-thing-of-the-past-;
LOD AI: Sunshine-Hill, "LOD Trader," *Game AI Pro* ch. 14; Influence maps: Mark,
"Modular Tactical Influence Maps," *Game AI Pro 2* ch. 30; Blackboard:
tonogameconsultants.com/ai-blackboard.

**Python / pygame perf** — py-spy (github.com/benfred/py-spy); spatial hash
(pygame.org/wiki/SpatialHashMap); pygame optimisation (pygame.org/wiki/Optimisations);
`__slots__` (wiki.python.org/moin/UsingSlots); GC taming
(making.close.com/posts/taming-the-python-gc); Numba
(numba.pydata.org/numba-doc/dev/user/performance-tips.html); GIL
(realpython.com/python-gil).
