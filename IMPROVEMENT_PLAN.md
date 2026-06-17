# RTS Game Improvement Plan

## Status (2026-04-30)

Phases 1–5 of the original plan landed on `feature/improvement-plan` with 70 tests passing. Most pieces work, but a deeper review revealed several features that were incomplete, dead, or only superficially tested. The dead/broken parts have been cleaned up; the AI in particular needs a rewrite to actually deliver on the "adaptive" promise.

This document was rewritten on 2026-04-30 to reflect what's actually in the codebase (not what the original plan claimed was done).

---

## What works

Verified by running the game and a smoke harness:

- **Core gameplay**: selection, movement, combat, gathering, building, production
- **Victory/defeat overlay** (R restart, ESC/Q quit)
- **Control groups** (Ctrl+1–9 set, 1–9 recall, Shift+Ctrl add)
- **Unit stances** (Aggressive / Defensive / Stand Ground / No Attack, S to cycle)
- **Formation movement** (Ring / Line / Box / Wedge, F to cycle)
- **Save/Load** (F5/F9) — but only saves a thin slice of state, see "Deferred" below
- **Pause menu** (ESC), **main menu**, **screen shake** on castle destruction
- **Floating damage numbers**, **particle effects** (attack/death/build/gather)
- **Fog of war** (3-state per-player grid + overlay rendering)
- **Tree regrowth** (60s after depletion)
- **Content**: 6 unit types (worker/warrior/archer/spearman/cavalry/healer), 12 buildings, 4 AI personalities (rusher/boomer/turtle/balanced)

---

## Bugs found in review and fixed

These were marked complete in the original plan but were broken or dead. Fixed on 2026-04-30:

| Issue | Resolution |
|---|---|
| `scout_brain` crashed every AI tick (`random` not imported). The exception was swallowed by a broad `except` in `simple_ai.update`, blocking `worker_brain.assign_idle_workers`. AI workers sat idle forever. | Added `import random` |
| Tech tree (`data/techs.json`, `Player.tech_*` attributes, bonus reads in `Unit.calculate_damage` / `gathering_manager`) — no UI to research, no AI logic, never reachable | Stripped (will revisit when needed) |
| JSON re-reads on hot paths — `floating_ui._get_max_hp`, `production_panel.draw`, `military_brain._get_unit_max_hp`, `unit_panel._get_unit_max_hp` opened `data/units.json` / `data/buildings.json` per call (hundreds of disk reads/sec) | Cached on `game.game_data["costs"]` and existing template objects |
| Borrowed sprites — spearman/cavalry/healer reused warrior/archer art with no visual difference | Per-unit-type secondary tint (spearman=green, cavalry=tan, healer=cyan) in `sprite_manager.UNIT_TYPE_TINTS` |
| `print()` calls leaked back into `production_panel.handle_click` | Removed |

---

## Still broken or shallow (not yet addressed)

### AI (next focus — see "Plan: AI rewrite")
- `_try_train` only handles worker/warrior/archer — spearman/cavalry/healer are filtered out at the orchestrator level even though `MilitaryBrain` knows about them
- AI never builds stable, temple, blacksmith, or wall in any phase
- "Adaptive build order" in `_tick_early` is a fixed priority list dressed as scoring, not actually reactive to context
- Broad `except` in `simple_ai.update` masks runtime bugs (the missing `random` import was hidden for a long time this way)
- Defensive-stance units freeze in the field after chasing past `stance_chase_distance` instead of returning to home position
- Pre-existing: workers occasionally get stuck at gold/wood nodes (pathfinding/collision edge case, predates this plan)

### Save/Load — deferred
Currently saves only camera, players, basic unit/building/resource/site fields. Misses: terrain (procedural — needs seed-based regeneration), AI state, fog grids, scout explored tiles, paths, gathering/building/combat targets, production queues, formation type, control groups, stance home positions, last attack times, tree regrowth tracker.

The load won't crash, but post-reload state diverges meaningfully from saved state. **Deferred until after the AI rewrite** — save/load semantics depend on what AI state actually is.

### Fog of war performance
`update()` walks the full grid every frame; `_draw_fog_overlay` allocates a fresh `pygame.Surface(SRCALPHA)` per visible tile per frame. Should tick at ~5Hz and reuse two preallocated alpha surfaces.

### Sound coverage
6 of 9 `play_*` methods (`attack`, `select`, `move_order`, `gather`, `build_complete`, `alert`) are defined but never called.

### Healer doesn't heal
Trainable, walks around, no healing logic anywhere.

### Wall is just a 1×1 building
No gate, no thin profile, no special placement logic.

### Test coverage
70 tests pass but they verify constants, attribute presence, and pure-function math. They did NOT catch the `random` import bug, the tech-tree wiring gap, or the unit-type filtering in `_try_train`. Need integration tests that actually run the AI for several ticks and assert observable outcomes.

---

## Completed: AI rewrite (Option B — utility AI)

The 4-phase state machine was replaced with a flat list of weighted goals scored each tick. The live orchestrator is `systems/ai/utility/ai.py`, and the old `simple_ai.py` module has been deleted.

### Why
The old "adaptive" AI was scripted in disguise. Utility AI now:
- Genuinely react to the game state (e.g., switch from economy to defense when attacked)
- Makes personalities meaningful (weights on goal categories instead of threshold tweaks)
- Makes adding new content trivial (new unit type → new training goal, no orchestrator changes)
- Surfaces bugs faster (narrow per-goal exception handling instead of a god-`try`)

### Current shape
- Each tick, evaluate a list of `Goal` candidates. Each returns `(score, action_callable)`.
- Goals are stateless; ongoing construction and production are read from game objects.
- Personality params become per-category weights (rusher: military × 2, boomer: economy × 2, etc.).
- Existing sub-brains (`worker_brain`, `military_brain`, `scout_brain`, `building_placer`) are reused as helpers — what changes is the orchestrator.

### Goal categories (initial set)
- **Economy**: train_worker, build_farm, build_house, build_lumbermill, build_mine, build_quarry
- **Military**: build_barracks, build_stable, train_warrior, train_archer, train_spearman, train_cavalry
- **Tactical**: scout, defend_base, attack_castle, retreat_damaged, focus_fire, kite_with_archers
- **Support** (later): build_temple, train_healer, heal_units (once healers heal)

### Design principles
- No broad `except`. Per-goal failure logs and skips, doesn't hide.
- All cost / HP lookups via `game.game_data` (no JSON re-reads).
- Personality config in one dict, weights only — no scattered thresholds.

### Out of scope for this rewrite
- Tech research (deferred — easier to wire as a goal once research itself exists)
- Healer healing (separate feature)
- Save/load round-trips (deferred — depends on stable AI state shape)

---

## Deferred (revisit later)

- Save/Load full state (post-AI-rewrite)
- Tech tree (post-AI-rewrite, wired as a research goal)
- Settings menu (volume, resolution, default game speed)
- Healer healing logic
- Wall as gate/wall-piece
- Map editor, scenarios
- Online multiplayer
- Fog-of-war perf pass
- Sound coverage on the 6 unused effects
