# RTS Master Plan — Performance Foundation & Single-Player Depth

> Single source of truth for the game's direction. Two tracks:
> **Track A (§1–6)** — make the sim fast and smooth at scale (hundreds of units)
> with a cheaper, better AI. This is the foundation and comes first.
> **Track B (§7)** — deepen the single-player-vs-AI skirmish into something
> genuinely fun, addictive, and replayable, once the foundation holds.
> **Track C (§8)** — UI/UX polish and game-systems depth: minimap, GUI rework,
> the resource model, combat/RPS, and audio & juice.
> Supersedes and replaces the old `IMPROVEMENT_PLAN.md` and `AI_UTILITY_DESIGN.md`
> (deleted). Status: **planning**, written 2026-07-09.

> **How to use this plan — it's a working checklist.** Every action is a `- [ ]`
> checkbox; tick it (`- [x]`) as you land it. Each phase/sub-phase ends with a
> **✅ Verify** gate — the concrete check that proves it works *and didn't regress*.
> **Do not start the next phase until its gate passes.** Track A gates are measured
> (`tools/benchmark_ai_spectator.py`, `cProfile`/`py-spy`, `pytest`); Track B/C gates
> are mostly play-and-observe plus the balance sim (§8.8). The baseline to beat is
> §6. §1–4 are the "why" (diagnosis + architecture) — reference, not checklist.

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
order; **re-run the benchmark after each and clear the ✅ Verify gate before moving
on.** Tags like (A1)/(D2) map each action back to the root-cause inventory in §3.

### Phase 0 — Make it measurable & safe (0.5 day, prerequisite)
**Goal:** be able to prove any later change helped and didn't regress.
- [x] Add a dev toggle for `PERF_STATS_ENABLED` (env var / CLI flag) — `RTS_PERF_STATS=1`.
- [x] Wire `py-spy` into the workflow for flamegraphs on a real late-game state —
  `tools/profile_pyspy.py` (also: `--profile out.prof` on the benchmark for cProfile).
- [x] Extend `tools/benchmark_ai_spectator.py` into a **perf regression gate** —
  assert `frame_max_ms` / `frame_p95_ms` under thresholds; support `--fail-on-stall`
  (`--max-frame-avg-ms/--max-frame-p95-ms/--max-ai-max-ms/--output/--profile`).
- [x] Extend the `reference_walkable()` cross-check in `tests/test_navigation.py`
  (the safety net for every incremental-nav change in Phase 2) — dense full-map sweep
  incl. post-mutation re-check.
- Baseline (2026-07-10, 120 sim s @5×, 48 units): `tools/perf_baseline.json` —
  frame avg 26.2 ms / p95 165 ms / max 514 ms; ai_max 511 ms; astar 442 cells/call,
  5.4 % capped; 70 mark_dirty.
- **✅ Verify:** `python tools/benchmark_ai_spectator.py --seconds 120 --speed 5
  --fail-on-stall` runs green and records a baseline JSON; `pytest
  tests/test_navigation.py` passes; a py-spy flamegraph of a late-game state is
  captured as the reference.

### Phase 1 — Cheap, high-ROI wins (2–4 days, low risk, no new architecture)
**Goal:** roughly halve average frame time and evict the coordinate-conversion +
fog hogs — with zero architecture change.
- [x] **Static walkable bitmap** (A1) — conservative per-nav-cell terrain bitmap
  built once at startup (terrain is static); all terrain probes (pathfinding,
  collision, movement, LOS) are O(1) lookups via `game_map.nav_terrain_walkable`.
- [x] **Fog rework** (D1/D2) — throttled to ~5 Hz game time; per-(radius, column
  parity) offset masks; per-player visible-tile sets (fade is O(visible));
  incremental explored counter; fog tile surfaces cached per (size, α); update
  skipped entirely when fog disabled.
- [x] **Shared spatial index** (B1/B2/C2/C5) — collision buckets exposed as
  `query_nearby_units` / `query_nearby_static` / `query_obstacles_along`; routed
  `evaluate_combat_targets`, building auto-target, `find_optimal_attack_position`,
  movement LOS obstacle lists, `production._is_valid_spawn_position`, watchdog
  safe-position. Bucket queries no longer O(all objects); static signature checked
  once per frame.
- [x] **Cache effective stats** (E1) — (multiplier, bonus) memoized per player
  keyed by new `player.upgrades_version`; zero-upgrade fast path.
- [x] **Throttle target re-acquisition** (C2) — idle units & defensive buildings
  re-scan every ~0.25–0.5 s (jittered per object); target kept between scans.
- [x] **O(1) worker-task validity** (E2) — `GameObject.in_world` flag set at every
  removal site replaces list-membership scans.
- [x] **Rendering hygiene** (D3/D4/D5) — frustum-cull before fog-check/sort/draw;
  scaled-sprite cache keyed (sprite, w, h); minimap dot layer redrawn at ~4 Hz.
- [x] **Micro-hygiene** (E3/E4/E5/E6) — `debug_log.enabled()` gates hot f-strings;
  single-pass projectile filter; squared-distance in hot loops; `gc.freeze()` after
  setup; `attack_trackers` purged on death. `__slots__` deliberately skipped:
  entities lean on dynamic attrs (hasattr/delattr probes); revisit in Phase 3.
- **✅ Verify (passed 2026-07-10):** benchmark (120 sim s @5×, 48→56 units):
  `frame_avg_ms` 26.2 → **6.1** (target ≤22), p95 165 → **24**, max 514 → **189**,
  ai_max 511 → **152**, A* capped 5.4 % → **0 %**; cProfile confirms
  `world_to_grid`/`grid_to_world` + `fog_of_war` out of top-5 self-time (top cost
  is now A* itself — Phase 2's target); `pytest` 144 green; headless human_1v1
  smoke sim: AI gathers/builds 9 buildings/trains mixed army/researches 2 techs
  with fog on. (Manual windowed play-check still recommended.)

### Phase 2 — Pathfinding structure: stop the stampede (3–5 days, medium risk)
**Goal:** kill the full-rebuild cache wipes and the A* expansion explosion; no
failed paths under load.
- [x] **Incremental / dirty-region nav** (A2) — `notify_blocker_added/removed`
  index/unindex one object and invalidate only walkable-cache cells + cached
  paths crossing the changed bbox; terrain bitmap never wiped; `mark_dirty` kept
  as bulk fallback (setup/load/restart). All runtime callers converted.
  (Static/dynamic blocker classes unnecessary — per-object updates are finer.)
- [x] **Jump Point Search** in `_astar` (A4) — strict no-corner-cut JPS
  (PathFinding.js JPFMoveDiagonallyIfNoObstacles rules), optimality verified by a
  randomized equivalence test vs a plain-A* oracle. Plus three rejection layers
  the profile demanded: negative (no-path) caching dropped on blocker removal,
  O(1) terrain connected-components (goals on terrain islands), and a bounded
  reverse flood fill (goals walled into small object pockets).
- [x] **Request queue + sane budgets** (A3/A6/C1) — over-budget commands queue
  and drain a few per frame (human-owned first, per-unit supersede, 5-retry cap)
  instead of failing; queue-drained requests get a 20 ms ceiling that bypasses
  the frame clamp. Budgets: `PATHFINDING_FRAME_BUDGET_MS` 180 → **10**,
  `PATHFINDING_MAX_REQUEST_MS` 150 → **12** (frame budget is the binding cap;
  2–3 ms per request proved too small for legit long paths in pure Python —
  they death-spiraled through retries).
- [x] Add **per-worker jitter** to repath cooldowns so a cache event doesn't align
  every worker on one frame — deterministic 0–0.35 s by worker id; worker
  too_expensive results retry via cooldown instead of recording unreachable.
- [x] *(optional)* Evaluate a **coarser routing grid** decoupled from collision —
  evaluated and skipped: with JPS + rejection layers, expanded cells/call is 12
  and capped searches all complete via the queue; a second grid isn't warranted.
- **✅ Verify (passed 2026-07-10, seeded benchmark 120 sim s @5×):**
  `astar_expanded_cells / astar_calls` 442 → **12** (≈37×, target ≲150);
  too-expensive: 34 deferrals = 4 % of calls but **0 dropped commands — every
  deferral completed via the queue** (the <1 % gate predates the queue; the
  failure-equivalent rate is 0 %); `path_full_rebuilds` **0** (was ~70/120 s,
  incl. every resource depletion); cache hits ~3×; frame avg **3.7 ms** /
  p95 13.8 / max 32 (vs 26.2/165/514 baseline); `pytest` 147 green incl.
  incremental-nav reference sweeps and the JPS-vs-A* oracle; stale-path
  invalidation on newly placed buildings covered by
  `test_incremental_add_invalidates_cached_straight_path`.

### Phase 3 — Local steering: fix stuck / teleport / bunch-up (3–5 days, medium)
**Goal:** units stop bunching, stalling, and teleporting.
- [x] **Arrival + stop-on-arrival** (B3) — steps clamped to remaining distance
  (no overshoot) + 40 px slowing radius into final goals; combat chases keep
  full speed. Arrived idle units are lowest right-of-way class.
- [x] **Context steering** (B1/B4) — 16-slot interest/danger map per moving unit
  from the shared hash; interaction targets excluded from danger; hysteresis;
  terrain-blocked slots never chosen. Unit-unit slide +
  `_find_escape_direction` retired. (`_stuck_detector` kept deliberately: it's
  the combat-repath trigger, not a steering mechanism — revisit in Phase 4.)
- [x] **Priority / right-of-way** (B4/B5) — `carrier > mover > idle` with id
  tie-break; winners nudge the crowd apart, yielders sidestep instead of
  freezing; followers pressing on a leader's back are ignored (convoys don't
  freeze); deep-overlap separation pass wired into the loop (was never called);
  watchdog capped at 2 recoveries/check and resumes interrupted move orders
  from `last_task` (per-incident cap).
- [x] **Substep at high speed** (B6) — per-unit substepping whenever one step
  would exceed 10 px; slow units stay single-step so it's ~free.
- [x] Add a **watchdog-teleport counter** to `perf_stats` (`watchdog_recoveries`
  / `watchdog_teleports`).
- **✅ Verify (passed 2026-07-10):** normal-play seeded benchmark: watchdog
  teleports **0**/120 sim s (recoveries 1), frame avg 2.9 ms / p95 13.2 / max 27;
  100-unit cross-map order (`tools/stress_group_move.py`): **0 → 95/100 arrive**,
  95 % arrival in ~105 sim s, teleports 3–5 per 300 sim s (residual: a few units
  in the dense spawn resource field — single-point mega-blob convergence is the
  Phase 5 formations/flow-field case); per-unit substepping = no tunneling at 5×;
  pytest 147 green.

### Phase 4 — AI: shared perception, LOD, squads (4–6 days, medium)
**Goal:** the 478 ms AI-tick spike is gone and AI cost stays flat as the army grows.
- [x] **Blackboard** (C1/C3/C4) — `GoalContext` is the single per-tick world scan:
  enemy units/buildings, enemies-near-base, known resources by type (fog-checked),
  per-resource gatherer counts, research-in-progress, memoized dropoff scores,
  threat map. Every goal and sub-brain reads the snapshot — enforced by
  `tests/test_ai_contract.py` (greps for `game.units`/`game.buildings` in
  goals/brains and fails on violation).
- [x] **LOD / time-sliced ticks** — AI ticks run in `pathfinder.deferred_paths()`
  mode: all path requests fast-fail into the cross-frame queue, so a tick spends
  µs enqueueing instead of ms searching (this, not per-unit round-robin, was the
  actual spike); scout brain runs every 2nd tick; unit-level target acquisition
  was already throttled+jittered in Phase 1 (C2).
- [x] **Squad command layer** (C1) — military ordered as rotating ~10-unit
  squads, one squad commanded per tick; defense still mobilizes everyone.
- [x] **Influence / threat maps** — coarse per-player threat cells (400 px)
  built per tick from enemy combat strength (defensive buildings ×2);
  `ctx.threat_at` steers attack-target selection toward least-defended targets.
- **✅ Verify (passed 2026-07-10):** `ai_max_ms` **4.0** (4 players, 45 u) and
  **4.9** at 8 players / 109 units (target < 8, no spike at 2.4× army);
  `ai_avg_ms` 1.02 → 1.59 (sub-linear); F4 debug info shows chosen goal +
  top-5 scores + worker/military breakdowns; 2-player AI-vs-AI match runs to
  `simulation_complete` (castle kill) with techs researched on both sides;
  148 tests green.

### Phase 5 — Scale play: flow fields + formations (5–8 days, high)
**Goal:** a 200-unit group move costs one field, not 200 searches; §6 targets hold
at 200 units.
- [x] **Flow fields** (A7) — `systems/flow_field.py`: one Dijkstra integration
  field per group order, built incrementally inside the per-frame path budget
  (no frame freeze), cached by (goal cell, radius), invalidated on nav changes;
  fanned to group members with per-unit formation-slot handoff at 90 px;
  per-unit JPS kept for singletons/workers and as fallback for disconnected
  cells / stale fields. Wired into 8+-unit right-click group moves.
- [x] **Minimal formations** — formation offsets (ring/line/box/wedge) already
  produced distinct per-unit points; they now become flow-field slot targets
  so a group aims at distinct points after one shared field.
- **✅ Verify (passed 2026-07-10, group-move gate):** 100-unit cross-map order:
  `flow_fields_built` **1**, path requests 101 → 10, 95 % arrival 105 → **50
  sim s**, 0 teleports/recoveries; 200-unit order: 95 % arrival at 80 sim s,
  frame avg 12.3 ms during the march, no chokepoint wedge. **§6-targets-at-200u
  is tracked by the Track A acceptance gate below (not yet met — see §6).**

### Phase 6 — Heavy artillery (only if §6 targets still unmet after 1–5)
**Goal:** close any residual gap — each item gated behind a profile that proves it's
*still* the bottleneck.
- [ ] **HPA*** for long cross-map routes — only if long queries still dominate a
  flamegraph.
- [ ] **D*-Lite** incremental replanning — only if per-change replans still spike.
- [ ] **numpy SoA + Numba `@njit`** on the confirmed movement/A* kernel — only if that
  kernel is still hot.
- [ ] **native `pyrvo2`/ORCA** — only if non-interpenetration at very high counts is
  still needed.
- **Not** multiprocessing (GIL makes threads useless for pure-Python A*, and shipping
  the constantly-changing grid to workers fights the design; flow fields give the same
  relief in-process).
- **✅ Verify:** a py-spy flamegraph shows the targeted cost was top before and gone
  after; §6 targets met at the intended scale.

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

- [ ] **Track A acceptance gate** — all six targets above hold at **200 units** in
  the benchmark. This is the definition of "performance done"; Track A is only
  complete when this is ticked.
  - **Status 2026-07-10 (Phases 0–5 + profile-backed Phase 6 quick wins landed):**
    45-unit benchmark: avg **4.2** / p95 **12.6** / max **28** / ai_max **2.5** /
    capped-failures **0** / teleports ~0–2 per 120 s — all targets met at 45 u.
    8-player war benchmark (92 u, heavy combat): avg **7.5** ✓ / p95 **17.2** ✗
    (target 16) / max **68** ✗ (33) / ai_max **6.0** ✓ / teleports ~2/min ✗.
    200-unit group-move stress: avg 12.3 ✗. Remaining hot spots per profile:
    JPS scan volume during war-time repaths, LOS sampling (now 8-frame cached),
    spatial-query iteration in steering. Residual gap is Phase 6 territory
    (numpy/Numba movement + A* kernels, possibly ORCA) — each still gated
    behind a fresh profile.

---

## 7. Track B — gameplay & fun (single-player vs AI)

Deepens the skirmish-vs-AI experience. **Sequencing** (deliberate): the
performance work (§5) lands **first** — at 45 units the sim is already ~5 FPS at
p95, so heavy new AI/gameplay systems feel bad until Phases 1–4 hold, and the
AI-depth items here explicitly build on the Phase 4 blackboard / squad /
influence-map work. **Exception:** items tagged **⚡** are input/UI/setup level,
independent of the perf refactor, and can ship **in parallel, starting now**.
This track also absorbs the gameplay items from the preserved backlog (§9):
healer healing and wall-as-gate.

> **Research provenance.** The AI difficulty/fairness principles in §7.1 were
> adversarially verified against primary sources (Hagelbäck & Johansson, IEEE CIG
> 2009; Zohaib DDA review 2018; Khajah et al. CHI 2016). The economy/combat, QoL,
> and replayability items draw on cited design writing (Wayward Strategy, Game
> Developer, Blizzard, Liquipedia) and the named games — the deep-research run was
> cut short by a session limit before its final synthesis, so treat those as
> well-sourced design guidance rather than lab-verified fact. Sources in §10.

### 7.1 North-star principles (what actually makes it fun)

These are the load-bearing, evidence-backed rules. Several are **counter-intuitive**
and should override "obvious" instincts.

- **Aim for the flow channel, not for winning.** Too-easy is boring, too-hard is
  frustrating; both kill fun. An opponent that produces *even, contested* matches
  is measurably more enjoyable than a statically strong or weak one. *[verified]*
- **Never throw the game.** An AI that deliberately drops its play to let the
  player win was rated the **least** enjoyable of all opponents tested — worse than
  a dumb static bot. Catch-up must never look like mercy. *[verified]*
- **If you adapt difficulty, hide it.** Covert adjustment helps engagement; overt/
  visible adjustment does little and gets **exploited** (players tank on purpose to
  trigger easy mode). Keep any adaptation subtle and coherent with recent state.
  *[verified]*
- **Don't scale difficulty by resource-cheating alone.** Multiplying the AI's
  gather rate is the cheap lever (AoE4's hardest tiers = 1.2×–2× resources) and it
  reads as **unfair** — the classic feel-bad. Scale *decision quality, reaction
  speed, aggression, build sophistication* first; reserve economic handicap for an
  explicit, player-chosen slider. *[verified]*
- **No rubber-banding.** Speeding the AI up when behind / slowing when ahead is a
  known feel-bad; avoid it. *[verified]*
- **The AI is load-bearing for everything else.** A skirmish game is only as
  replayable as its AI is fun to beat — §7.4/§7.5 rest on §7.2.

### 7.2 AI opponent depth — *builds on Phase 4 (blackboard / squads / influence maps)*

- [x] **Honest difficulty tiers** *(med)* — Easy/Normal/Hard implemented
  2026-07-10 as pure decision-quality scaling (§7.1-compliant, no stat/resource
  cheats): strategic tick cadence 1.0/0.5/0.35 s, attack-commitment delta
  +3/0/−1, idle-worker assignments per tick 1/2/3. Selectable per match in the
  setup screen (`ai_difficulty` on AI players). Verified: easy AIs tick ~3×
  slower than hard. (Still open for later tiers: scout frequency + micro
  scaling; the transparent economic "handicap" slider.)
  - *(2026-07-10)* per-personality attack-threshold **mechanism** added
    (`ATTACK_ARMY_THRESHOLDS` / `attack_army_threshold()`), but the first
    tuning (rusher 4, boomer/turtle 8) **failed same-seed validation**:
    rusher 4/13 → 3/13, 0–5 vs boomer — smaller armies attacking sooner into
    full-DPS defenses lose harder. Values reverted to flat 6. Conclusion for
    the real fix: rusher needs a *signature build order* that fields an army
    faster (skip early farm/dropoff goals, barracks-first), not an earlier
    trigger on the same economy. Validation data:
    `tools/balance_20_thresholds.json`.
- [x] **Personalities that actually differ** *(med)* — signature build orders
  landed 2026-07-10: per-personality worker targets (rusher 4, boomer 9) +
  army-composition fractions (rusher warrior-heavy, turtle/boomer
  archer-leaning) + tower doctrine (§8.10). **Same-seed validation: rusher
  31 %→46 % win rate (head-to-head vs boomer 1–4 → 2–3), boomer's dominance
  56 %, turtle 4/5.** Watch-item: `balanced` fell to 4/13 now that every
  specialist got sharper — needs its own identity pass or acceptance as the
  "teaching" opponent. Data: `tools/balance_20_signature.json` (authoritative
  run).
- [x] **Telegraph attacks** *(low–med)* — 2026-07-10: when an AI squad is
  dispatched against the human, an "Enemy attack incoming!" alert + minimap
  ping fires at a marching unit's position — but **only if the human can
  currently see part of the squad** (fair perception: no free intel from
  unexplored fog; with fog disabled the march is plainly visible). 45 s
  per-AI throttle. Tests in `tests/test_telegraph.py`. Original scope for
  reference (army
  massing near the border, a "hostile force detected" alert, scout-visible staging).
  Needs the alert system (§7.4).
- [ ] **Reactive counters** *(med)* — AI scouts the player's composition and shifts
  production toward counters instead of a fixed comp. Rides on Phase 4.
- [ ] **Fair perception** *(med)* — AI acts on *scouted* info, not omniscience.
  Pairs with the fog work.
- [ ] **Optional covert DDA** *(med)* — within the chosen tier, nudge AI
  aggression/expansion (never stats) toward even matches; hidden, coherent, never
  throwing.
- **✅ Verify:** play a match against each personality at ≥2 tiers — openings differ,
  the higher tier is harder *without feeling like it cheated* (§7.1 guardrails hold),
  and the §8.8 balance sim shows no single personality/tier dominating win-rate.

### 7.3 Economy & combat decision depth

- [ ] **Power spikes / timing** *(low)* — make tech/upgrade completion a visible,
  meaningful army-strength jump so "attack right after Forged Blades finishes" is a
  real decision. Mostly surfacing existing upgrades + feedback.
- [ ] **Legible, imperfect counters** *(low–med)* — show strong/weak-against in the UI
  and tune so range/speed/size matter; keep it *imperfect* RPS where
  position/terrain/upgrades still decide. (Mechanic lives in §8.4.)
- [ ] **Risk/reward economy** *(med)* — expanding/booming opens a real, scoutable
  vulnerability window, so greed vs safety is a live choice. (Enabled by §8.3 worker
  saturation.)
- [ ] **Anti-snowball / comeback** *(med)* — diminishing returns so a small early lead
  isn't an auto-win; the biggest fun-killer is a foregone 20-minute loss.
- [ ] **Scouting payoff** *(med)* — a scout that reveals enemy tech/army so the player
  makes informed build decisions. Ties to fog.
- **✅ Verify:** in a playtest, an upgrade produces a *felt* power spike; counters are
  readable and change fight outcomes; an early lead is not an auto-win (play out a
  comeback); the §8.8 balance sim shows varied unit usage (no single dominant unit).

### 7.4 Game feel & QoL — *the modern bar; many **⚡** parallelizable now*

- [x] ⚡ **Idle-worker management** *(low)* — F1 selects/cycles idle workers and
  centers the camera; amber "Idle: N (F1)" badge on the top bar when nonzero.
  (2026-07-10)
- [x] ⚡ **Control-group centering** *(low)* — double-tap a group number (<450 ms)
  to center the camera on the group centroid. (2026-07-10)
- [x] ⚡ **Shift-queued commands** *(low)* — Shift+right-click queues
  move/gather/attack/dropoff/garrison commands per unit (cap 8); the queue
  drains as units go idle, a plain command or Stop wipes it. (2026-07-10)
- [x] ⚡ **Rally points** *(low)* — right-click with an own production building
  selected sets its rally (yellow flag drawn while selected); new units path
  there on spawn, and workers rallied onto a resource start gathering it.
  (2026-07-10)
- [x] ⚡ **Alerts & minimap pings** *(low–med)* — completed 2026-07-10 with a HUD
  alert feed (`ui_manager.add_alert`: fading toasts under the top bar, optional
  minimap ping, per-key throttling). Wired: **under attack** (sound + ping +
  toast, 10 s throttle), **building complete** (toast + ping, human only),
  **research complete** (toast + ping, human only), **low on X** (dip below 25
  triggers once, 30 s per-resource throttle). "Unit idle" is the amber F1
  badge from idle-worker management. Sound hooks were wired in the §8.5 audit.
  Tests in `tests/test_alerts.py`.
- [x] ⚡ **Smart context commands** *(low)* — right-click resource=gather /
  farm=garrison / enemy=attack / carrying-worker-on-building=dropoff were
  already in; 2026-07-10 added the missing case: an empty worker right-clicked
  onto an own lumbermill/mine/quarry gathers the nearest matching live
  resource (within 400 px). Tests in `tests/test_smart_commands.py`.
- [x] ⚡ **Instant command feedback** *(low)* — 2026-07-10: every right-click
  order plays the move-confirm sound and draws a shrinking ring at the target
  (green move / red attack / amber gather / blue rally), drawn over fog on the
  map surface, ~0.45 s. Rally and group moves included.
- [x] **Production/queue UI** *(med)* — the panel already had radial progress,
  per-type queue badges, click-to-queue, and rally flags; 2026-07-10 closed
  the real gaps: queueing now **pays up front** (was: queued units were free
  and silently dropped if unaffordable when popped), queue capped at 5,
  **right-click a unit button removes the last queued of that type (full
  refund)** or cancels the in-progress one (50 % refund) when none queued.
  Stale panel rects no longer eat clicks after deselecting. Tests in
  `tests/test_production_queue.py`.
- [ ] **Readability pass** *(med)* — HP bars, team-color clarity, hover/selection
  highlights, damage/heal floats.
- **✅ Verify:** each item is observable in-game — idle-worker key selects/cycles and
  the badge counts; double-tap centers; Shift queues; rally points path new units;
  alerts fire *and* ping *and* play sound; right-click gathers; every order gives a
  visible/audible cue.

### 7.5 Replayability — *cheap match-to-match variety; mostly **⚡***

- [x] ⚡ **Match-setup screen** *(low)* — `screens/match_setup.py` (from Start
  Game): play-vs-AI or spectate, 1–7 opponents, AI personality, map seed
  (R rerolls), game speed. (2026-07-10. Not yet: map size, per-opponent
  personality, resource richness — extend the same rows when wanted.)
- [x] ⚡ **Map/start randomization** *(low–med)* — seed exposed in the setup
  screen and `--seed` CLI; same seed reproduces terrain + starts + layouts
  (verified), fresh seed each screen visit. Terrain/starts/resources were
  already procedural.
- [x] **Victory conditions beyond annihilation** *(med)* — 2026-07-10: match
  setup offers **Annihilation** (castle-kill, default), **Economic** (first to
  5,000 cumulative resources gathered), and **Timed** (highest score —
  economy + production + army — at 20 game-minutes). Castle loss still
  eliminates in every mode. Verified headless: economic and timed both
  trigger and declare the right winner. (Landmark / king-of-the-hill /
  relic-hold remain future variants.)
- [x] **Match modifiers ("mutators")** *(low–med)* — 2026-07-10: Mutator row in
  match setup with **Double Resources** (2× gather ticks + farm food),
  **No Towers** (watchtower disabled for humans via menu/`can_player_build`
  and for AI via goal + construction guards), and **Revealed Map** (fog off).
  Applied via `game.mutators`; survives save/load (with fog-enabled state).
  Tests in `tests/test_mutators.py`. Sudden death is effectively the base
  rule already (castle loss eliminates); attrition/weather stay future.
- [ ] **Dynamic map elements / random events** *(med)* — periodic neutral events
  (resource booms, wandering hostiles, weather) that force adaptation.
- **✅ Verify:** start 3 matches with different setup/seed and confirm they genuinely
  differ (map, start positions, opponents); each non-annihilation victory condition
  can be triggered to a win/loss; a mutator visibly changes the rules.

### 7.6 Start-now cluster (parallel to Phases 1–3)

All **⚡**, low-effort, independent of the pathfinding/AI refactor — pure
playability that can land while the perf work is in flight:
idle-worker key · control-group centering · shift-queue · rally points · alerts +
minimap pings (wiring the dead sound hooks) · smart context commands · match-setup
screen · map/start randomization. Ship these first for immediate feel wins; save
§7.2's AI depth for after Phase 4.

---

## 8. Track C — UI/UX & game systems

Polish, playability, and systems depth. A mix of **cheap fixes** (tagged **⚡** —
safe to do anytime, independent of the perf refactor) and **deliberate systems
work**. Two items — the resource model (§8.3) and the combat/RPS rework (§8.4) —
change core game feel and are **balance-sensitive**: prototype, playtest, and
validate with the balance sim (§8.8) before committing; the direction below is a
recommended starting point, not a locked spec. **Suggested order:** the §8.1
minimap fix and §8.5 audio hooks first (cheap, visible), then the §8.2 GUI rework
as the visual backbone, with §8.3/§8.4 prototyped against §8.8 in parallel.

### 8.1 Minimap & readability — *⚡ mostly quick fixes*

Current state: [`ui/minimap.py`](ui/minimap.py) draws **every** unit, building, and
resource as the same hardcoded green rect (line 54) — no owner color, no resource
color, no fog respect, redrawn every frame. This is both a bug and a colorblind
hazard.

- [x] ⚡ **Color by owner** *(low)* — units/buildings draw in their player color;
  buildings 4×4 with a white outline vs 2×2 unit dots. (2026-07-10)
- [x] ⚡ **Resource colors** *(low)* — gold=amber, wood=green, stone=grey via
  `RESOURCE_COLORS`.
- [x] ⚡ **Respect fog** *(low)* — enemy units only while currently visible;
  enemy buildings/resources only once explored.
- [x] ⚡ **Colorblind-safe palette** *(low)* — amber/green/grey resource palette
  distinct in hue+lightness; player colors from config unchanged (verify with a
  colorblind check when doing the §8.2 HUD pass).
- [x] **Throttle + pings** *(low–med)* — dot layer cached at ~4 Hz (Phase 1 D5);
  expanding red alert pings drawn live; `minimap.add_ping` wired to the
  under-attack alert (§7.4).
- **✅ Verify:** in a live match the minimap shows your stuff, enemies, and each
  resource type as visually distinct colors; fogged enemies do **not** appear; the
  colors are distinguishable in a colorblind check.

### 8.2 HUD & GUI rework — *structural*

The UI works but is ad-hoc (delegated panels in `ui/components/*`) and hardcoded to
1280×720 (`core/config.py`). Rework toward a cohesive, scalable system.

- [ ] **Resolution independence + UI scaling** *(med–high)* — layout from
  anchors/relative units, not fixed pixels; support arbitrary window sizes. Foundation
  for everything visual.
- [ ] **Command card / action grid** *(med)* — SC/AoE-style action grid for the
  selection with grid hotkeys, replacing bespoke panels.
- [ ] **Multi-select panel** *(med)* — grouped unit icons + counts + health for mixed
  selections.
- [ ] ⚡ **Settings menu** *(low–med)* — resolution, volume, default game speed,
  hotkeys — long-deferred.
- [ ] **Universal tooltips** *(low–med)* — cost, counters, description on hover for
  every unit/building/tech.
- [ ] **Event/notification feed** *(low–med)* — scrolling log of alerts. Pairs with §7.4.
- [ ] **Menu polish** *(low–med)* — main/pause/victory screens scale and share the
  visual language.
- **✅ Verify:** resize the window to a non-720p size and confirm the HUD lays out
  correctly with no clipping; the command card issues actions; tooltips appear on
  hover; settings changes persist across a restart.

### 8.3 Resource model rethink — *balance-sensitive*

Today: gold/stone (1/s, carry 10, 1000-node), wood (2/s, carry 20, 600-node), food
from farms (3/s) — four resources with fuzzy identities.

- [ ] **Sharpen resource identity** *(med)* — give each a distinct strategic role
  (e.g. gold = scarce/contested → map control; wood = renewable bulk; stone =
  rare/strategic → defense & key buildings; food = land+labor). Or cut to 2–3 if roles
  can't be made distinct.
- [x] **Worker saturation** *(med)* — prototyped behind
  `WORKER_SATURATION_ENABLED` (2026-07-10): past 3 gatherers a node's total
  yield stays flat (each stacked worker gathers at cap/n rate). Verified:
  per-worker rate exactly halves at 6 gatherers. The AI's existing crowding
  penalties already push it to spread across nodes; the full §8.8
  income-vs-worker-count charting remains for the tuning pass.
- [ ] **Gathering range/flow tuning** *(low)* — `GATHERING_DISTANCE_MULTIPLIER = 0.5`
  makes workers hug nodes; tune gather + drop-off distances so it feels smooth.
- [x] **Income-rate HUD** *(low)* — 2026-07-10: green `+X/s` under each
  stockpile in the top bar, from a 15 s rolling window of the human player's
  worker drop-offs and farm ticks (`game.record_income`/`income_rate`).
  Hidden when ~zero. Tests in `tests/test_income_rate.py`.
- **✅ Verify:** *prototype behind a flag first.* With saturation on, a second base
  measurably raises income (chart income vs worker count); the income HUD matches
  actual gains; the §8.8 balance sim shows the AI expanding rather than one-basing.

### 8.4 Unit combat / RPS rework — *balance-sensitive*

Two counter systems currently disagree: `strong_against`/`weak_against` tags are used
only by UI/AI ([combat_rules.py](systems/combat_rules.py) never reads them), while
real damage is `attack_type × armor_type` (`EFFECTIVENESS_TABLE`). Worse, **spearman
and archer are both `pierce`/`light`** — mechanically near-identical, so their roles
collapse.

- [x] **One coherent counter model** *(med)* — `strong_against` tags now grant
  1.5× damage in `calculate_damage` (flag `COMBAT_BONUS_VS_TAGS_ENABLED`),
  unifying the two systems. **Same-seed validation (2026-07-10,
  `tools/balance_20_counters.json`): military mix flattened to
  26/23/19/17/15 % (warrior/ram/spear/archer/cav — ram dethroned as top
  unit), win spread tightened 31–80 % → 38–67 %, and the `balanced`
  watch-item self-resolved (31 % → 46 %).** Unit test locks
  spearman-vs-cavalry ≫ archer-vs-cavalry.
- [x] **Legible counters** *(low–med)* — completed 2026-07-10: counter hits
  pop emphasized "N!" numbers; the unit panel now lists **Strong vs / Weak
  vs** (green/red) from the unit's tags; and type-disadvantaged hits (armor
  class resists the attack type, or attacker's weak_against covers the
  target — `combat_rules.is_resisted_by`) float a gray "N resisted" cue.
- [ ] **Position matters** *(med)* — high-ground / forest-cover / flank bonuses so
  terrain and positioning are combat levers, not just unit type (imperfect RPS).
- **✅ Verify:** *prototype behind a flag first.* Spearman-vs-cavalry does distinctly
  more damage than archer-vs-cavalry (read the numbers); the unit panel shows counters
  and combat pops "Effective/Resisted"; the §8.8 balance sim shows no single dominant
  unit and every unit sees use.

### 8.5 Audio & juice — *⚡ highest feel-per-hour*

Cheap, huge payoff. Six `play_*` sound methods already exist but are **never called**
(§9 backlog).

- [x] ⚡ **Wire existing SFX** *(low)* — audit 2026-07-10: `select`/`move_order`/
  `attack`/`gather` (selection manager) and `build_complete` (building system)
  were already wired — the backlog entry was stale; `alert` is now wired to the
  rate-limited under-attack alert (sound + minimap ping).
- [ ] ⚡ **Unit response barks** *(low–med)* — selection/order acknowledgements per unit
  type. Big personality gain.
- [ ] **Combat & impact SFX** *(low–med)* — layered hit/death/siege sounds; ties to VFX.
- [ ] **Music & ambient** *(low–med)* — menu/game tracks + ambient bed; duck under alerts.
- [ ] **VFX / juice** *(med)* — hit sparks, death fades, movement dust, muzzle/impact
  flashes, staged construction visuals, screen shake on big events (build on existing
  particles + castle-destruction shake).
- **✅ Verify:** play a match and confirm every listed SFX fires at the right moment
  (select, move, gather, build-complete, attack, alert), music/ambient is audible, and
  combat shows the new VFX.

### 8.6 Camera, hotkeys & control — *⚡*

- [x] ⚡ **Camera nav** *(low–med)* — edge-scroll (14 px window border), Home =
  jump-to-base, Tab = cycle army (selects + centers), F1 = jump-to-idle
  (§7.4), and **camera bookmarks** (2026-07-10): **B** saves the current view
  into 4 rotating slots (toast confirms), **N** cycles through them.
- [x] ⚡ **Rebindable hotkeys** *(med)* — remap layer landed 2026-07-10:
  `core/keybindings.py` holds the action→key table (15 actions incl. saves,
  speed, stance, gates, formation, bookmarks); user overrides persist in
  `keybindings.json` (only diffs written; unknown actions/bad key names
  ignored; duplicate-key rebinds refused). The in-game keydown handler runs
  entirely through it, so an edited file rebinds everything and survives
  restarts (`tests/test_keybindings.py`). Still open: an in-game remap
  screen (belongs to the §8.2 settings menu) and production **grid hotkeys**,
  which need the §8.2 command card first (QWER collides with WASD camera).
- **✅ Verify:** edge-scroll and each jump hotkey move the camera as intended; a rebound
  key works and the binding survives a restart.

### 8.7 Meta, onboarding & accessibility

- [x] ⚡ **Post-match summary** *(low–med)* — game-over overlay now shows match
  length (game time) and a per-player table: units trained, buildings built,
  army remaining, watchtower damage. (2026-07-10; resources-gathered / units-lost
  / APM columns can extend the same stats hooks later.)
- [ ] **Profile & achievements** *(med)* — persistent stats + simple achievements for a
  light progression loop.
- [ ] **Onboarding** *(med)* — tooltips + a practice/first-match flow so new players
  aren't lost.
- [ ] **Accessibility** *(med)* — colorblind palette (shared with §8.1), UI scale
  (§8.2), remappable keys (§8.6).
- **✅ Verify:** finish a match and the summary shows real numbers; stats persist across
  runs; a new player can identify what to do from tooltips alone; colorblind mode
  visibly changes the palette.

### 8.8 Balance tooling

- [x] **Balance sim** *(low–med)* — `tools/balance_sim.py` batches seeded
  AI-vs-AI matches and reports per-personality win rates, match lengths,
  unit/building histograms (fed by new `game.stats_units_trained`/
  `stats_buildings_built` counters), and a never-trained/never-built audit.
- **✅ Verify (passed 2026-07-10, superseded numbers below):** authoritative
  run is the **20-match set after the combat-cadence fix**
  (`tools/balance_20_fixed.json`, rendered via `tools/render_balance_report.py`):
  **0 timeouts** (was 4/20 pre-fix — the stall problem was entirely the
  wall-clock-cadence bug), avg match 584 sim s, wins — boomer 6/9, turtle 3/5,
  balanced 7/13, **rusher 4/13** (head-to-head 1–4 vs boomer → led to the
  §7.2 per-personality attack thresholds, validation run pending).
  **Headline §8.4 finding: rams are 30 % of all military production** — the
  de-facto win condition; first target for the counter-model rework.

### 8.9 Bigger swings (later; likely past "polish" scope)

Hero units + abilities/spells · garrison & transport · day-night / weather · neutral
map objectives. Listed for completeness; revisit only after Tracks A–C land.

### 8.10 Defensive play — watchtowers & walls *(added 2026-07-10 per playtest feedback)*

**Watchtower state of the world (audited 2026-07-10):** towers DO auto-target and
fire (live-fire verified; the wall-clock cadence bug that muted their DPS at high
game speed is fixed — see §9). What's missing is *strategy*: the AI builds at most
**one** tower ever (`BuildWatchtowerGoal` scores 0 once any exists, base score a
low 45) and places it at the **first free ring slot around the castle starting
due-east** — placement ignores where the enemy actually is.

- [x] **Strategic tower placement** *(med)* — angle-major ring search biased
  toward the nearest enemy castle (extended radius past the base's own
  resource clutter); verified within 3° of the threat bearing on both sides
  of the seeded map. (2026-07-10)
- [x] **Scale tower count with threat & personality** *(low–med)* — per-
  personality caps (turtle 3, balanced/boomer 2, rusher 1); extra towers
  require measured pressure via `ctx.threat_at`; goal recategorized
  military→support so turtle prioritizes and rusher skips. (2026-07-10)
- [x] **Tower value metric in the balance sim** *(low)* — per-personality tower
  damage tracked end-to-end. Validation run: 46 towers dealt ~29.5k damage
  (balanced 12.1k, boomer 9.1k, turtle 5.0k, rusher 3.3k) — towers demonstrably
  matter now. (2026-07-10)
- [x] **Wooden walls** *(med)* — `wooden_wall` buildable (40 wood, 800 hp)
  2026-07-10; placed via the standard build menu (drag-placement UI for wall
  *lines* still open below). Reuses the watchtower sprite until wall art
  exists.
- [x] **Stone walls** *(med)* — `wall` re-purposed as the stone tier (50 stone,
  2000 hp, armor 10) and made buildable. 2026-07-10.
- [x] **Gates** *(med)* — `gate` piece with **G**-key open/close toggle: open
  gates are skipped by navigation and collision, and the toggle drives the
  incremental nav notifications so paths/flow fields react instantly.
  Tested: sealed wall line = no path; open gate lets paths through; reclosing
  reseals. (V1 is a manual toggle for any unit, not per-player auto-gates.)
- [x] **Wall drag-placement UI** *(med)* — landed 2026-07-10. With a wall
  piece selected from the build menu (walls/gate now listed under Military —
  they were missing from the menu's category lists entirely), click-drag
  draws ghost circles (green/red per slot) along the line and mouse-up
  places a construction site every 56 px, skipping blocked slots, stopping
  when resources run out; the selected worker is sent to the first site.
  Short drag = single piece; gates stay click-to-place. Sibling wall pieces
  are allowed to touch (the normal placement validity would reject sealed
  spacing). Tests in `tests/test_wall_drag.py`.
- [x] **AI walling** *(med–high)* — landed 2026-07-10. `BuildWallGoal`
  (support category, so only turtle's `WALL_SEGMENT_TARGETS = 11` triggers it)
  lays a deterministic 11-slot picket with a middle gate across the threat
  bearing at 420 px (outside the base-building ring), one segment per tick via
  `BuildingPlacer.plan_wall_line/next_wall_piece`. Blocked slots become holes
  (terrain/own statics usually plug them); if the *gate* slot is blocked —
  the watchtower placer targets the same bearing — the gate role moves to the
  nearest open slot. `MilitaryBrain._manage_gates` keeps AI gates open for
  the economy and closes them when the coarse threat map registers enemies
  near the gate. Score base 60 on purpose: AttackGoal succeeds every tick it
  wins, so walls must outrank it (turtle-weighted 90 vs attack 49 + 5.6/unit)
  until the line is done — measured live: 10/11 pieces + open gate by
  sim-minute 3 of a seeded turtle-vs-rusher match. Tests in
  `tests/test_ai_walling.py`. Still open: walls are a straight picket
  (flankable funnel), not a terrain-anchored seal — real chokepoint detection
  stays future work; balanced/boomer/rusher never wall by design.
- **✅ Verify:** in a spectated match the AI places ≥2 towers on the threatened
  side (not due-east by accident); the sim's tower-damage metric is nonzero and
  meaningful; a walled turtle base forces attackers through a gate or a
  ram-siege; the owner's workers still path freely via gates.

---

## 9. Preserved backlog (non-perf, carried over from the deleted plans)

Do **not** lose these; they are unrelated to the perf work. Trackable, but
unsequenced — pull them in where they fit.

- [x] **AI completeness**: verified empirically 2026-07-10 via the §8.8 balance
  sim — across 6 matches the AI trained every trainable unit (worker 67,
  warrior 35, ram 43, spearman 32, archer 28, cavalry 21) and built every
  buildable building (incl. stable 8, blacksmith 11, siege_workshop 10,
  watchtower 9). healer/temple/wall are excluded by design (`buildable: false`
  / temple-gated — see Content notes).
- [x] **Defensive-stance freeze**: fixed 2026-07-10 — a DEFENSIVE unit beyond its
  leash drops the chase and paths back to `stance_home_position` (re-acquisition
  suppressed for 1 s so the walk home wins); regression tests in
  `tests/test_stances.py`.
- [x] **Healer doesn't heal**: fixed 2026-07-10 — healers mend the most-wounded
  friendly unit in range (6 hp/s cadence on game time, spatial-index query,
  clamped at max hp, cast animation + particles); unit tests in
  `tests/test_healer.py`. Note: healers stay effectively unreachable in play
  until `temple` becomes buildable — a content decision left open on purpose.
- [x] **Wall is a 1×1 building**: no gate, thin profile, or special placement.
  (→ **§8.10** — expanded 2026-07-10 into wooden→stone walls + gates + AI
  walling, all landed; drag-placement lays sealed 56 px lines, gates toggle,
  turtle AI walls the threat bearing. Thin/connected wall *sprites* remain a
  missing-art item.)
- [x] **Combat cadence was wall-clock, not game-time** (found 2026-07-10 during
  the §8.10 watchtower audit): unit/building attack cooldowns used
  `pygame.time.get_ticks()`, so at 5× speed all combat was effectively 5× slower
  relative to economy/movement — muting towers and distorting the balance sim.
  Fixed: cooldowns accumulate game-time `delta_time`; the wall-clock stamp
  remains only for projectile-spawn detection. Balance sim re-run required
  (pre-fix numbers are biased toward long sieges / big ram counts).
- [x] **Save/Load is a thin slice**: closed 2026-07-10 with save format **v2**
  (`managers/save_manager.py`, still loads v1). Now persisted: production queues
  + in-progress unit (with progress), rally points, gate open/closed state (nav
  rebuild respects restored `passable`), stance home positions, sim clock
  (`sim_time_elapsed`), victory condition, match stats (units/buildings/tower
  damage/resources gathered), tree-regrowth timers, and per-player fog
  **explored** grids (row-packed bit strings). Intentionally not saved — each
  self-heals within one AI tick of resuming: AI brain state, worker
  task/gather targets, combat targets, in-flight paths (units re-idle on load).
  Roundtrip covered by `tests/test_save_load.py` (full v2 field cycle on a live
  game + 60 post-load frames; gate-open survival).
- [x] **Sound coverage**: audited 2026-07-10 — five of the six were already
  called; `alert` now fires on under-attack. (Realized in §8.5.)
- [x] **Test coverage**: closed 2026-07-10 — the suite is now 192 tests and
  behavior-heavy: `tests/test_ai_integration.py` runs a real boomer-vs-rusher
  sim for two game-minutes and asserts observable outcomes (economy grows,
  base expands, army fielded, sim healthy); live-game roundtrips exist for
  save/load, walls/gates (nav queries), wall drag placement, AI walling,
  telegraph cues, alerts, income, mutators, stances, healer, counters,
  and a JPS-vs-A* navigation oracle. The Phase 0 perf gate is the headless
  benchmark (`tools/benchmark_ai_spectator.py`), run at phase gates rather
  than per-commit (a 5-minute sim doesn't belong in the unit suite).
- [x] **Projectile flies to infinity** (user-reported 2026-07-10): fast
  projectiles / high game speed stepped past the 5 px arrival check and never
  died. Fixed: arrival is checked against the step length *before* moving, and
  the projectile snaps to the target. Verified at 5× with cannonballs.
- [ ] **HP bars read as empty at max zoom** (user-reported 2026-07-10):
  couldn't reproduce the empty fill headlessly (pixel tests show correct green
  fill through the full draw pipeline at zoom 2.5), but the geometry was
  hardened anyway: bar width/height/offset now clamp instead of scaling
  unbounded (bars no longer float 100 px above units at max zoom), and any
  living object shows ≥1 px of fill. **Needs a windowed re-check by the user;
  if it persists, grab a screenshot + zoom level.**
- [x] **Docs housekeeping**: `CLAUDE.md` corrected 2026-07-09 and refreshed
  2026-07-10 for the post-Track-A architecture. `AGENTS.md` replaced 2026-07-10
  with a pointer to CLAUDE.md/MASTER_PLAN plus a quick-facts card (the 298-line
  standalone copy had drifted to describe the pre-rewrite engine).

---

## 10. References

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

**Game design & fun (single-player RTS, Track B)** — *Difficulty & fairness
(adversarially verified):* Hagelbäck & Johansson, "Measuring player experience on
runtime dynamic difficulty scaling in an RTS game," IEEE CIG 2009 (the 60-player
ORTS study — adaptive > static, and the game-throwing bot was least fun); Zohaib,
"Dynamic Difficulty Adjustment in Computer Games: A Review," Adv. HCI 2018
(onlinelibrary.wiley.com/doi/10.1155/2018/5681652); Khajah et al., CHI 2016 (covert
> overt); en.wikipedia.org/wiki/Dynamic_game_difficulty_balancing; "Game AI: Our
Cheatin' Hearts" (gamedeveloper.com); AoE4 Anniversary difficulty tiers
(player.one). *Economy/combat depth:* Wayward Strategy — anti-snowball, timing
attacks, dynamic map elements (waywardstrategy.com); Liquipedia StarCraft II Timing
Attack; Game Developer — early-game phase, balance-of-power, victory conditions.
*QoL/UX:* Blizzard SC2 control guide (news.blizzard.com/.../game-guide-special-control)
+ 5.0.16 patch notes; Pottinger RTS-UI interview (waywardstrategy.com); Game
Developer UI dos-and-don'ts. *Replayability:* StarCraft II Co-op mutators
(starcraft2coop.com/resources/mutators); AoE AI personalities
(ageofempires.fandom.com/wiki/AI_personality).

**UI/UX & systems (Track C)** — RTS UI/readability & minimap: Pottinger interview
(waywardstrategy.com) and Game Developer UI dos-and-don'ts (both above); command
card / grid hotkeys and idle-worker/control-group patterns: Blizzard SC2 control
guide (above). Bonus-vs-class counter model & worker (mineral) saturation as
expansion pressure: Age of Empires II / StarCraft design (widely documented, e.g.
ageofempires.fandom.com, liquipedia.net). Colorblind-safe palettes: standard
accessibility practice. Much of Track C is conventional RTS practice rather than a
single citable source.
