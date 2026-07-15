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
  - **Status 2026-07-13 (fresh measurement + one more profile-backed win):**
    standard benchmark (120 s, 4p): avg **2.4** / p95 **11.5** / max **23** /
    teleports **0** — all targets met. 8-player war (300 s, ~87 u): avg
    **6.7** ✓ / p95 **16.3** ~borderline / max **61** ✗ / ai_max **4.2** ✓ /
    teleports ~2.4/min ✗. 200-unit march: avg **17.6** ✗ / p95 18.9 ✗ /
    max 30.5 ✓ — steady-state steering cost, not spikes. **Quick win
    landed:** `_goal_pocket_reachable` now memoizes CLOSED pocket sets
    (was ~19 % of profiled war time — every unit attacking a sealed target
    re-flooded the same pocket per request); war max 74→61,
    `path_queue_failed` 660→432. **Named residual kernels (fresh cProfile,
    `tools/war8p.prof`):** `jump_straight`+`walkable` ≈23 s cum of a 57 s
    profiled war (the JPS scan kernel — the numpy/Numba port target) and
    per-unit context steering at 200-unit scale. These are the genuine
    Phase 6 items; no cheaper structural win remains visible in the
    profile.

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
- [x] **Reactive counters** *(med)* — landed 2026-07-10 after a two-cycle
  same-seed A/B: barracks production targets blend the signature composition
  with a boost for units whose strong-vs tags cover the enemy's fielded army
  (≥4 enemy military to react; `tests/test_reactive_counters.py`).
  **Cycle 1 (weight 0.5, `balance_20_reactive.json`)**: boomer dethroned
  67→33 %, turtle 40→60 % (walls work: 47 built) — but matches +49 % longer
  (timeouts 1→3) and the warrior↔archer mutual-counter loop concentrated the
  mix (cavalry 15→7.5 %). **Cycle 2 (softened to 0.25/cap 0.6,
  `balance_20_reactive_soft.json`) — KEEP**: tightest win spread of any run
  (balanced 46 / boomer 56 / rusher 46 / turtle 40 %), timeouts back to 1,
  avg match 671 s (walls legitimately lengthen sieges vs 559 baseline), mix
  restored to 26/21/18/11/24 % (warrior/archer/spear/cav/ram — no dominant
  unit). This is the new authoritative §8.8 dataset.
  Original scope: AI scouts the player's composition and shifts
  production toward counters instead of a fixed comp. Rides on Phase 4.
- [x] **Fair perception** *(med)* — 2026-07-10: with fog on, the AI blackboard
  only contains enemy **buildings it has explored** (remembered once seen —
  buildings don't move) and enemy **units it can currently see**; the threat
  map, attack targeting, tower/wall bearings, and reactive counters all
  inherit the scouted view, so the AI hunts with its scout before it can
  hunt with its army. ~~Spectator mode / balance sims run fog-off and stay
  omniscient~~ **(superseded 2026-07-14, user report: AIs built across the
  map in spectate)** — fog RULES now always apply to AI players; spectator
  mode only reveals the *display* (`SPECTATOR_REVEALED_DISPLAY`,
  `game.spectator_reveal_display`), and the `revealed_map` mutator remains
  true omniscience for everyone as a game rule. Balance sims therefore run
  fair now (see §8.8 re-baseline). Verified live: a blind AI
  in a human match still grows its economy, expands exploration, and builds
  (`tests/test_fair_perception.py`, incl. a 3-game-minute integration run).
  Pairs with the fog work.
- [x] **Optional covert DDA** *(med)* — 2026-07-10: **off by default**, opt-in
  via the settings menu ("Adaptive difficulty"). Within the chosen tier it
  nudges only AI *reaction time* (the §7.1 guardrail — never stats or
  resources): human below half the AI's score → AI tick interval ×1.5;
  above double → ×0.75; close games untouched. Score = the §7.5 timed-victory
  metric. Tests in `tests/test_dda.py`. Original scope: nudge AI
  aggression/expansion (never stats) toward even matches; hidden, coherent, never
  throwing.
- **✅ Verify:** play a match against each personality at ≥2 tiers — openings differ,
  the higher tier is harder *without feeling like it cheated* (§7.1 guardrails hold),
  and the §8.8 balance sim shows no single personality/tier dominating win-rate.

### 7.3 Economy & combat decision depth

- [x] **Power spikes / timing** *(low)* — 2026-07-10: research completion is
  now a moment — sound + "Research complete" alert/ping (own techs), and a
  gold "+Tech Name" float over every affected unit (both players, capped at
  15; affected types derived from the tech's effect keys, gather techs →
  workers). Tests in `tests/test_power_spikes.py`. Original scope: tech/upgrade completion a visible,
  meaningful army-strength jump so "attack right after Forged Blades finishes" is a
  real decision. Mostly surfacing existing upgrades + feedback.
- [x] **Legible, imperfect counters** *(low–med)* — realized via §8.4
  (2026-07-10): strong/weak-vs in the unit panel and every tooltip;
  emphasized "N!" counter pops and gray "N resisted" floats; the 1.5×
  tag bonus stays *imperfect* — armor/type multipliers, upgrades, and
  positioning still decide fights (validated: no dominant unit in the
  same-seed mix). Terrain bonuses remain the separate §8.4 "position
  matters" item.
- [x] **Risk/reward economy** *(med)* — landed 2026-07-13 on three pillars:
  (1) **worker saturation is live** (was prototype-flagged) — a node's total
  yield caps at 3 gatherers, so income growth *requires* forward dropoffs;
  the income-vs-worker-count curve the plan asked for is
  `tools/chart_worker_saturation.py` → `tools/saturation_curve.json`
  (one node goes flat at the cap, two nodes keep climbing).
  (2) **Raids punish greed**: `_find_attack_target` no longer beelines the
  castle — a raid-sized army (≤7, rusher ≤12) prefers the least-defended
  enemy *economy* building (lumbermill/mine/quarry/farm) when it's
  meaningfully softer (<0.6×) than the castle's threat. Fog rules hold:
  the AI can only raid expansions it has scouted, and cavalry (the raid
  unit) now actually gets fielded (§8.3 fix).
  (3) **The window is scoutable both ways**: first-sighting intel alerts
  (§7.3 scouting payoff) already announce enemy expansions to the human.
  Tests in `tests/test_risk_reward.py`.
- [x] **Anti-snowball / comeback** *(med)* — 2026-07-10 as the **comeback
  mutator** (opt-in, keeping default balance untouched): any player —
  human or AI, symmetric — below 60 % of the score leader gathers 15 %
  faster (recomputed once per second). Softens foregone losses without
  punishing the leader directly. Whether it should become a default rule
  is a playtest call — flip it on in match setup to try.
- [x] **Scouting payoff** *(med)* — 2026-07-10: first-sighting **intel
  alerts**, strictly fog-gated (earned by scouting; none when fog is off):
  the first time the human sees each enemy military unit type → "Enemy
  cavalry spotted!" (+ping), and per-opponent key buildings (castle,
  barracks, stable, siege workshop, blacksmith, watchtower) → "Enemy siege
  workshop located!" — production buildings ARE the tech reveal. Once per
  type/building per match. With the §8.4 counters UI, sighting → informed
  build response is closed. Tests in `tests/test_scouting_intel.py`.
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
- [x] **Readability pass** *(med)* — HP bars, team-color clarity, hover/selection
  highlights, damage/heal floats.
  - *(2026-07-11)* **Directional sprite mirroring** landed (user request):
    sheets face right; units moving left render mirrored (cached flip in
    the renderer), facing persists while idle, and `start_attack` faces
    the target so combat never plays backwards.
  - *(2026-07-13)* **Completed**: HP-bar borders now carry the **owner's
    player color** (fill stays HP-coded green/yellow/red) so friend/foe
    reads at a glance; **hover highlight** — a thin ground ellipse under
    the object beneath the cursor (white-gray own / amber enemy / gray
    neutral), fed by the existing cursor-context probe, fog-checked, and
    dropped when the object dies; **heal floats** — green "+N" over units
    the healer mends (damage/counter/resisted floats already existed).
    Tests in `tests/test_readability.py` + rendered-frame verification.
    Always-on HP bars kept deliberately (prior user feedback favored
    visible bars).
- **✅ Verify:** each item is observable in-game — idle-worker key selects/cycles and
  the badge counts; double-tap centers; Shift queues; rally points path new units;
  alerts fire *and* ping *and* play sound; right-click gathers; every order gives a
  visible/audible cue.

### 7.5 Replayability — *cheap match-to-match variety; mostly **⚡***

- [x] ⚡ **Match-setup screen** *(low)* — `screens/match_setup.py` (from Start
  Game): play-vs-AI or spectate, 1–7 opponents, AI personality, map seed
  (R rerolls), game speed. (2026-07-10. Not yet: map size, per-opponent
  personality, resource richness — extend the same rows when wanted.)
  - *(2026-07-11, user request)* **Map size row added** (Tiny 45² / Small
    60² / Medium 70² / Large 85² / Huge 100², `config.MAP_SIZES`) with the
    **player count capped by map size** (Tiny 2, Small 4, Medium 6,
    Large/Huge 8) — shrinking the map clamps the opponents row live, and
    the cap shows in the value ("Tiny (up to 2 players)"). Resource counts
    already scaled by map area. **Game-speed row removed** (settings'
    default + in-game [ ] keys own it). Saves store the map size so a load
    rebuilds matching dimensions (`SaveManager.peek_map_size`).
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
- [x] **Dynamic map elements / random events** *(med)* — v1 landed 2026-07-10
  behind the **random_events** mutator (`systems/dynamic_events.py`): every
  ~3 sim-minutes (±60 s jitter) either a **resource boom** (3-node 2×-rich
  gold/wood/stone cluster on open ground ≥400 px from every castle, alert +
  ping; AI picks it up through normal fog-gated resource discovery) or a
  **bumper harvest** (every farm's food tick fires immediately). Mutator-
  gated on purpose so default matches and the §8.8 balance baseline stay
  event-free. Wandering hostiles/weather need neutral-unit AI — still future.
  Tests in `tests/test_dynamic_events.py`.
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
**→ The ground-up rework is specced in §8.2.1 below (researched 2026-07-10 at the
user's request); the checklist items here are its inputs/prerequisites.**

- [x] **Resolution independence + UI scaling** *(med–high)* — landed
  2026-07-11 as §8.2.1 Phase D: `config.apply_resolution()` recomputes the
  derived map-view size from any startup resolution, and every HUD element
  is anchored (top bar spans to the minimap, sidebar/card anchor right,
  strip/alerts/log anchor left, camera math uses the derived view size).
  Verified clean at 1920×1080 by rendered frame — which also exposed and
  fixed a fog gap on the map's last hex column/row (previously hidden under
  the 720p sidebar). Remaining niceties, deliberately out of scope: live
  window resizing (resolution applies at startup) and DPI *scaling* of
  fonts/tiles (the HUD keeps its pixel size and the map view grows).
- [x] **Command card / action grid** *(med)* — first pass 2026-07-10 (from
  windowed user feedback "this is very bad"): the build menu and unit
  production are now matching **2-column icon-tile grids** — icon on top,
  wrapped name, compact cost line ("150G 100W") that never clips — with
  muted availability states (green-bordered buildable / tan "requires X" /
  red-tinted unaffordable, dimmed icons), hover highlight, tooltip on top.
  All 8 military buildings fit on screen at 720p (rows used to clip text
  AND overflow past the screen bottom — stone wall/gate were unreachable).
  Production adds a status strip (unit, %, queue depth) under the tiles.
  Top-bar overlap fixed (idle badge anchored left of Speed/Fog, redundant
  hint removed). Verified by rendered-frame screenshots.
  **Completed 2026-07-11 by the §8.2.1 Phase A unified command card**
  (grid hotkeys + unified per-selection actions, bespoke panels deleted).
- [x] **Multi-select panel** *(med)* — 2026-07-10: mixed selections now render
  grouped by unit type (biggest group first) with an ×N count badge per icon
  and an aggregate health bar (sum hp / sum max), so a 40-unit army fits the
  panel instead of overflowing a per-unit grid. Tests in
  `tests/test_multi_select_panel.py`. (Click-icon-to-filter-selection can
  ride the §8.2 command-card pass.)
- [x] ⚡ **Settings menu** *(low–med)* — landed 2026-07-10: Settings entry in
  the main menu (`screens/settings_menu.py`) with resolution (720p/900p/1080p,
  applied at startup — main.py patches `core.config` before UI modules import
  the constants; live layout awaits the resolution-independence rework above),
  volume + sound on/off (live via `SoundManager.set_volume`), and default
  game speed. Persisted as diffs in `settings.json` (`core/settings.py`,
  git-ignored); hotkey *rebinds* live in §8.6's `keybindings.json` — an
  in-game remap UI is the remaining piece of both items. Tests in
  `tests/test_settings.py`.
- [x] **Universal tooltips** *(low–med)* — completed 2026-07-10: every hover
  tooltip now carries name/role/description, **cost + build/research time**,
  and counters. Units (production panel): display name, role, cost line,
  strong/weak-vs. Techs: display name, effect tooltip, cost + research time,
  availability reason. Buildings (build menu): role, cost, availability
  reason, strong/weak-vs. Selected units additionally show counters in the
  unit panel (§8.4).
- [x] **Event/notification feed** *(low–med)* — 2026-07-10: every alert also
  lands in a 50-entry history stamped with game time; **L** (rebindable)
  toggles a bottom-left log panel showing the last 10 as `mm:ss — text`.
- [x] **Menu polish** *(low–med)* — audited 2026-07-10: main menu, match
  setup, settings, pause, and victory/summary overlays all lay out from
  `SCREEN_WIDTH/HEIGHT` (no hardcoded resolutions anywhere outside config),
  so they scale with the §8.2 settings-menu resolution, and they share the
  same dark-panel style (bg 20/20/30, gold titles, highlight rows).
  Original scope: main/pause/victory screens scale and share the
  visual language.
  - *(2026-07-11)* **Visual upgrade pass** (user: "they look horrible"):
    `screens/theme.py` centralizes the language — splash-art backdrop,
    rounded scrim panels with gold borders, shadowed gold titles,
    label/value rows with adjuster arrows, green primary action buttons.
    Match setup + settings restyled with it (also fixed: match setup's
    Back row clipped off-screen at 720p), and the bare "PAUSED" text is
    now a real **pause menu** — Resume / Settings / Quit to Menu,
    clickable, with gameplay clicks blocked while paused. Victory/summary
    overlay is the remaining screen still on the old flat style.
  - *(2026-07-11, same day)* **User-generated frame art wired in**:
    `assets/ui/panel_frame.png` (stone panel with gold filigree border)
    now textures every scrim panel, and `assets/ui/button_frame.png` is
    3-sliced (fixed ornate end caps, stretched middle) into every menu
    row/button with programmatic state tints — dimmed normal, warm-glow
    selected, green-shifted primary. Main menu options became framed
    buttons too. Flat rounded rects remain as the fallback when the art
    files are missing.
- **✅ Verify:** resize the window to a non-720p size and confirm the HUD lays out
  correctly with no clipping; the command card issues actions; tooltips appear on
  hover; settings changes persist across a restart.

### 8.2.1 GUI ground-up rework — research-backed design spec *(2026-07-10, updated 2026-07-11)*

User verdict on the interim tile-grid pass: **"The GUI needs a rework from
ground up."** Two deep-research passes ran on how RTS games structure
build/production UI. Source reliability is mixed on purpose — noted per claim:

- **✅ Verified** = passed adversarial panel review (3 independent votes).
- **Sourced** = pulled from a primary source (official docs, a studio designer
  diary, or the game's own published config/hotkey files) but the verification
  panel didn't reach it (rate-limited both runs) — treat as reliable, not proven.
- **✗ Refuted** = a specific detail the panel checked and rejected; superseded
  below.

*(A second research attempt burned far more budget than it should have —
re-running a 100-agent workflow twice for a handful of net-new verified facts
was a bad call; this update was written from what was already gathered,
without spawning further agents.)*

**What the genre does:**

1. **Two proven placements.** The **right sidebar** (Dune II 1992 → RA2 → C&C3)
   stacks credits/radar/build-list vertically. Its defining advantage, per EA's
   own C&C3 designer diary, is **global production control — build anything from
   anywhere without moving the camera** (Sourced: GameSpot designer diary #3).
   The **bottom command card** is the Blizzard/Ensemble lineage: a
   *context-sensitive* card for the current selection, with control groups
   carrying the "produce from anywhere" job instead. C&C Generals moved to a
   bottom bar because it was the genre norm; C&C3 deliberately moved back to the
   sidebar and modernized it (Sourced: cnc.fandom.com/wiki/Sidebar).
2. **Scaling to many buildings = categories + tabs, not bigger lists.** RA2:
   four sidebar tabs (buildings / defense / infantry / vehicles) hot-switched
   with Q/W/E/R and a 30-deep queue. C&C3: five category tabs with per-factory
   sub-tabs (each factory its own queue; double-click jumps the camera to it),
   rendering **only currently-producible buttons** — locked items show a lock
   glyph instead of a dead row (Sourced: cnc.fandom.com/wiki/Sidebar).
3. **Grid hotkeys are position-mapped, and one real config confirms exactly how.**
   Beyond All Reason's own hotkey files (✅ **Verified**, 3-0) map **12 slots as
   a 3×4 grid across the physical Z/X/C/V, A/S/D/F, and Q/W/E/R rows** — not
   mnemonics, raw key position. More importantly: **BAR reuses the same four
   keys for two jobs** — unmodified `Z/X/C/V` pick one of exactly **4 build
   categories**, and once a category is open, an `Any+` modifier layer turns
   those *same physical keys* into grid-position slots (✅ Verified, 3-0). That
   is a directly reusable pattern for a 2-category, ≤12-item roster like ours.
   One specific claim about BAR — that overflow beyond 12 slots is handled by a
   dedicated `B` paging hotkey — was **✗ refuted** (1-2 votes); BAR's actual
   overflow/paging mechanism is genuinely unclear across its two hotkey config
   files (`grid_keys.txt` vs `gridmenu_keys.txt` disagree on key rows used), so
   don't copy a paging scheme from BAR without checking the live game. Separately,
   Ensemble's Dave Pottinger has said on record he personally dislikes
   QWERTY-grid hotkeys and would offer them as an option, not force them
   (✅ Verified, 3-0, waywardstrategy.com interview) — reinforcing: ship grid as
   default, always remappable.
4. **Multi-building production is the real scaling mechanism** (SC2 model):
   production buildings join control groups; Tab cycles subtypes inside a mixed
   group; one keypress queues one unit **at the shortest queue** in the group;
   one right-click rallies every selected building (Sourced: Blizzard's own
   control-group guide, corroborated by Liquipedia and a hotkey-analysis
   site — three independent sources agree, though none passed the panel this
   round). **Batch-queue-size is a converging convention, not one game's quirk:**
   AoE4 uses Shift = queue 5 (Sourced: Xbox Wire hotkey reveal); **BAR's own
   changelog confirms the same default** — Shift queued 5, Ctrl(-1) removed one
   from the queue — and BAR has since made the quantity **user-configurable up
   to arbitrary batch sizes** (✅ Verified, 3-0 both, beyondallreason.info
   microblog). Two unrelated lineages landing on "5" independently is a good
   signal it's the right default, with configurability as the natural next step.
   AoE4's Season 1 also added a persistent **Global Build Queue** HUD strip
   showing everything in production everywhere, Ctrl+click to cancel (Sourced:
   player.one Season 1 notes).
5. **Rally points are exactly the UX we already built.** Official AoE4 guidance
   — select a production building, right-click a destination (including a
   resource node), new units auto-walk there — is **✅ Verified (3-0,
   ageofempires.com)**, and it is **already what our rally-point feature does**
   (`§7.4 Rally points`, shipped 2026-07-10). No change needed; this is a
   confirmation, not a gap.
6. **Icon+cost+tooltip + explicit disabled states** are universal: cost on/near
   the tile, rich tooltip on hover, unaffordable = dimmed, locked = lock icon +
   prerequisite line — consistent across every sourced example above, already
   partially shipped in the interim tile-grid pass.

**Recommendation for this game** (200 px right panel, minimap top-right, 1280×720
base, 13 buildings / 2 categories, 7 units, single-player, mouse+keyboard):

**THE CORE FIX — how the builder's build menu is shown.** This is the thing the
user actually complained about, twice. Current flow (`ui/components/building_menu.py`):
select worker → panel opens on a **category picker** (two big Economy/Military
buttons, *zero buildings visible*) → click a category → see ~6-8 tiles → click
**Back** to reach the other category. **You can never see all 13 buildings at
once; every building is 2 clicks + scanning away.** That two-level modal
drill-down is the problem — not the tile styling (already fixed in the interim
pass).

Fix: **kill the drill-down. Always-visible category tabs, never a picker screen.**
- Select worker → the card immediately shows **[Economy | Military] tab chips**
  across the top with one category's grid already displayed (default Economy).
- One click (or Q/W) swaps the visible category. **No "Back" step, no blank
  picker.** You're always one click from any of the 13 buildings.
- ~6-7 buildings per category in a 2-wide grid = 3-4 rows, fits the 200 px panel
  with no scroll. (If a category ever exceeds ~8, page or scroll *within* the
  grid — never re-introduce a drill-down.)
- The tab you last used is remembered while the worker stays selected.
This is the RA2/BAR always-on-tab model applied to the *mouse* flow, and it's
Phase A's headline deliverable. Everything below (grid hotkeys, batch
production, global queue) is secondary depth — do it after the flow is fixed.

**Keep the right sidebar — do not move to a bottom bar.** The C&C3 rationale
maps exactly onto a comfy single-player RTS: global production without camera
trips beats APM-style control-group juggling, and our vertical budget (top bar
already takes 100 px of a 720 px window) can't afford a bottom HUD strip too.
The rework is to make the sidebar a **real command card system** instead of
today's bespoke panels:

- **Phase A — unified sidebar command card**: one context-sensitive card
  component replaces `building_menu` / `production_panel` / per-type panel code
  paths. Fixed anatomy top-to-bottom: minimap → **selection block**
  (portrait/grouped icons + stats) → **action card** (fixed 2×4 tile grid) →
  status strip. Card content switches by selection: worker → 2 category chips
  (Economy/Military — **reuse the BAR pattern**: the same physical keys pick a
  category when none is open, then become grid-position slots once one is)
  + build tiles; production building → unit/tech tiles; military → stance/
  formation/stop tiles. Same tile anatomy everywhere (icon, wrapped name,
  compact cost, state colors — the interim pass's tile style is the seed).
  **Position-mapped grid hotkeys** on the 2×4 card: `Q W / A S / Z X / C V`
  printed on tile corners, driven through `keybindings.json`
  ("card_slot_0..7"), always remappable per Pottinger's caveat.
- **Phase B — multi-building production (SC2 model)**: drag/Shift-click
  selection of multiple own production buildings + buildings joining control
  groups (units-only today); a production tile press queues at the **shortest
  queue** among selected; one right-click rallies all (matches the AoE4-
  verified UX we already ship, extended to groups); Tab cycles subtypes in
  mixed selections; **Shift+tile = queue 5** as the default batch size (two
  independent lineages converge on 5), with the quantity **configurable in
  settings** (BAR's confirmed evolution — don't hardcode 5 forever).
- **Phase C — global production visibility (AoE4 model)**: a slim **global
  build queue strip** docked under the minimap — live icons + progress for
  every unit/tech in production anywhere; click jumps camera to the producer,
  Ctrl+click cancels (refund rules already exist). Plus one
  select-all-military-production hotkey through the keybindings layer.
- **Phase D — resolution independence** (the existing §8.2 item): anchor-based
  layout so the card scales beyond 720p. Kept last on purpose: the card is
  designed at fixed 200 px first, then generalized — don't block the UX fix on
  the layout-engine rework.

**Conventions locked in** (already partially shipped in the interim pass, keep
in the rework): tile = icon + wrapped name + compact cost ("150G 100W");
unaffordable = dimmed icon + red-tint cost; locked = tan tile + "Requires X"
tooltip line (upgrade to a lock glyph in Phase A); rich hover tooltip (cost,
time, counters, description); right-click on a queued tile cancels with refund.

- [x] **Phase A (headline: fix the build-menu flow)** — landed 2026-07-11.
  `ui/components/command_card.py` replaces `building_menu` + `production_panel`
  + the 2×2 action buttons (both files deleted). Fixed sidebar anatomy:
  compact selection header (`unit_panel`, ≤118 px) → tab-chips row → **fixed
  2×4 tile grid** → status strip. Select worker → build grid shows
  **immediately** with always-visible [Economy | Military] chips — no picker
  screen, no Back; one click or **E** swaps tabs (last tab remembered).
  Card content by selection: worker → build tiles; production building →
  unit tiles + tech tiles (blacksmith techs now share the tile anatomy, with
  queued=blue / done=green states); military → Stop/Stance/Formation with
  live values; construction site → Cancel tile (the old Cancel button called
  a nonexistent `game.cancel_construction` and would have **crashed on
  click** — now routed through `building_system`); gate → Open/Close tile.
  **Position-mapped grid hotkeys**: `card_slot_0..7` = Q W / A S / Z X / C V
  + `card_tab_swap` = E in `keybindings.json` (remappable), printed as badges
  on tile corners. Slot keys are consumed **only while a tile occupies the
  slot** — otherwise they fall through to global bindings (S still cycles
  stance) and to WASD pan, which is muted per-key only then (arrows/
  edge-scroll always pan). Military actions deliberately sit on the
  **Z/X/C row** so an army selection never steals W/A/S panning.
  Verified: 254 tests green incl. 11 new in `tests/test_command_card.py`
  (per-selection content, tab swap/memory, hotkey placement/production/
  research/army actions, disabled-tile consumption, pan-key suppression,
  right-click refund) + rendered-frame screenshots of all 7 selection
  scenarios at 720p.
- [x] **Phase B** — landed 2026-07-11 (SC2 model). Drag-selecting several own
  production buildings (already supported by the selection manager) now
  drives one **union card**: tiles for every type any selected building can
  produce; a tile press queues at the **shortest queue** among its producers
  (re-evaluated per unit, so batches spread evenly); right-click removes from
  the **deepest** queue (full refund) before touching in-progress work.
  **Buildings join control groups** (`set/recall_control_group` accept
  buildings; dead ones drop out on recall) and the multi-select header groups
  buildings by type with count badges. **Shift+tile queues a batch** —
  `batch_queue_size` in settings (default 5, cycle 1–10 in the settings
  menu, persisted). Group rally was already live (§7.4) — one right-click
  rallies every selected producer. **Tab subtype cycling deliberately
  dropped**: SC2 needs it because one hotkey targets "the active subtype";
  our card gives every unit type its own position-mapped tile, so there is
  no ambiguity for Tab to resolve (and Tab is the army-cycle key). Aggregate
  status strip shows "N/M producing · K queued". Verified: 258 tests green
  (4 new: shortest-queue routing, union card, batch spread, building control
  groups) + rendered screenshot of a barracks×2+stable selection.
- [x] **Phase C** — landed 2026-07-11. `ui/components/global_queue.py`: a
  slim overlay strip listing every own unit/tech in production anywhere —
  icon, name, live progress bar, "+N" queue badge (8 rows + "+N more"
  overflow). Click a row → camera jumps to and selects the producer;
  **Ctrl+click cancels** the in-progress item (`research_manager.
  cancel_research` added: 50% refund mirroring production cancel, queued
  techs auto-start). Docked on the **left map edge** — the plan drafted
  "under the minimap" but the Phase A card's fixed grid owns that space,
  and the left edge is where AoE4 itself docks its global queue.
  **Select-all-military-production hotkey**: `select_all_production` (F2,
  rebindable) selects every own building producing non-worker units —
  straight into the Phase B group card. Verified: 261 tests green (3 new)
  + rendered screenshot (worker/warrior/tech rows with progress bars).
- [x] **Phase D** — landed 2026-07-11 (absorbs the §8.2 resolution item):
  `config.apply_resolution(w, h)` sets the screen size and recomputes
  `MAP_VIEW_*`; main.py calls it before UI modules import constants by
  value. All HUD layout was already anchor-based after Phases A–C, so
  900p/1080p lay out correctly — verified by a rendered 1080p frame, which
  also caught a pre-existing fog gap on the map's last hex column/row
  (fog rects now widen at the map edge). Live resize + DPI scaling of
  fonts/tiles remain future polish, noted in §8.2.
- **✅ Verify:** every selection type drives the same card with the same grid
  hotkeys; a barracks+stable group batch-produces to shortest queue and rallies
  with one click; the global strip shows all production and cancels on
  Ctrl+click; a full match is playable mouse-only AND (production) keyboard-only.
  - *Status 2026-07-11:* every clause covered by `tests/test_command_card.py`
    (18 tests) + rendered screenshots of 10 HUD scenarios at 720p/1080p.
    The one thing automation can't sign off is feel — a windowed
    mouse-only / keyboard-only match play-through is the remaining human
    check before calling §8.2.1 fully closed.

### 8.3 Resource model rethink — *balance-sensitive*

Today: gold/stone (1/s, carry 10, 1000-node), wood (2/s, carry 20, 600-node), food
from farms (3/s) — four resources with fuzzy identities.

- [x] **Sharpen resource identity** *(med)* — landed 2026-07-13 as a cost
  re-map (validated same-seed, see below):
  **gold = the army currency** (every non-siege combat unit + tier-2
  military buildings + techs; scarce/contested by node placement);
  **wood = renewable building bulk + bows/siege frames** (removed from
  warrior/spearman); **stone = defense & siege only** (removed from
  barracks/stable/mine/quarry; watchtower re-costed 75w/**125s**) — you
  never pay stone to unlock the economy, only to fortify or besiege;
  **food = labor** (all units, farms only). Barracks 150g/100w/50s →
  **100g/100w** so a barracks-first rush is a real opening from the lean
  100g start. Also fixed alongside (the lean-start regression from the
  §8.4 watch-item): **cavalry joined every personality's composition
  target** (rusher/balanced 0.15, boomer 0.10, turtle 0.05),
  `TrainCavalryGoal` is composition-driven like the barracks units, and
  `BuildStableGoal` outranks flat train goals once a core army exists.
- [x] **Worker saturation** *(med)* — prototyped behind
  `WORKER_SATURATION_ENABLED` (2026-07-10): past 3 gatherers a node's total
  yield stays flat (each stacked worker gathers at cap/n rate). Verified:
  per-worker rate exactly halves at 6 gatherers. The AI's existing crowding
  penalties already push it to spread across nodes; the full §8.8
  income-vs-worker-count charting remains for the tuning pass.
- [x] **Gathering range/flow tuning** *(low)* — audited 2026-07-13:
  `GATHERING_DISTANCE_MULTIPLIER` was **dead code** (defined, never read —
  removed). The real formula lives in `gathering_manager.get_gathering_distance`
  / `get_drop_off_distance`: combined radii + 10% + 5 px, plus a generous
  interaction tolerance — workers do not actually hug nodes; the config
  comment was describing a wiring that never existed. No feel change needed.
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
- [x] **Ram glass-cannon rebalance** (user-reported 2026-07-11: "way too
  powerful — should hit hard but die easily"): old ram was hp 650 / armor 2
  — with pierce doing ×0.45 vs siege armor, ranged units needed 160+ shots.
  Two-round same-seed A/B: **round 1** (hp 280, damage unchanged) failed —
  fragile rams + slow breach (82 s solo vs a castle) meant failed sieges:
  timeouts 3/12, matches 671→1189 s, ram share UP to 27%. **round 2 — KEEP**
  (hp 300, armor 0, damage 55-75 → **85-115**): dies to ~8 warrior hits but
  breaches decisively; avg match back to 700 s, ram share 24→**20%**, mix
  healthy (28/23/17/11/20 warrior/archer/spear/cav/ram). Data:
  `tools/balance_12_ram_nerf.json` / `balance_12_ram_glass.json`.
- [x] **Position matters** *(med)* — forest-cover prototyped 2026-07-10 behind
  `COMBAT_TERRAIN_COVER_ENABLED`: units standing in forest take ×0.85 damage
  (buildings never get cover); terrain read via a module-level provider so
  the shared damage math stays entity-agnostic. **Enabled by default
  2026-07-13** after a 12-match same-seed A/B
  (`tools/balance_12_cover_{off,on}.json`): win rates identical, 0 timeouts,
  matches slightly shorter (641 vs 686 s), and ram share dropped 32%→20%
  (infantry gains). Env-overridable via `RTS_TERRAIN_COVER=0` for sims.
  High-ground needs elevation data the map doesn't have; flanking needs
  facing — both stay open.
  - **⚠ Baseline watch-item (2026-07-13, orthogonal to cover — present in
    both A/B arms):** the lean-start economy change (starting resources
    10000 → 200/100/75/200, snapshot commit `96edf32`) regressed
    personality balance vs the old authoritative §8.8 dataset: **rusher
    0/6 wins, boomer 6/7, and cavalry is never trained** (stable rarely
    built). The old `balance_20_reactive_soft.json` baseline is stale.
    Fix rides with the §8.3 resource-identity pass.
    **→ RESOLVED same day** through five same-seed 12-match iterations
    (`balance_12_{cover_off,cover_on,identity,raids,final,final2}.json`):
    cost re-map + cavalry in compositions + §7.3 raid targeting + rusher
    early-raid trigger (4) + 5th rusher worker + cavalry re-priced
    food-heavy (120g/80f → 80g/100f — it lost every gold race to the
    100g warrior). Final spread: **rusher 33 / boomer 43 / balanced 57 /
    turtle 75 %** (was 0/86/29/75), 0 timeouts, every unit & building
    used. Remaining watch-items: cavalry trains but stays marginal
    (2/318 units), spearman-heavy mix (39 %).
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
- [x] ⚡ **Unit response barks** *(low–med)* — code landed 2026-07-13:
  selection/move/attack acknowledgements are per-unit-type. Real voice files
  are drop-in content — `assets/sfx/bark_<unit>_<select|move|attack>_<n>.ogg`
  (numbered variants rotate); until files exist, each unit type gets a
  deterministic pitch-variant of the synth blip so types are audibly
  distinct now. Tests in `tests/test_audio.py`.
- [x] **Combat & impact SFX** *(low–med)* — code landed 2026-07-13: every
  synth SFX is now overridable by a real file (`assets/sfx/<key>.ogg|.wav`,
  synth kept as fallback — the AUDIO_GUIDE §2 contract). hit/death/attack
  triggers were already wired; sourcing the actual sounds is content work
  per AUDIO_GUIDE.
- [x] **Music & ambient** *(low–med)* — completed 2026-07-13: **mood-aware
  music** — `peace_*`/`combat_*` pools (AUDIO_GUIDE `assets/music/` layout,
  legacy `game_*` folder still works); combat mood follows human-involved
  damage events with a 10 s linger; **victory/defeat stingers** play on game
  over when the files exist; **ambient bed** (`ambient.ogg`) loops on its own
  channel; **alerts duck the music** (×0.35, 2.5 s, smooth recovery).
  All content files are drop-in optional — missing pools fall back cleanly.
  Tests in `tests/test_audio.py`.
  - *(2026-07-11)* **Background music landed** (user-supplied tracks): 3
    soundtracks converted mp3→ogg (`assets/sounds/Background Music/`),
    looping playlist via `pygame.mixer.music` with 1.5 s fade-in and
    auto-advance (runs even while paused); **separate Music/SFX volume**
    settings (mixer bumped to 44.1 kHz, synth SFX resampled to match);
    settings screen now opens **in-game from pause (O)** and re-applies
    audio live. Same day: **menu vibe pass** — the splash art is the main
    menu background (cover-cropped, scrim column for readability, title
    drop shadow), a splash + caption shows while a match generates, and
    the playlist now starts **on the menu** via a shared `music_player`
    singleton. Track roles are a **file convention** (user request):
    `menu.ogg` loops forever on the menu (Legacy of the Gilded Peak),
    `game_0.ogg, game_1.ogg, ...` form the numerically-sorted in-match
    playlist — drop new files in, no code change. Still open: ambient
    bed, ducking under alerts.
- [x] **VFX / juice** *(med)* — landed 2026-07-13 on the existing particle
  system (which now uses its own RNG so bursts never perturb the seeded
  sim stream): **death fades** (units/buildings ghost out in place, capped
  list, sims can't grow it), **movement dust** (fast movers, draw-time hook
  so headless sims pay nothing), **muzzle + impact flashes** (archer/tower
  shots), **staged construction** (the finished building **fades in** over
  the site, alpha 0→255 with progress — reworked 2026-07-14 per user
  request from the original bottom-slice reveal; alpha copies cached in 32
  quantized steps), **build dust** while a worker hammers, **ram-hit camera
  rattle** (castle/military-building destruction shake already existed).
  Tests in `tests/test_vfx.py`.
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
  restarts (`tests/test_keybindings.py`). Production/build **grid hotkeys**
  landed 2026-07-11 with the §8.2.1 command card (`card_slot_0..7` +
  `card_tab_swap`; the WASD collision is resolved per-key — pan is muted only
  while a card tile occupies that key). Still open: an in-game remap screen
  (belongs to the §8.2 settings menu).
- **✅ Verify:** edge-scroll and each jump hotkey move the camera as intended; a rebound
  key works and the binding survives a restart.

### 8.7 Meta, onboarding & accessibility

- [x] ⚡ **Post-match summary** *(low–med)* — game-over overlay now shows match
  length (game time) and a per-player table: units trained, buildings built,
  army remaining, watchtower damage. (2026-07-10; resources-gathered / units-lost
  / APM columns can extend the same stats hooks later.)
- [x] **Profile & achievements** *(med)* — 2026-07-10: `core/profile.py`
  accumulates lifetime stats (matches played/won/lost, units trained,
  buildings built, resources gathered) in git-ignored `profile.json`, folded
  in once per finished human match from both game-over paths (idempotent).
  Six achievements (First Victory, Veteran ×10 matches, Economist 10k
  resources, Warlord 100 units, Master Builder 50 buildings, Blitz sub-10-min
  win) unlock once and toast via the alert feed. Tests in
  `tests/test_profile.py`. (No profile *screen* yet — stats are in the JSON;
  surface them in the menu when the §8.2 menu polish pass happens.)
- [x] **Onboarding** *(med)* — 2026-07-10: universal tooltips (§8.2) cover the
  "what is this" half; the flow half is timed **first-match tips** — six
  contextual hints (gathering, build menu, idle workers/control groups,
  rally, event log/bookmarks, stances/speed) toast during the opening
  minutes of a human match, only while the profile shows fewer than 3
  matches played. Tests in `tests/test_onboarding.py`. (A guided practice
  *scenario* remains future content work.)
- [x] **Accessibility** *(med)* — 2026-07-10: **colorblind team palette**
  (Okabe-Ito, no red/green confusion pairs) toggle in the settings menu,
  swapped in-place over `PLAYER_COLORS` at startup so every consumer —
  sprites, minimap, panels — picks it up; **remappable keys** via §8.6's
  `keybindings.json`; **UI scale** rides the §8.2 resolution setting
  (full DPI-independent scaling stays with the §8.2 rework item).
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
  - *(2026-07-13)* **New authoritative dataset under the lean-start
    economy: `tools/balance_12_final2.json`** (same-seed 12-match run on
    the §8.3 identity re-map + §7.3 raid targeting + terrain cover ON):
    0 timeouts, avg 594 sim s, wins rusher 33 / boomer 43 / balanced 57 /
    turtle 75 %, all units/buildings used. Pre-lean-start datasets
    (`balance_20_*`) are historical reference only.
  - *(2026-07-14)* **Authoritative dataset under FAIR PERCEPTION:
    `tools/balance_12_fair.json`** — since §8.11 fair spectating, sims run
    with AIs under fog (scouting required), so all omniscient datasets
    above are historical. 12 matches (4×3 parallel slices via
    `tools/merge_balance_runs.py`): avg 761 sim s (~35 % longer — finding
    the enemy takes time), **2/12 timeouts** (watch-item: fair-perception
    stalls when neither side finds a kill), wins rusher 17 / balanced 43 /
    turtle 50 / boomer 57 %, cavalry usage up (9). Long matches are best
    simmed in parallel slices with disjoint `--seed-base`.
    **→ Timeout watch-item RESOLVED same day:** both stalls were scout
    blind spots — the scout brain's own explored model stamped 6 tiles vs
    the fog's ~2.7, so a castle could sit on scout-"explored" ground the
    fog never saw, and the anchor search stopped instead of sweeping on.
    Scout targeting now reads the FOG grid directly and sweeps to the
    farthest unexplored ground after the anchors. Verified on the exact
    stalled seeds: 1000 → turtle in 1060 s, 1001 → boomer in 501 s
    (both previously hit the 3600 s cap).

### 8.9 Bigger swings (later; likely past "polish" scope)

Hero units + abilities/spells · garrison & transport · day-night / weather · neutral
map objectives. Listed for completeness; revisit only after Tracks A–C land.

**Depth round 3 (2026-07-14, user-selected from the depth recommendations):**

- [x] **Healing fountain** *(med)* — landed 2026-07-14: neutral fountain
  placed at the map center (spiral search: open walkable ground, ≥12 tiles
  from every spawn, open-approach validated), heals any nearby unit
  5 hp/s within 140 px. Blocks movement/placement; indexed as a "resource"
  in the collision layer so no combat query ever targets it. Fog-gated in
  the AI blackboard (`ctx.fountains` — must be scouted). Procedural
  stone-basin visual with drop-in art convention
  (`assets/sprites/Buildings/Fountain.png` — prompt given to the user);
  blue healing motes already spawn; richer glow/heal-ring VFX planned when
  the art lands. Saved/loaded.
- [x] **Garrison** *(med)* — landed 2026-07-14: castle (cap 10) /
  watchtower (cap 4) shelter own units — garrisoned units leave the world
  (safe, untargetable), ejected unharmed on exit or building destruction;
  each garrisoned unit speeds tower fire +15 %. Right-click own
  castle/tower garrisons (replacing the vestigial farm-garrison path,
  which called a method that never existed); command card gets an
  "Ungarrison (N)" tile; **worker-flee now shelters INSIDE** when there's
  room, and the AI pops workers back out when the threat clears.
  Population/elimination/save-load all count garrisoned units.
- [x] **Squad retreat & regroup** *(med)* — landed 2026-07-14: when local
  enemy strength exceeds 1.8× the engaged army's (towers weigh half), the
  whole squad disengages (retaliation suppressed while fleeing), re-masses
  at home — or a scouted, quiet fountain, where it also HEALS — and attack
  goals stay silent for 20 s of regrouping. Emergency castle defense
  outranks retreat.
  - **Validation (`tools/balance_12_depth3.json`, 4×3 slices):** win spread
    UNCHANGED vs the pre-feature baseline (rusher 17 / balanced 29 /
    turtle 50 / boomer 71 %), 2/12 timeouts, avg 849 sim s (+10 % — armies
    that retreat live to fight again; warrior count +27 %). 347 tests
    green incl. 9 new in `tests/test_depth3.py`.
- [x] **Market building** *(low–med)* — landed 2026-07-14 with
  user-generated art. Two-way trades through gold: sell 100 wood/food/stone
  → 50 g, buy 100 ← 150 g (the spread makes it a release valve, never a
  money machine; barter = two hops paying the spread twice). Six
  command-card tiles (Shift = 5 lots), AI `BuildMarketGoal` (lopsided
  stockpiles) + `MarketTradeGoal` (sell rotting surplus when gold-short,
  buy shortages when banked; 10 s cooldown — an always-valid trade goal
  won the tick EVERY tick and starved AttackGoal: armies never left home
  and matches timed out). **Two regressions found by the smoke/battery:**
  (1) `find_idle_worker`'s pull-a-gatherer fallback had been unreachable
  since §8.11 auto-continuation (workers never idle) — construction
  starved for minutes, pop-locking armies; gather-cycle workers carrying
  nothing may now be pulled to build. (2) User-reported: a crowded
  barracks spawned units INSIDE itself (single-ring spawn search fell
  back to the building center) — spawn search now widens over 4 rings,
  tolerates unit overlap (separation resolves it), and never returns the
  center. Battery `tools/balance_12_market.json`: **0/12 timeouts**,
  spread unchanged (17/43/71/75), armies much larger (market economies
  fund longer wars, avg 1071 sim s). Floating AoE2-style prices remain
  future work. Quarry art regenerated by the user (stricter magenta
  keying — the first market pass left ~30 k tinted pixels, now cleaned).
- [ ] **Temple + healer activation** *(low, BLOCKED ON ART)* — healer logic
  is done and tested; flipping `temple` to buildable + an AI
  support-composition rule adds the sustain dimension to fights. Needs the
  temple sprite (healer currently reuses archer sheets — its own sheet
  wanted too).
**AI tune-up batch 3 (2026-07-14, user spectating reports — all landed
same day):**

- [x] **Slow factions** *(investigated)* — root cause was the
  builder-starvation regression fixed earlier the same day (workers never
  idled → construction stalled for minutes). Verified post-fix with an
  instrumented balanced-vs-turtle match: turtle fields 8 military + 7
  building types by t=150. Balanced remains the mildest personality
  (chronic ~29-43 %) — its identity pass stays a §7.2 watch-item.
- [x] **Watchtowers with map awareness** *(med)* — tower #1 rings the
  castle on the threat bearing (unchanged); **tower #2 now guards the
  forward economy** — the placer anchors it at the forward dropoff
  (mine/lumbermill/quarry/market ≥300 px out) farthest from existing
  towers — and needs no pressure; the pressure gate applies from #3 on.
  Caps +1 (turtle 4 / balanced+boomer 3 / rusher 2). Battery: towers
  built doubled (~2 per player-match); turtle's towers dealt 21.7k
  damage across the set.
- [x] **Ram-spam loop** *(low)* — rams are the only gold-free unit, so a
  wood-flush gold-broke AI trained one every quiet tick (user saw ~30;
  the old past-cap "filler 15" was the leak). Cap is now proportional —
  25 % of the army, min 3, **zero past the cap** — big ram trains require
  an army to escort them. Battery: rams settle at ~15 % of production.
- [x] **Rams march unescorted** *(low–med)* — squads sliced the army list
  in production order, so consecutively-trained rams formed pure-ram
  squads that walked to their deaths alone. The army is now interleaved
  by unit type before squad chunking: every squad mixes fighters with
  siege.
- [x] **Buildings half off the map** *(low)* — placement bounds used a
  flat 50 px margin regardless of building size; bounds are now
  radius-aware (building must fit entirely in the world) for the AI
  placer and the human placement ghost alike.
  - **Battery (`tools/balance_12_tuneup3.json`):** 2/12 timeouts, avg
    1125 sim s, cavalry at its series-high (21), markets in use (8).
    ⚠ rusher 0/6 this round (yo-yos 0–2 wins per battery; more towers =
    stronger defense again) — the §8.12 multi-prong/timing work remains
    the aggression side's structural fix.

- [ ] **Unit active abilities** *(med–high, LATER)* — one ability per core
  unit (cavalry charge, spearman brace, archer volley); micro depth, and a
  natural difficulty-tier lever ("hard AI uses abilities well").
- [ ] **Challenge presets** *(low, LATER)* — named mutator/victory/difficulty
  combos with an achievement each; pure configuration over shipped systems.

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

> **⏸ Walls & gates DISABLED / deferred (2026-07-12).** The wall mechanics below
> all landed and work (drag-line placement + live cost readout, Esc/right-click
> cancel, AI walling, gate toggle, nav sealing), but `wall` / `wooden_wall` /
> `gate` are now **`buildable: false`** in `data/buildings.json` — hidden from
> the human build menu ([command_card.py:160](ui/components/command_card.py:160))
> and skipped by the AI's `start_construction`
> ([actions.py:39](systems/ai/utility/actions.py:39)); `BuildWallGoal.score` also
> bails on non-buildable pieces so a turtle doesn't churn. **Why:** a single
> straight segment sprite can't read correctly for lines built in ~6 directions
> on the hex map — walls need **orientation-aware art** (straight / corner / end /
> T pieces) plus auto-connection logic before they're worth shipping. The
> `Watchtower.png` placeholder sprite is still what they'd draw as. **Re-enable:**
> flip the three `buildable` flags back to `true` and supply the oriented
> sprites. Watchtowers (above) stay live and unaffected.

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

### 8.11 Playtest feedback batch — AI-vs-AI observation (2026-07-14)

User-reported from spectating AI matches, plus a version milestone. Version
bumped **0.9.0-beta → 0.10.0-beta** (no installer build).

- [x] **Towers out-range archers** *(low)* — archer range 200 (225 fletched)
  vs watchtower 175 meant a single archer could demolish a tower for free.
  Watchtower `attack_range` 175 → **230**: ahead of even fletched archers
  (both gain +25 from fletching, so the gap holds post-upgrade).
- [x] **Workers still get stuck a lot** *(med)* — root-caused 2026-07-14 to
  a structural blind spot: workers wedged in the stationary task phases
  (DROPPING_OFF/BUILDING) were invisible to BOTH recovery systems — the AI
  idle-scan skips non-FAILED tasks and the watchdog skips
  `is_dropping_off`/`is_building` — and those phases had **no timeout**.
  Fixed: stall timeouts (drop-off 6 s, build 8 s on frozen progress) fail
  the task into the normal recovery path; slot-exhaustion failures are now
  remembered so the AI stops re-picking the same crowded node
  (FAILED→reassign→FAILED thrash — the most common visible "stuck"); and
  recent-failure retries back off instead of churning every frame.
- [x] **Units frozen in attack animation with no enemies around** *(med)* —
  root-caused 2026-07-14: on a focus-fire kill, `handle_unit_death` cleared
  every other attacker's target but left `status="attack"` — which not only
  froze the animation, it PERMANENTLY disabled target re-acquisition (the
  auto-engage gate requires `status=="idle"`). Fixed there + in building
  destruction; corpses/despawned objects are no longer valid attack targets
  (`is_valid_attack_target` checks hp/in_world); idle healers drop their
  cast pose. Victims also record `last_attacker` now, which makes the
  dormant kill-XP path live.
- [x] **Emergency castle defense** *(med)* — 2026-07-14: combat stamps
  `_last_damage_frame` on victims; `ctx.castle_under_attack` (hit within
  ~3 s) escalates `DefendBaseGoal` to score 500+ and flips military_brain
  into **full recall**: units marching or fighting far from home abort and
  come defend (fights within 600 px of the castle are kept — they're
  already defending), and damaged units skip the retreat rule — the castle
  is worth more than any soldier.
- [x] **Attack-move retaliation** *(med)* — 2026-07-14: auto-engage only
  ever ran for `status=="idle"` units, so marching armies soaked free
  damage all the way to their destination. Now a unit hit while moving
  (aggressive/defensive stance, non-ram vs units) turns on its attacker
  when it's within chase range. Squadmates spread the fight naturally via
  the existing idle auto-engage once they stop.
- [x] **Worker auto-continue on depletion** *(low–med)* — 2026-07-14: all
  three depletion paths (mid-gather, node-vanished, returned-from-dropoff)
  retarget to the nearest live same-type node within 400 px (preferring
  un-crowded nodes), for human and AI workers alike; idle only when
  nothing is in range.
- [x] **Construction fade-in** *(low, user request)* — buildings now
  materialize (alpha 0→255 with progress) instead of the bottom-slice
  curtain reveal; verified by rendered frame (§8.5 entry updated).
- [x] **Fair spectating + build-on-revealed-ground** *(med, user report:
  "AI putting buildings across the map")* — 2026-07-14. Root cause was
  twofold: spectator mode ran fog-off making AIs **omniscient by design**
  (old §7.2 note), and building placement **never checked exploration** for
  anyone. Now: (1) fog rules always apply to AI players — spectator mode
  reveals only the viewer's *display* (`spectator_reveal_display`; the
  `revealed_map` mutator stays true omniscience as a rule); (2) AI and
  human placement both require **explored ground** (`building_placer` +
  `is_valid_building_position`); worker continuation is fog-gated too;
  (3) fair perception made sims time out — the scout random-walked and
  armies idled with no known target — fixed by **directed scouting**
  (probe far spawn-anchor corners/edges first — fair map knowledge since
  spawn placement maximizes spread) and **armed scouting** (a standing
  army with no known enemy sends one squad probing anchors).
  Tests in `tests/test_fair_spectating.py`; perf gate unaffected
  (fog updates cost ~0.15 ms/frame in the benchmark).
- **✅ Verify:** `tests/test_playtest_batch.py` (10 tests) +
  `tests/test_worker_task_system.py` continuation tests cover every item;
  12-match validation sim (`tools/balance_12_playtest.json`): 0 timeouts,
  all units/buildings used, towers now deal real damage (turtle 2.3k /
  balanced 3.8k across the set — the range fix bites). The sim also caught
  a rams-only crash no unit test reached (missing import in the
  retaliation branch) — regression-tested now. **⚠ Watch-item:** the batch
  shifted the win spread defender-ward (rusher 33→17 %, boomer 43→71 %) —
  expected, since emergency defense + retaliation + stronger towers all
  favor defenders; re-tune the aggression side with the §8.12 round.
  The remaining human check is spectating an AI match — towers repel lone
  archers; no frozen attack animations; a raided march turns and fights;
  castle attacks trigger a visible all-in defense; depleted-node workers
  walk to the next tree.

### 8.12 AI depth — next round *(2026-07-14)*

User-reported from further AI-vs-AI spectating (second batch):

- [x] **Mutual battlefield awareness** *(med)* — landed 2026-07-14. Root
  cause ran deeper than reported: target acquisition searched only
  **weapon range**, so melee units were blind beyond 48 px even when
  IDLE. New `AGGRO_RANGE = 200` notice radius (stances still gate the
  response), plus AI units **on the move** engage enemy units that come
  within it (attack-move semantics for AI marches; human orders stay
  literal). Exposed and fixed a latent crash: idle workers/healers could
  now *acquire* targets and divide by `attack_speed = 0` — acquisition is
  gated on `can_attack_flag` + a stand-down guard in `update_combat`.
- [x] **No tunnel vision on buildings** *(med)* — landed 2026-07-14: a
  unit hammering a *building* that takes hits from a live enemy *unit*
  switches to the guard (rams keep ramming — escorts handle guards).
- [x] **Losing the castle ≠ lobotomy** *(med–high)* — landed 2026-07-14:
  **castle buildable** (500g/200w/300s — in the human Economy tab and via
  the AI's top-priority `RebuildCastleGoal`, placement anchored at the
  surviving base/worker cluster); **last stand** — a castle-less military
  guards its rebuild site if one exists, otherwise attacks with
  everything; **elimination re-ruled** — out means no castle AND no
  castle site AND no workers (a surviving worker is a real comeback
  path). Bonus items from the proposals below also landed: **rams react
  to fortifications** (tower/castle/wall-heavy enemies pull siege
  production) and **AI workers flee attackers** to their base (raids get
  counterplay; human workers stay under player control).
  - **Validation (2026-07-14, `tools/balance_12_depth2.json`, 4×3
    parallel slices):** 1/12 timeouts (was 2/12), avg 650 sim s (761
    before — wider aggro means armies actually meet), 338 tests green
    incl. 10 new. **⚠ Balance watch-item sharpened:** the batch swings
    further defender-ward — rusher 0/6, boomer 86 %, cavalry flickers to
    0 again (awareness intercepts raiders, worker-flee blunts raids).
    The §8.11 aggression re-tune is now the top balance priority.
- [x] **Aggression re-tune pass** *(2026-07-14, user request: "rusher
  shouldn't be at 0%")* — three sim cycles + five INSTRUMENTED matches
  (`scratchpad diagnose_rusher.py` pattern: 30 s state samples — worker
  allocation, per-node distances, stockpiles). The instrumentation found
  five structural defects that aggregate win rates hid:
  1. **Gold was a fake economy** — one near-castle node, saturation cap
     3, carry 10 → ~0.5 g/s per worker FOR EVERYONE; gold armies were
     tiny regardless of macro and the wood-priced ram was the de-facto
     army. Gold carry 10 → **20**.
  2. **Spearman meta = affordability artifact** — composition targets
     can't assert themselves when the flagship unit is the unaffordable
     one. Warrior 100g → **80g** (warrior share up 47 % in the battery).
  3. **Food-crisis starvation** — low-economy-weight personalities
     under-built farms (weighted flat-40 goal) and banked gold they
     couldn't spend. Farm goal escalates to 70 under 50 food.
  4. **Spawn luck ≈ 2× income** — starting-deposit band was 3-5 tiles,
     an `int()` truncation widened it further (147 px vs 280 px rich
     nodes), and a node could be placed with NO walkable approach (one
     match: 2500 gold untouched all game). Band 3-4 + honest rounding +
     open-approach validation, wide-band fallback.
  5. **Worker count was the only macro** — near-parity targets
     (rusher/boomer 8, balanced/turtle 7); boomer's identity moved to its
     late attack commitment (threshold **9**), which IS the rusher's
     timing window; rusher's suicide-trigger 4 removed (§8.11 defense
     math makes 4-unit pushes guaranteed wipes); ram fortification boost
     tamed (+8×4 → +5×3; ram share 35 % → 8 %).
  **Result (`tools/balance_12_retune3.json`):** rusher 0 → **17 %**,
  boomer 86 → **71 %**, turtle 50 %, warriors 112 (+47 %), rams 31
  (was 135), 2/12 timeouts. **Caveat:** the fixed seed schedule pits
  rusher against boomer in 4 of its 6 matches, so per-personality rates
  carry matchup bias — the true spread is tighter. Remaining boomer edge
  is a job for the deeper §8.12 items (squad retreat & regroup,
  multi-prong attacks), not more parameter knobs.

Candidates for "more depth", ordered by feel-per-effort. Top three are the
recommended next batch:

- [ ] **Reactive counters vs fortifications** *(low–med)* — reactive
  production only reads the enemy's *units*; a tower/castle-heavy turtle
  should visibly pull ram/siege production. Cheap: include defensive
  buildings in the counter signal.
- [ ] **Squad retreat & regroup** *(med)* — army-level "we're losing this
  fight" detection (squad hp dropping fast vs damage dealt) → disengage,
  re-mass at a rally point, re-engage. Currently only individuals retreat
  at 30 % hp; armies bleed out piecemeal.
- [ ] **Worker flee behavior** *(low–med)* — workers under attack keep
  gathering like nothing happened; they should run to the castle/towers
  and resume after. Pairs with raid targeting (raids get counterplay).
- [ ] **Timing pushes on power spikes** *(low)* — AI attacks sync to its
  own tech completion (attack-commitment bonus for ~30 s after a combat
  tech lands) — personalities get sharper timing identities.
- [ ] **Coordinated multi-prong attacks** *(med–high)* — main army push +
  simultaneous cavalry raid on the economy from another bearing (squad
  layer exists; needs a second simultaneous command channel).
- [ ] **Map control / expansion denial** *(med)* — small guard posted at
  contested rich gold/stone nodes; deny scouted enemy expansions before
  they're defended.
- [ ] **Tower-aware army pathing** *(med)* — armies route around known
  tower coverage using the existing threat map instead of walking through
  it (flow-field + threat infrastructure already in place).

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
- [x] **Five user-reported bugs, batch 2026-07-11**: (1) the command-card
  hover tooltip drew as a detached box pinned to the screen bottom, half
  overlapping the sidebar ("two boxes") — now a flyout anchored beside the
  hovered tile; (2) tab chips verified clickable at every resolution (the
  live miss was the fullscreen surface-size mismatch, fixed same day);
  (3) enemy health bars leaked through unexplored fog — floating bars draw
  above the fog overlay, so they now fog-check themselves; (4) **siege
  reach**: units ordered to attack sometimes stopped trying — the watchdog
  wiped attack orders on recovery (now resumed like moves, 3-resume cap)
  and attack contact points prefer arcs not already held by in-combat
  friendlies (latecomers route around the ring). Repro: 24 warriors vs a
  cluttered castle went from units orbiting/giving up to razing it;
  regression tests in `tests/test_siege_reach.py`; (5) the attack-range
  ring on selected units removed.
- [x] **Spearman/cavalry drawn tiny** (user-reported 2026-07-11): three
  compounding causes — the AI-generated sheets are thin-realistic style
  next to the chunky cartoon originals; stale multiplicative type-tints
  (from the shared-sheet era) washed their colors out; and the spearman's
  attack frames were authored 40% smaller than its idle (the unit shrank
  in combat). Fixed: per-unit `render_scale` in units.json (spearman
  1.22, cavalry 1.12) applied in the renderer only — collision/gameplay
  size untouched; tints dropped for the dedicated sheets (healer keeps
  its — still shares the archer sheet); spearman run/attack/guard frames
  normalized in-place to the idle character height, feet anchored.
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
- [x] **HP bars read as empty at max zoom** (user-reported 2026-07-10, closed
  same day after a screenshot): unit HP bars verified green through the real
  frame pipeline at zoom 2.5 (pixel-sampled). The black bar in the screenshot
  was a **fresh construction site's progress bar at 0 % fill** — an all-dark
  bar that reads as "0 HP". Fixed: construction bars floor at a 4 % blue
  sliver, and all floating bars now draw **above the fog overlay** so a
  fog-tile edge can never dim them. (The same screenshot's foundation was the
  §9 orphaned-site bug, also fixed below.)
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
