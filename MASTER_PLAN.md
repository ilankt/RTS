# RTS Master Plan — active work

> **Single source of truth for what's being worked on next.** Open items only.
> Completed work — and, more importantly, the *rationale and failed experiments*
> behind it — lives in **[PLAN_ARCHIVE.md](PLAN_ARCHIVE.md)**. Split 2026-07-17.
>
> **Four tracks:**
> **A (§5–6)** — sim performance at scale. *Substantially done; residue only.*
> **B (§7)** — single-player-vs-AI depth and fun. *Substantially done; residue only.*
> **C (§8)** — UI/UX and game-systems depth.
> **D (§11)** — world, art & atmosphere. *New 2026-07-17.*
>
> **How to use this plan.** Every action is a `- [ ]` checkbox; tick it as you
> land it. Each sub-phase ends with a **✅ Verify** gate — the concrete check that
> proves it works *and didn't regress*. **Do not start the next phase until its
> gate passes.** Track A gates are measured (`tools/benchmark_ai_spectator.py`,
> `cProfile`/`py-spy`, `pytest`); B/C/D gates are play-and-observe plus the
> balance sim (§8.8).
>
> **Section numbers are stable labels, not an ordering.** §11 (Track D) is new
> and sits last; §9/§10 kept their archive meanings so old references resolve.
>
> Do not maintain a second roadmap or changelog. Update this file; archive
> completed work into PLAN_ARCHIVE.md with its evidence; rely on `git log` for
> the rest.

---

## 0. Where the project stands (2026-07-17)

Core gameplay works end to end. Content is a 7-unit / 14-building / 6-tech roster
with a personality-driven utility AI, fog-gated fair perception, walls/gates,
garrison, market, healing fountain, temple+healer, save format v3, and a
research-backed command-card HUD.

**Track A**: Phases 0–5 landed and hold at 45 units (avg 2.4 ms / p95 11.5 /
max 23 / 0 teleports). The **200-unit acceptance gate is not met** — see §6.
**Track B/C**: nearly all shipped; residue is listed below.

**What's actively open**, in recommended order:

| Priority | Item | Why now |
|---|---|---|
| 1 | **§8.2.2 HUD readability & scale** | The HUD is unreadable at the default 1080p — §8.2's deferred DPI item came due |
| 2 | **§11 Track D — world, art & atmosphere** | The map is the least-finished-looking part of the game |
| 3 | §8.12 AI depth candidates | Depth, not defect |
| 4 | §6 / §5 Phase 6 Track A residue | Gated behind a fresh profile; only at 200 u |

*(The §8.13 bug batch — the old priority 1 — landed 2026-07-17; see §2 for the
residue: a live-play observation pass and the gated planner-erosion deferral,
plus §8.13.4. The early-game benchmark `frame_max` spike (~84 ms) was
root-caused the same day — the path queue's retry ladder restarting cross-map
scout searches — and fixed; queued searches now suspend + resume. See §6.)*

---

## 1. Hard-won lessons that still bind

Compressed from the archive. **These are the traps that cost real time already.**
Violating one is how a "small fix" becomes a two-day regression hunt.

- **Never scale AI difficulty by resource/stat cheats.** Decision quality,
  reaction speed, aggression, build sophistication — those only. Reserve
  economic handicap for an explicit, player-chosen slider. *[verified]*
- **Never throw the game.** A bot that visibly drops its play rated **least**
  enjoyable of all opponents tested — worse than a dumb static bot. *[verified]*
- **If you adapt difficulty, hide it.** Overt adjustment gets exploited. *[verified]*
- **No rubber-banding.** Known feel-bad. *[verified]*
- **Balance changes require same-seed validation before they're believed.**
  Aggregate win rates hide structural defects — the §8.12 re-tune found five
  real bugs only via *instrumented* matches (30 s state samples), not win rates.
  Run 12 matches as 12 parallel 1-match processes + merge.
- **A goal that is always valid wins every tick and starves everything else.**
  `MarketTradeGoal` did exactly this and armies never left home. Cooldown them.
- **Never do O(map) work on an O(1) change.** Nav updates are local/dirty-region.
- **Budget by measured wall-time and *queue* overflow — never freeze the frame,
  never silently drop a command.**
- **Scan the world once per tick, publish, everyone reads.** The blackboard
  contract is enforced by `tests/test_ai_contract.py` — goals and sub-brains read
  `GoalContext`, never `game.units`/`game.buildings`.
- **Game-time, not wall-clock.** Combat cadence used `pygame.time.get_ticks()`
  and was silently 5× slower at 5× speed, muting towers and distorting every
  balance sim. Check any new cadence against `delta_time`.
- **Draw-side work must be draw-side.** Particles, dust, death fades and ambient
  visuals hook the render path on visible objects only, so headless sims and the
  perf gate pay nothing. Keep it that way (§11 depends on this).
- **The map's seed does not reproduce the map.** Generation draws from the global
  RNG, so terrain is *stored* in saves (v3). Don't "just replay the seed".
- **Sprite sheets need the pipeline.** Team-color keying is a ±25 match on two
  exact shades; run `tools/normalize_team_color.py` + `reanchor_sprite_frames.py`
  on any generated sheet. Resources/props load **untinted** — no discipline needed.

---

## 2. §8.13 — Bug batch 2026-07-17 (round 2) — **landed except 8.13.4**

**8.13.1 (worker depletion continuation), 8.13.2 (floats through fog), and
8.13.3 (stuck at water — the Phase 3 reopen) all landed 2026-07-17** with
their test gaps closed first — full root causes, fixes, evidence, and the
two deliberate deferrals are in **PLAN_ARCHIVE.md §8.13**. Headline evidence:
the 20-unit lakeshore crowd test arrives 20/20 (`tests/test_shoreline_movement.py`),
the depletion test failed-then-passed exactly as predicted once real cleanup
ran in the loop, suite 385 green, benchmark teleports 0.

Still open here:

- [ ] **Live-play observation** — the B/C-style half of each gate (a real
  session: worker continuation without input, no fog floats, shoreline feel).
  Automated halves are green; play a match and watch for stragglers at shores.
- [ ] *(deferred, gated)* **Erode the planner graph near terrain** so JPS stops
  hugging shorelines — changes every path; do it only behind a fresh §6
  profile (the §8.13.3 steering/slide fixes may have moved the numbers).

### 8.13.4 *(separate, low priority)* Hex coordinate round-trip is broken

`grid_to_world` (`map.py:348-356`) returns the tile's **top-left corner**;
`world_to_grid` (`:375-419`) searches against an assumed center of
`corner + (TILE_WIDTH*0.375, TILE_HEIGHT/2)` = `corner + (24, 28)`. But
`0.375*64 = 24` is half the **stride** (48), not half the **tile** (64), while
`draw()` blits a 64×56 image at the corner (center = `corner + 32`). Measured:
**100/100 round-trips fail**, always landing on `(col-1, row-1)`.

Net effect: terrain at world point `p` is read from the tile drawn at
`(p.x + 8, p.y)` — an 8 px lattice shift, so units can stand ~8 px into *drawn*
water on right-hand shores.

- [ ] Fix the center offset **carefully**: the nav bitmap, terrain components, and
  collision all share the same shifted frame, so they are mutually consistent today.
  Correcting it re-baselines every seeded map and every terrain-dependent test.
  **Low priority, deliberately: it's cosmetic relative to §8.13.3 and the fix is
  more dangerous than the bug.** Do it as its own change with the navigation
  reference sweep green, never bundled.
- [ ] Fold in `find_safe_spawn_position`'s corner-return (`map.py:344` returns
  `grid_to_world(col,row)` — the tile's top-left corner, not its center). Checked
  during §8.13.3: **safe today** — its 3×3 safe-terrain area check covers the full
  radius for every caller (setup-time castle/worker placement only) — but it's the
  same corner-vs-center confusion as this item, and moving the returned point
  re-baselines seeded maps, so it must land here, not in a bug batch.

---

## 3. §8.2.2 — Command card: information architecture, readability & scale
*(reopens §8.2's deferred DPI item; supersedes the §8.2.1 tile anatomy)*

User: *"The text is too small on unit purchase, etc. **We might just need tooltip
when the cursor is above the icon.** Also the tooltip window is blocked and not
shown completely. Mostly I want to see the cost (with icons, not text or
abbreviation) and duration (also an icon)."*

### The decision: icon-first tiles, tooltip carries the detail

**This is an information-architecture change, not a styling pass** — and it is the
headline of this section. Today's tile crams icon + wrapped name + cost into 86×74
with ~13 px of vertical slack and an 11 px line step against an 11 px font (zero
leading). The fix is not to win that fight; it's to stop having it.

**New tile anatomy (decided 2026-07-17):**

| On the tile | In the hover tooltip |
|---|---|
| Large icon (gets the ~22 px the name currently eats) | Display name |
| **Cost as icon+number pairs** | Role / description |
| Hotkey badge | **Cost (icons) + duration (clock icon)** |
| State: dimmed / red-tint / tan-locked | Strong vs / Weak vs |
| Queue badge | Availability reason ("Requires X") |

**Why cost stays on the tile rather than moving into the tooltip** (the one place
this diverges from the user's literal "just need tooltip"): §8.2.1's own research
found cost-on-tile is **universal across every sourced RTS**, precisely so you can
scan affordability across the whole grid at once. Moving it into the tooltip would
force hovering each tile in turn to answer "what can I afford right now?" — which
is the opposite of what "mostly I want to see the cost" asks for. Name and
duration have no such at-a-glance requirement, so they move.

**Consequence — the tooltip becomes load-bearing.** Every item below marked ⛔ is
now **blocking**, not polish: if the tile no longer carries the name, a tooltip
that is painted over or chopped mid-word is a functional regression, not a
cosmetic one. Fix the tooltip *before* stripping the tile.

### The scale problem (independent, and also real)

**Root cause of "too small" is not styling — it's that the HUD never scales.**
`config.apply_resolution()` (`config.py:258-267`) recomputes `MAP_VIEW_*` but
**`MINIMAP_WIDTH` stays hardcoded at 200** (`config.py:39`), and the default
resolution is **1920×1080 fullscreen** (`settings.py:21`). So the sidebar is 10 %
of screen width running 14–16 px fonts (≈9–11 px rendered cap height). §8.2
Phase D explicitly deferred "DPI scaling of fonts/tiles" — this is that bill.

**There is no font infrastructure**: no shared module, no constants, no scale
factor — **44 separate `pygame.font.Font(None, N)` call sites** with hardcoded
literals. A font-size change today means touching every file.

**The tile grid has no slack**: grid width = 2×86+4 = **176 into a 180 px inner
column**; grid bottom 458 + strip = 478 into 488. Tiles cannot grow inside the
current sidebar. **Decision (user, 2026-07-17): scale the HUD with resolution.**

The two decisions compose: **scaling gives the tile room; the icon-first anatomy
decides what to spend it on** (a bigger, more legible icon — not more small text).

### Actions

*Order matters: tooltip correctness → font/scale infrastructure → anatomy → icons.*

- [x] ⛔ **Tooltip occlusion** — *landed 2026-07-17.* `draw_tooltip` moved out of
  `draw_ui_panel` into `draw_frame` truly last (after `_draw_map_border`, alerts,
  event log, debug panel). Guarded by an end-to-end pixel test that drives a real
  frame with a hovered tile plus a source-order assertion
  (`test_command_card.py::test_tooltip_draws_over_map_border` /
  `::test_draw_ui_panel_no_longer_owns_the_tooltip`) — the regression shipped
  precisely because no test could see it.
- [x] ⛔ **Tooltip truncation** — *landed 2026-07-17.* `line[:34]` and the `[:5]`
  line cap replaced with measured word-wrap (`_wrap_tooltip_line`, lossless — a
  wrap test asserts no characters are dropped and every piece fits) and a
  content-sized box (`TOOLTIP_*` constants). Long entries (gate, fletching,
  stable…) now wrap instead of chopping mid-word.
- [ ] ⛔ **Tooltip content + behavior** — it now owns name / role / cost+duration /
  counters / availability reason (see the anatomy table). Decide and record: hover
  delay (instant vs ~200 ms), anchor side when the tile is near a screen edge, and
  ordering. It already anchors beside the hovered tile (the §9 2026-07-11 fix); keep
  that, don't regress to a screen-pinned box.
- [ ] **Strip the name off the tile; grow the icon.** `_draw_tile`
  (`command_card.py:567-631`) drops the wrapped-name block (`:617-621`) and reflows:
  `TILE_ICON` (`:49`, currently 28) takes the freed ~22 px. Keep hotkey badge, cost
  row, state colors, queue badge.
- [ ] **Audit the sibling blind truncations** — same class of bug:
  `unit_panel.py:159` `[:30]`, `:171` `[:16]`, `ui_manager.py:94` `[:44]`.
- [ ] **Shared font module + UI scale factor** (`ui/fonts.py`) — one place that
  resolves a semantic size (`tile_cost`, `hotkey_badge`, `tooltip_title`,
  `tooltip_body`, `body`…) against a scale derived from resolution. Migrate the 44
  call sites. Structural prerequisite; everything else here is cosmetic without it.
  Drop the dead `command_card.small_font` (`:63`) in passing.
- [ ] **Scale the sidebar with resolution** — `MINIMAP_WIDTH` (and the card's tile
  geometry) become derived, not constant; `apply_resolution` computes them. At 1080p
  the sidebar grows ~1.5×. Costs map view area — that's the accepted trade.
- [ ] **Cost as icons + a duration icon.** Replace `_compact_costs`'
  `"150G 100W"` (`command_card.py:456-462`, `RESOURCE_LETTER` at `:37`) with
  icon+number pairs on the tile, and a clock icon for build/research time **in the
  tooltip**. Needs a legibility check: two icon+number pairs must fit one tile row
  at the scaled size without re-creating the cramping this section exists to fix —
  if they don't, that's a signal the sidebar scale factor is too low.
  **⚠ The existing resource icons are NOT drop-in.** `gold/lumber/stone/food/house_icon.png`
  exist at 1000–1024 px, but all are **fully opaque (alpha=255 everywhere) with
  baked-in dark brown backgrounds** (corners ≈ RGB(32,20,8)). They only work in the
  top bar because the banner behind them is also dark. Blitted at ~12–14 px onto a
  tile's green fill they render as **dark opaque squares**, and 1000→14 px
  downscaling turns them to mud. → **re-cut as true transparent cut-outs** (or
  regenerate small), and add a **clock/duration icon which does not exist at all**.
  Also: resource icons load in `core/game.py:208-223`, **not** `sprite_manager`, and
  `ui/components/icon_loader.py` has no path to them — wire that up.
- [x] Add the coin/clock prompts to `REQUIRED_VISUAL_ASSET_PROMPTS.md` in house style —
  *done 2026-07-17.* Items **28–32** (`gold/wood/stone/food/time_glyph.png`), plus a new
  **HUD Cost Glyphs** style section that deliberately overrides the file's UI-Icons rules,
  and `tools/preview_cost_glyphs.py` as the gate. Three decisions the prompts encode, each
  measured rather than assumed:
  - **New files in `assets/ui/Glyphs/`, not replacements.** The legacy `*_icon.png` plates
    are drawn at 48 px on the dark top banner where they look right; overwriting them to
    serve the cost row would restyle the top bar as a side effect. Framed plate in the
    banner, bare glyph inline. (So no pop/house glyph is needed — the tile cost row is
    gold/wood/stone/food only, per `RESOURCE_LETTER`.)
  - **Regenerate, not "re-cut".** The plan assumed a keyable dark background; the art
    actually has a *rounded plate with a bronze border baked in* and the subject composed
    to fit inside it. There is nothing to key out.
  - **⚠ The plan's "blitted onto a tile's green fill" is wrong** — every surface a glyph
    touches is dark (`42,52,42` affordable / `45,42,32` locked / `50,38,38` unaffordable /
    `67,77,67` hovered / `10,10,14` tooltip). So *fill brightness*, not the dark outline,
    carries readability, and the natural colors fail: mid-brown wood scores **1.84** and
    roast-red food **1.36** contrast on the tile. The prompts specify measured fills
    (wood `196,142,92` = 4.54, food `230,125,95` = 4.60) and cap outlines at 3–4 % so they
    don't eat a 14 px glyph's core. Also: single objects only — today's clustered gold
    (ingot + 4 coins) and lumber (3 logs + 2 planks) are *identical warm smears* at 14 px.
- [ ] *(latent, trivial)* `command_card._hovered_rect` (`:548`) is never reset to
  `None`; harmless today, read via `getattr(...) or self._panel_rect`.
- [ ] **Update `tests/test_command_card.py`** — 18 tests assert the *old* anatomy
  (per-selection content, tile text, hotkey placement). Stripping the name and
  re-flowing the tile will move them; that's expected, but they must be re-asserted
  against the new anatomy rather than deleted. Add a tooltip word-wrap test and a
  draw-order test (tooltip after the map border) — the occlusion regression shipped
  precisely because no test could see it.
- **✅ Verify:** at 1920×1080 fullscreen (the default), on a rendered frame:
  (1) every tile's icon reads instantly at normal viewing distance and its cost is
  legible without leaning in; (2) **hovering any tile shows a tooltip that is fully
  visible with nothing painted over it, no word chopped** — check a long one (gate,
  fletching) specifically, since those are the current worst; (3) cost is icons+numbers
  on the tile and the tooltip shows a clock duration; (4) **a player who has never seen
  the game can still name every tile via hover alone** — that's the real bar now that
  the name has left the tile; (5) 720p still lays out correctly. Screenshots at both
  resolutions attached to the gate. **Fold in the §8.2.1 human check here** (windowed
  mouse-only *and* keyboard-only play-through) — it was pending anyway and the HUD is
  changing underneath it.

---

## 4. §11 — Track D: World, art & atmosphere *(new 2026-07-17)*

**Why this is a new track.** Track C is UI/HUD and game systems; nothing in the
plan covers *the world's visual identity*. The map is now the least-finished part
of the game, and the gap is measurable rather than a matter of taste: the tileset
is **photo-texture**, while `REQUIRED_VISUAL_ASSET_PROMPTS.md` — the project's own
style guide — specifies hand-painted with crisp dark outlines for everything else.
**The current tileset violates the game's own art direction.** That is the single
biggest visual inconsistency in the build, and it's why the map reads as "simple"
next to the buildings.

**Standing constraints for this whole track:**
- **Ambient visuals are draw-side only**, on visible objects only — the precedent
  is `particle_system` / movement dust (`rendering_system.py:287-302`), explicitly
  built so headless sims and the perf gate pay nothing. Track A's numbers are
  hard-won; this track must not show up in the benchmark.
- **New prop groups are NOT covered by save/load.** `save_manager.py:47` enumerates
  groups by hand — a prop that isn't serialized **silently vanishes on load**.
- **New props must validate placement** (open approach, distance from spawns) the
  way `_place_fountain` does, or they'll strand economies. The §8.12 re-tune already
  found "a resource node with no walkable approach" costing an AI 2,500 gold.
- `tools/verify_visual_assets.py`'s `EXPECTED_DIMS` has **no `assets/tiles/` entry** —
  add one so sheet geometry is pinned by a test, not by convention.

### 11.1 Tileset overhaul — *reskin + variants* (user decision, 2026-07-17)

Current: `assets/tiles/tileset.png` (384×448) = 3×4 grid of **128×112 flat-top
hexes**, one flat sprite per type, downscaled to 64×56. `tileset.json` already
decouples `name → [col,row]` and carries `tile_width/tile_height`, so **sheet
geometry is data**. `Map.draw` blits `scaled_tile_images[name]` per visible tile;
`scale_tiles` re-scales all 12 on zoom change (6 discrete levels — cheap).

Two facts that set the scope:
- **A reskin alone is free** — zero code, same names/layout. Saves are immune
  (terrain persists as a *name palette*, not indices). The minimap **re-derives its
  colors automatically** via `transform.average_color` per tile (`minimap.py:30-37`).
- **But without variants, better art looks worse.** One bitmap per type means two
  adjacent grass tiles are the identical image; at a 48 px column pitch, detailed
  hand-painted art shows obvious repetition. This is why the decision is reskin **+
  variants**, not reskin alone.

- [ ] **New hand-painted tileset** matching the buildings' house style (crisp dark
  outlines, soft upper-left light, stylized medieval) — *not* photo-texture. Same
  12 names. Geometry may change via `tileset.json` if the art wants it.
- [ ] **Per-tile variants** *(low, ~30 lines)* — `tile_images[name] → list[Surface]`,
  deterministic pick (`hash(row, col) % len`) so a seed still reproduces the look,
  cache key `(name, variant)`. Touches `map.py:24-46, 433-434` and `minimap.py:34`
  (average across variants). 2–4 variants for high-coverage types (grass, plains,
  desert, water); 1 is fine for rare ones.
- [ ] **Pin the sheet** in `tools/verify_visual_assets.py`.
- [ ] *(stretch, cheap)* **Water fringe** — one shoreline overlay blitted only where
  `grid[r][c] != neighbour` across a water/land boundary. Biggest visual delta per
  line of code; softens the worst seam without an autotiler.
- **Deliberately NOT doing: hex autotiling.** Full 6-bit edge masks + transition art
  is the one genuinely structural item here — flat-top hex has **parity-dependent
  neighbour offsets that exist nowhere in the codebase** (the smoothing pass at
  `map.py:187-192` iterates a *square 3×3*, which is already subtly wrong for hex
  adjacency, and would need fixing first). Revisit only if variants+fringe prove
  insufficient.
- **✅ Verify:** a screenshot of grass/desert/forest fields at zoom 1.0 shows no
  obvious repeating pattern; biome boundaries don't read as a hard sawtooth; the
  minimap still looks right (it's derived); `pytest` green; zoom in/out costs the
  same as before (variant count × 12 scales per zoom change — confirm it's still
  imperceptible).

### 11.2 World props — mountains & oases *(props, not terrain — user decision)*

**Decision: props.** Mountains are **objects**, not tiles — they will not be part
of the tileset and need no terrain-type work. This is also the cheap path: the
`Fountain` (`entities/fountain.py`) is the newest and closest precedent and is
*precisely* "a decorative-or-blocking prop".

What's free, and why:
- **Nav blocking is free.** `pathfinding._blocks_navigation` (`:312-319`) is fully
  duck-typed: any object with `x/y/radius` and `hp > 0` blocks navigation.
- **Un-attackability is free.** `invulnerable` is honored by
  `combat_rules.is_valid_attack_target` (`:65-67`).
- **The drop-in art convention exists** — `rendering_system._fountain_sprite`
  (`:358-383`): load the PNG if present, else draw a procedural placeholder, cache
  either way. So the game can ship the prop *before* the sprite exists.

The ~10 touch points (all small, none architectural), following Fountain exactly:
entity class → `game.<group>` list → placement in `game_state` → nav notify →
**collision static index (`collision_system.py:52, 78-80` — nav alone is NOT
enough)** → render group tuple (`rendering_system.py:263`) → sprite fn → **save/load
(`save_manager.py:47` + rebuild)** → reset (`game.py:1232,1238`) → optional AI
awareness (`context.py`).

- [ ] **Mountain prop** — large `radius`/`size` (fountain uses `radius=70, size=[3,3]`),
  `invulnerable`, blocking. Sprites: user-generated later; ship behind the procedural
  placeholder.
- [ ] **Cluster placement so mountains form ridges, not confetti** — scattered
  singletons will read as rubble. Reuse the gaussian-cluster approach from
  `_place_forest_clusters` (`game_state.py:315-389`). **This is where mountains earn
  their keep: a ridge is a chokepoint.**
- [ ] **⚠ Validate reachability after placing** — a ridge that seals a spawn or
  orphans a resource is a match-ruining bug, and the terrain connected-components
  machinery (`pathfinding._build_terrain_components`) only models *terrain*, not
  props. Placement must verify every spawn and resource still has an open approach.
- [ ] **Oasis prop** — `invulnerable`, **non-blocking** (either `passable=True` or
  simply never call `notify_blocker_added`). **Cheapest of everything here:** the
  generator *already* has an oasis rule (`map.py:209-211`, arid tile with ≥2 water
  neighbours → grass), so the setup exists; `dirt`/`grass`/`water` tiles exist; and
  **`assets/sprites/Resources/TREE_DESERT.png` is already on disk, referenced by
  nothing** — free art. Sketch: `_place_oasis` finds a desert region, stamps a small
  `water` disc into `grid` **inside `generate_perlin_map`** (do it after `Pathfinding`
  is constructed and you must call `pathfinder.rebuild_terrain()`; do it during
  generation and it's free), then scatters desert-tree props.
- [ ] Decide whether mountains/oases affect the terrain-cover table
  (`COMBAT_FOREST_COVER_MULTIPLIER`, `config.py:216`) — terrain already has combat
  meaning; new world objects should make a deliberate choice, not inherit one.
- [ ] **Re-baseline §8.8 if mountains block meaningfully.** Chokepoints change AI
  attack pathing, walling, and tower value. Same-seed 12-match battery before/after.
- **✅ Verify:** mountains appear as ridges that units path *around* cleanly (no new
  stuck cases — cross-check against §8.13.3); no spawn or resource is ever sealed off
  across 12 seeded maps; oases read as oases; props survive save/load; the §8.8 battery
  shows no personality collapse.

*(Note: `game_state.py:306` already tests `grid[r][c] in {"water","lava","mountain"}` —
a latent leftover for a terrain type the generator never emits. Harmless; leave it,
or drop the dead `"mountain"` string so it doesn't imply a terrain path we chose
against.)*

### 11.3 Ambient life — motion & animals

- [ ] **Swaying trees** *(low — cheapest ambient win in the codebase)*. Route: a
  quantized `pygame.transform.rotate` over ~8 angle steps with a `(sprite, step)`
  surface cache, phase-offset per tree by `id(obj) % 8`. **Both idioms already exist
  verbatim**: `_draw_fountain_auras` (`rendering_system.py:172-203`, pulse quantized
  into 8 cached steps) and the dust throttle (`:296`). ~25 lines, 8 cached surfaces
  total, one blit per tree, **zero headless cost**. No new art required.
  - ⚠ `_scaled_sprite_cache` is capped at 2048 and **cleared wholesale on overflow**
    (`rendering_system.py:341-342, 421-422`) — a sway that generates many distinct
    `(sprite,w,h,mirrored)` keys will thrash it. **Quantize aggressively.**
  - Alternative (needs art): `Animation` is already decoupled from `Unit` — it takes
    a Surface + dims. But its `192,192,100` args are hardcoded at 3 call sites, and
    **nothing ticks non-unit animations**, so a sheet-based tree needs a tick site or
    draw-side driving. Prefer the rotate route.
- [ ] **Updated tree sprite** (user request) — house style; `TREE.png` is 1000×1000.
  Pairs naturally with the sway work.
- [ ] **Decorative animals** *(moderate — keep them dumb on purpose)*. **No neutral-unit
  concept exists**, and the plan already flags that wandering hostiles "need neutral-unit
  AI and stay future work" (`dynamic_events.py:7-8`). A **purely decorative** animal —
  not selectable, not targetable, no collision, no nav registration, never in
  `game.units`, existing only inside the camera frustum, driven draw-side like particles
  — **dodges all of that and is genuinely easy.** User has already scoped it this way
  ("just for visual, you can't do anything with them"). **Hold that line:** the moment an
  animal needs to path, be selected, or be attacked, it becomes neutral-unit AI and
  changes track.
  - ⚠ `_draw_all_objects` (`:261-285`) y-sorts a per-frame list from a hardcoded group
    tuple; adding a group is one line, but ambient objects then join the sort and the fog
    filter (usually what you want — animals *should* hide in fog).
  - Biome-appropriate picks are cheap variety: desert lizard/camel, grass deer/rabbit,
    birds over forest.
- [ ] *(stretch)* Ambient particles — falling leaves over forest, dust over desert —
  same draw-side, visible-only hook as movement dust.
- **✅ Verify:** trees sway visibly but don't shimmer or pop; the benchmark's frame avg
  is **unchanged** (this is the gate that matters — ambient must cost nothing headless);
  animals wander, are un-clickable and un-attackable, and hide under fog;
  `_scaled_sprite_cache` is not thrashing (check the overflow counter).

### 11.4 Terrain constants — *the enabler, do it first*

**The single highest-leverage refactor before any of the above.** There is no
terrain constants module. The impassable set is a bare literal in **11 places**
(`pathfinding.py:424` is authoritative; also `collision_system.py:520,780`,
`building_system.py:114,232,484`, `combat_system.py:71`, `gathering_manager.py:526`,
`production_manager.py:252`, `unit_watchdog.py:180`, `entities/unit.py:325`,
`tests/test_navigation.py:481`, `game_state.py:306`). Worse, `safe_terrain =
{"grass","plains","forest","dirt"}` is duplicated at `map.py:240` and `:302`, and
resource-suitability sets are duplicated at `game_state.py:266-268` and `:403-406`
— a *third* category with no name.

- [ ] Hoist `TERRAIN_TYPES`, `BLOCKED_TERRAIN`, `BUILDABLE_TERRAIN`,
  `SPAWN_SAFE_TERRAIN`, `RESOURCE_TERRAIN` into `core/config.py` and route all sites
  through them. Pure refactor, no behavior change — land it on its own with the
  navigation reference sweep green.
- **✅ Verify:** `pytest` green incl. `tests/test_navigation.py`'s dense reference
  sweep; a grep for `{"water", "lava"}` returns **zero** hits outside config;
  benchmark unchanged.

---

## 5. Track A residue — Phase 6 (heavy artillery)

**Only if §6 targets are still unmet.** Each item gated behind a fresh profile
that proves it's *still* the bottleneck. Full Phase 0–5 history in the archive.

- [ ] **numpy SoA + Numba `@njit`** on the confirmed kernel — the named residual is
  `jump_straight`+`walkable` ≈23 s cumulative of a 57 s profiled 8-player war (the JPS
  scan kernel), plus per-unit context steering at 200-unit scale (`tools/war8p.prof`).
- [ ] **HPA*** for long cross-map routes — only if long queries still dominate a flamegraph.
- [ ] **D*-Lite** incremental replanning — only if per-change replans still spike.
- [ ] **native `pyrvo2`/ORCA** — only if non-interpenetration at very high counts is
  still needed. *(Note: §8.13.3's steering fixes may move these numbers — re-profile
  after that batch before starting any of this.)*
- **Not** multiprocessing (the GIL makes threads useless for pure-Python A*, and shipping
  a constantly-changing grid to workers fights the design).
- **✅ Verify:** a py-spy flamegraph shows the targeted cost was top before and gone after.

---

## 6. Performance targets

Measured on the headless benchmark. The bar is to hold these at **200 units**.

| Metric | Target @ 200u |
|---|---|
| Update avg | **< 8 ms** |
| Update p95 | **< 16 ms** |
| Update max (worst hitch) | **< 33 ms** |
| Single AI tick max | **< 8 ms** |
| A* "too_expensive" rate | **< 1 %** |
| Watchdog teleports / min | **≈ 0** (recovery, not routine) |

- [ ] **Track A acceptance gate** — all six hold at 200 units. This is the definition
  of "performance done".
  - **Status 2026-07-13:** standard benchmark (120 s, 4p): avg **2.4** / p95 **11.5** /
    max **23** / teleports **0** — all met at 45 u. 8-player war (300 s, ~87 u): avg
    **6.7** ✓ / p95 **16.3** ~borderline / max **61** ✗ / ai_max **4.2** ✓ / teleports
    ~2.4/min ✗. 200-unit march: avg **17.6** ✗ / p95 18.9 ✗ / max 30.5 ✓ — steady-state
    steering cost, not spikes.
  - **Status 2026-07-17 (post-§8.13.3):** standard benchmark: avg **3.0** / p95
    **12.0** / teleports **0** / recoveries 0 / `terrain_rescues` 1 (new counter —
    the movement-side wedge rescue firing). avg/p95 within wall-clock noise of the
    07-13 line.
  - **Status 2026-07-17 (frame_max spike root-caused + fixed):** the ~84–93 ms
    early-game hitch was **not** a lazy init — fair-fog spectating (§8.11, 07-14)
    made benchmark AIs *scout*, and a corner-to-corner worker path costs
    ~65–80 ms of JPS; the queue's escalating retry ladder (20/40/60/80 ms)
    re-ran each such search *from scratch* per retry, then dropped 30 of the
    commands anyway. **Fix:** queued searches now **suspend their frontier and
    resume** across ~10 ms slices (`_suspended_searches` in
    `systems/pathfinding.py`). Frontiers survive incremental world changes
    (scans read the live grid; finished chains are re-walked if the grid
    revision moved; post-change no-path verdicts re-verify fresh instead of
    negative-caching; expansion caps leave an O(1) tombstone cleared on
    removals). The drain fits `PATHFINDING_QUEUE_FRAME_MS`, retries skip
    already-run pre-checks, and smoothing skips >30-cell merge tests.
    Standard benchmark: frame_max **18.2 ms** — target met again. 300 s
    vs same-HEAD baseline: max 94.5→**29.2** / p95 38.3→**12.3** / avg
    14.3→**3.1** / watchdog recoveries 79→**9** / queue drops **0**. Scout
    orders now complete instead of silently dropping (gameplay fix too).
  - The 07-13 teleport-figure caveat is **resolved**: the watchdog now tests terrain
    at full radius and movement self-rescues wedges (§8.13.3), so shoreline stalls
    can no longer hide outside the counters. Teleports stayed 0 with the fixes in.

---

## 7. §8.12 — AI depth candidates

Ordered by feel-per-effort; top three are the recommended next batch. (Landed
§8.12 work — mutual awareness, no-tunnel-vision, castle rebuild, aggression
re-tune — is in the archive, **including the failed tunings; read them before
re-tuning**.)

- [ ] **Reactive counters vs fortifications** *(low–med)* — reactive production reads
  only the enemy's *units*; a tower/castle-heavy turtle should visibly pull ram/siege.
  Cheap: include defensive buildings in the counter signal.
- [ ] **Timing pushes on power spikes** *(low)* — attack commitment bonus for ~30 s
  after a combat tech lands; sharpens personality timing identity.
- [ ] **Coordinated multi-prong attacks** *(med–high)* — main push + simultaneous
  cavalry economy raid from another bearing. Squad layer exists; needs a second
  command channel. **This is the aggression side's structural fix** — the archive is
  explicit that more parameter knobs won't do it.
- [ ] **Map control / expansion denial** *(med)* — guard posted at contested rich nodes.
- [ ] **Tower-aware army pathing** *(med)* — route around known tower coverage using the
  existing threat map (flow-field + threat infra already in place).
- **⚠ Standing balance watch-items:** `balanced` is chronically mildest (~29–43 %) and
  needs an identity pass or acceptance as the "teaching" opponent; rusher yo-yos 0–2
  wins per battery. Per-personality rates carry **matchup bias** (the fixed seed schedule
  pits rusher vs boomer in 4 of 6 matches) — the true spread is tighter than it looks.
- **✅ Verify:** §8.8 balance sim shows no single personality/tier dominating.

---

## 8. §8.9 / §8.2.1 — remaining smaller items

- [ ] **Unit active abilities** *(med–high, LATER)* — one per core unit (cavalry charge,
  spearman brace, archer volley); micro depth + a natural difficulty-tier lever.
- [ ] **Challenge presets** *(low, LATER)* — named mutator/victory/difficulty combos with
  an achievement each; pure configuration over shipped systems.
- [x] **§8.2.1 human check** — *folded into the §8.2.2 gate* (2026-07-17). It was
  the one clause automation couldn't sign off, and the HUD is about to change
  underneath it; doing it twice would be waste. Tracked there, not here.
- [ ] **Wall/gate re-enable** — `wall`/`wooden_wall`/`gate` are fully implemented but
  `buildable: false` pending **orientation-aware sprites**. Flip the flags when the art
  lands. *(Natural fit with Track D's art work.)*
- [ ] Live window resizing (resolution currently applies at startup) — noted in §8.2,
  deliberately out of scope there. Reconsider alongside §8.2.2's scale work.

---

## 9. Preserved backlog

Fully closed — see PLAN_ARCHIVE.md §9. Nothing open.

## 10. References

See PLAN_ARCHIVE.md §10 (unchanged): flow fields, JPS, HPA*, D*-Lite, context
steering, ORCA, RTS AI (utility/LOD/influence maps/blackboard), pygame perf, and
the Track B/C design-research sources with their verification status.

## 11. Track D

See §4 above. *(Numbered §11 so §9/§10 keep their archive meanings.)*
