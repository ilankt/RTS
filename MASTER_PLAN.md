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
| 1 | **§8.15 balance re-baseline (stone removal)** | The economy changed shape 2026-07-19 and *nothing* has been measured since |
| 2 | **§8.2.2 HUD readability & scale** | The HUD is unreadable at the default 1080p — §8.2's deferred DPI item came due |
| 3 | **§11 Track D — world, art & atmosphere** | The map is the least-finished-looking part of the game |
| 4 | §8.12 AI depth candidates | Depth, not defect |
| 5 | §6 / §5 Phase 6 Track A residue | Gated behind a fresh profile; only at 200 u |

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

## 1a. §8.15 — Balance re-baseline after the stone removal *(new 2026-07-19)*

**Stone was removed 2026-07-19** (4 resources → gold/wood/food). The removal
itself is done and test-green — full record, conversion math and the
deliberately-rejected alternatives are in **PLAN_ARCHIVE.md §8.15**. What is
**not** done is proving the new economy is balanced.

**Every cost below was derived from a worker-time conversion, not measured.**
Treat the whole table as a hypothesis.

### What changed, and what it might break

| Change | The risk it creates |
|---|---|
| Stone costs → **wood** (tower 200w, ram 200w, castle 500g/500w, temple 150w, workshop 100g/200w, siege tech 250w) | Wood becomes the dominant currency. Boomer (best wood economy) may re-dominate — the exact failure the 2026-07-14 gold carry re-tune fixed. |
| Home gold node 2500 → **3000**, one node only | If gold now runs out mid-game, armies stall; if it never runs out, map gold is pointless. |
| Map gold nodes **1-2 → 2-3** | Meant to pull labour outward. If nobody expands, the freed stone workers just idle on wood. |
| `RESOURCE_DROPOFF_CAPS["mine"]` 2 → **3** | More AI mines competing for base space — watch §7 P1 placement starvation. |
| Ram stayed **gold-free** (200w) | The archive already records "the wood-priced ram became the de-facto army". More wood income + a wood-only ram is exactly that trap re-armed. **Prime suspect if composition collapses.** |
| Starting stone (75) dropped, **not** compensated | Openings are marginally leaner. Probably noise; confirm it isn't. |

### Actions

- [x] **Measured baseline (2026-07-19)** — superseded the planned 12-match
  battery with a **30-match config matrix** (players 2/3/4 × maps 50/70/90 ×
  all pairings/mirrors × difficulty axis), **equal-cost arena duels**
  (`tools/arena_match.py`), and new per-unit combat instrumentation
  (damage/kills/losses/healing — `stats_damage_dealt` et al.). Full findings
  with evidence and the proposed change list:
  **[tools/BALANCE_REPORT_2026-07-19.md](tools/BALANCE_REPORT_2026-07-19.md)**
  (datasets: `tools/balance_matrix_2026-07-19/`, `tools/arena_2026-07-19_v2.json`).
  - **Ram confirmed as the predicted failure**: 24 % of late-game armies,
    2 rams kill a castle in 17 s taking 0 damage (2.25× table × 1.5× tag
    double-dip); towers deal ~7 hp/hit back (F1).
  - **Spearman monoculture is back** (most-trained, worst K/D 0.63) — §7
    defect 3 re-armed by gold scarcity; archer hard-counters the
    anti-cavalry specialist (F2).
  - **Archer 3× cost-efficiency in real games** (K/D 3.02) though arena
    stats are sane — micro-driven; warrior↔archer mutual counter tags are
    incoherent (F3).
  - **10/30 timeouts are an AI defect, not balance**: the winner sits on a
    huge bank + army vs a crippled opponent and never finishes (F4 — fix in
    §7 as "finish the map" push; also market SELL_GOLD_CAP 200→350).
  - **Techs are a no-brainer** (61–91 % uptake; full tree during a 409 s
    rush) — raise research times first (F5).
  - Healer healthy; difficulty hard>rest works, normal≈easy; personality
    spread 0.23–0.36 unreliable until F4 lands.
- [x] **Report changes 1–5 applied + same-seed validated** (2026-07-19):
  siege-vs-fortified 2.25→1.5, ram 60g+160w, archer tags cleared (+
  `weak_against` mirrors made truthful — they drive the Resisted! cue),
  research times +75 %, SELL_GOLD_CAP 350. Arena: warrior beats archer at
  cost (+477), spearman beats archer (+347) and cavalry (+461), ram castle
  TTK 17→21.6 s. Battery: warrior K/D 0.90→1.19, spearman 0.63→0.79, archer
  efficiency 3.2×→2.17× warrior, timeouts 10→8 (3p all resolve). **Ram share
  gate FAILED (24→23 %)** and spearman spam moved to #1 — structural
  (train-goal scoring under gold scarcity), NOT price. Full diff in the
  report's validation addendum. **Do not turn price/stat knobs further for
  the spam gates** — the fix is AI-side.
- [x] **Endgame close-out landed** (report change 6, §8.16, 2026-07-20):
  `overwhelming()` dominance test, full-army wave launches, 3x3 remnant
  sweep, AttackGoal regroup bypass + remnant-unit targeting, ram cap 12 %.
  Same-seed battery v3: **ram share 24 %→12 % (gate PASSED)**, no unit type
  above 25 % of armies for the first time; 2p dominance-stall timeouts
  halved; difficulty ladder unstuck (normal beats easy decisively). Tests:
  `tests/test_endgame_closeout.py`. Full diff in the report's change-6
  addendum.
- [ ] **Timeout residue** (8/30, composition changed): all four 4p FFAs
  (§7 mop-up tails — needs its own FFA close-out design), one 3-way peer
  stalemate (correct behavior, arguably), and fog-corner remnants the 3x3
  sweep lattice walks past (seed 3044) — densify/route the sweep by fog
  coverage next.
- [ ] **Personality spread**: inconclusive at N=30 (rusher swung
  0.36→0.50→0.29 across same-seed batteries; ±0.07 per win). Needs a ~3x
  battery after the sweep/FFA follow-ups — don't tune personalities on
  this data.
- [ ] **Live-play pass**: does the opening still feel like it has choices with
  one fewer resource to manage? That was the point of the change.
- **✅ Verify:** the report's re-validation gates, plus a human match
  where wood never feels like the only decision.

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
- [x] ⛔ **Tooltip content + behavior** — *landed 2026-07-17.* The tooltip now owns
  name (title row) / role / cost+duration (glyph row) / counters / availability
  reason. Kept the beside-the-tile anchor (§9 2026-07-11); hover is instant (no
  delay added — it reads fine and a delay is easy to add later if it feels twitchy).
- [x] **Strip the name off the tile; grow the icon.** *Landed 2026-07-17.* Cost-bearing
  tiles (build/unit/tech — all of them cost something) drop the wrapped name and grow
  the icon to `TILE_ICON_LARGE` (44 from 28); the tooltip carries the name. Action tiles
  (stop/stance/formation/gate/market/cancel) keep the small icon + label, since they
  have no cost and the label *is* their content. Hotkey/queue badges + state colors kept.
- [ ] **Audit the sibling blind truncations** — same class of bug:
  `unit_panel.py:159` `[:30]`, `:171` `[:16]`, `ui_manager.py:94` `[:44]`.
- [x] **Shared font module** (`ui/fonts.py`) — *landed 2026-07-17, partial.* One place
  that resolves a clean **system face** (Segoe UI / Arial / DejaVu, default fallback)
  at semantic sizes (`title`/`body`/`label`/`cost`/`badge`/`bar_text`) — the old
  `pygame.font.Font(None, N)` default read small and *uneven* (user-reported). Migrated
  the two surfaces the user sees (command_card, unit_panel); the other ~40 call sites
  still use the default font and can migrate lazily. Dead `small_font` dropped.
  - ⚠ **`ui/fonts.py` must NOT cache `Font` objects at module level** — a
    `pygame.font.quit()`/re-init cycle (the main menu and `test_phase5` both do it) leaves
    a cached Font holding a dead TTF handle and **segfaults on the next render** (cost a
    full-suite crash to find). Fonts are built per-instance in `__init__` (tied to the
    Game lifecycle, as the old code did); only the face-path *string* is cached.
  - **UI scale factor from resolution: still deferred.** The face + fixed larger sizes
    already fixed "too small/uneven"; a resolution-derived scale is the next lever if
    1440p+/4k needs it.
- [ ] **Scale the sidebar with resolution** — *still open, deliberately.* `MINIMAP_WIDTH`
  (and tile geometry) become derived, not constant; `apply_resolution` computes them.
  The big-icon + portrait-centric-header pass landed **within** the fixed 200px sidebar
  (icons fill the tile, header sprite up to 84px), so this is no longer blocking — but it
  remains the honest fix for making the whole sidebar bigger at high resolutions. Costs
  map-view area; that's the accepted trade. **⚠ 720p is the constraint**: the card already
  fills the sidebar height there, so grow the header only behind this.
- [x] **Icon-first tiles: fill the square + portrait-centric header** — *landed 2026-07-17
  (user feedback: icons/fonts/header "too small", 2nd pass).* Tile icons now **fill the
  tile** (`TILE_ICON_FILL=70`, `_icon` default), cost overlays a thin bottom **scrim**;
  the cost size is **adaptive** (readable 15px for 1-2 resources, compact 11px for the
  rare 3-resource so the archer's 75/50/40 stays one thin row instead of a fat block over
  the icon — the specific complaint). Header redesigned portrait-centric per the user:
  **name on top → big centered sprite → HP bar overlaid at the sprite's base → stats
  below** (`unit_panel._draw_single_selection`); sprite is 84px for buildings, ~56–64px
  for units (shrinks to keep stats in the fixed 118px header). Tooltip got a bold title +
  divider rule + real line spacing. `test_command_card` updated (26 tests), suite 393 green.
- [x] **Cost as icons + a duration icon.** *Landed 2026-07-17.* Tile cost row is now
  glyph+number pairs (`_draw_tile_cost_glyphs`), wrapping to a second row for the one
  3-resource case that never fit (castle 500g/200w/300s — the old text row already
  clipped it at 87px into 78). Tooltip cost row adds the hourglass duration
  (`_draw_tooltip_cost_row`); unit build time is read from
  `production_manager.units_data` since it isn't on the Unit template (the old text
  tooltip silently showed no unit time). New glyphs live in `assets/ui/Glyphs/` and
  load via a new `IconLoader._load_cost_glyphs` / `get_cost_glyph` (cached per size) —
  `icon_loader.py` now has the path to resource art it lacked. Missing-glyph fallback
  is the old letter abbreviation, tinted per resource.
  - **Sidebar scale factor deferred:** two pairs fit one tile row at the *current*
    sidebar width, so this shipped without the scale work below. The one overflow
    (3-resource castle) wraps cleanly rather than forcing the sidebar wider. Revisit if
    the scale pass changes tile geometry.
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
- [x] *(latent, trivial)* `command_card._hovered_rect` reset to `None` each draw —
  *done 2026-07-17.*
- [x] **Update `tests/test_command_card.py`** — *done 2026-07-17.* The old anatomy tests
  keyed on `slot['name']` (kept), so they held; added new-anatomy tests: costs-as-dict,
  glyphs load at size, tooltip cost-row + duration, unit build_time-from-JSON regression,
  and an end-to-end hovered-cost-tile frame render. Plus the earlier word-wrap and
  draw-order tests. 26 tests, full suite 393 green.
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

**ROSTER SIMPLIFIED 2026-07-18 (user decision):** the 12-type photo-texture
roster is gone. New roster: **grass, desert, swamp, dirt + water_shallow,
water_deep** (6 names, 3×2 sheet, 384×224). Forest/mountain/lava tiles are
PROPS now: trees = choppable resources with biome sprites (desert wood uses
`TREE_DESERT.png`, wired), mountains = §11.2 props (landed same day), the
forest-cover combat mechanic dropped with the forest tile (user decision —
the new-world balance baseline supersedes the old cover-on evidence).
Old saves load via `LEGACY_TERRAIN` name mapping. Generation rewritten:
elevation/moisture → 6 types, deep water always ringed by shallow, spawns
confined to the largest land component (a water-sealed "safe" pocket used
to be a valid spawn — found by the mountain-reachability BFS).

- [ ] **New hand-painted tileset** matching the buildings' house style — *not*
  photo-texture. The **6 new names**; prompts ready in
  `REQUIRED_VISUAL_ASSET_PROMPTS.md` ("Terrain Tileset"). Until it lands the
  game runs on a placeholder sheet derived from the legacy art
  (`tools/build_placeholder_tileset.py`; swamp = recolored forest,
  water_deep = darkened water).
- [x] **Per-tile variants** — *landed 2026-07-18.* `tile_variants[name] →
  list[Surface]`, deterministic per-coordinate pick (never the seeded RNG),
  `tileset.json` accepts `"variants": [[col,row],…]` per tile; until real
  variant art exists, all 6 types get 4 FREE derived variants
  (hex-symmetric flips + 180°). Minimap averages across variants.
  `tests/test_tile_variants.py`.
- [x] **Pin the sheet** in `tools/verify_visual_assets.py` (384×224).
- [x] **Edge transitions (supersedes the water-fringe stretch item AND the
  deferred autotiling)** — *landed 2026-07-18 (user request).* Procedural
  texture splatting, no transition art ever needed: the higher
  `TERRAIN_BLEND_PRIORITY` terrain feathers ~30 px (sheet res) into its
  lower-priority hex neighbours through 6 per-direction alpha masks +
  pre-blended per-terrain overlays, precomputed per map cell
  (`Map.build_transitions`, rebuilt on save-restore) and blitted over
  boundary tiles only. The old blocker — "parity-dependent neighbour
  offsets exist nowhere in the codebase" — died when `Map.hex_neighbors`
  landed for the mountain BFS; its direction order (N S NW SW NE SE) IS
  the mask order, parity-tested in `tests/test_tile_transitions.py`.
  Because overlays derive from the live tile images, the hand-painted
  sheet upgrades the transitions automatically. Measured: 2.49 → 2.75
  ms/frame full draw (+0.26 ms), 989 boundary cells on a 70×70 map.
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

- [x] **Mountain prop** — *landed 2026-07-18* (`entities/mountain.py`): radius
  60–110 scaled by relative elevation, `invulnerable`, blocking; all fountain
  touch points wired (collision static index, nav, render group, minimap,
  save/load v4, restart). Placeholder massif draws until
  `assets/sprites/Props/Mountain.png` exists (prompt in
  `REQUIRED_VISUAL_ASSET_PROMPTS.md`).
- [x] **Ridge placement** — *landed:* candidates = top slice of ELIGIBLE land
  by elevation (adaptive threshold — the island generator peaks at the
  excluded map center, so any absolute cutoff starved or flooded), ~2-tile
  chaining separation turns perlin's high blobs into contiguous ridges.
  Spawn areas + map center stay clear.
- [x] **⚠ Reachability validated** — *landed:* hex-adjacency BFS
  (`Map.hex_neighbors` — the codebase's first true parity-correct hex
  adjacency) with ±1-tile tolerance on spawn coords (the §8.13.4 round-trip
  lands them a tile off); any mountain severing a spawn pair is deleted.
  Bonus find: **spawn selection could pick a water-sealed pocket** — spawns
  are now confined to `Map.largest_land_component()`.
- [x] **World props round 2** — *landed 2026-07-18 (user art batch):*
  generic `Prop` entity + type registry (`entities/prop.py`) — **rocks**
  (blocking outcrops on open ground), **dead trees** (swamp scenery,
  non-blocking), **ruins** (rare blocking landmark, minimap dot).
  Placement is art-gated (a type only spawns if its sprite exists), joins
  the reachability guarantee, saves in v4. Mountain variants land as
  `Mountain_N.png` (auto-loaded, position-stable per-instance pick).
  **Latent bug fixed in passing:** the pathfinder's bulk rebuild
  enumerated only buildings/resources/sites — every `mark_dirty()` (one
  runs right after setup, another after every load) silently DROPPED
  fountains/mountains from the nav grid, so units pathed *through* ridges
  and only the collision system pushed them out. All static neutrals are
  now in the sweep; 3-seed stuck-probe unchanged (76/56 vs 84/49).
- [ ] **Oasis prop** — non-blocking; desert region + small shallow-water
  stamp during generation + desert-tree props (art wired: wood on desert
  renders `TREE_DESERT.png`; reeds art still ungenerated).
- [ ] **Re-baseline §8.8** — REQUIRED now, not conditional: new generator +
  ridges + no forest cover = a new world. Same-seed 12-match battery
  (12 parallel 1-match processes) once the hand-painted art lands.
- **✅ Verify (open):** live-play pass — units path *around* ridges cleanly
  (cross-check §8.13.3 stuck cases); props survive save/load (test-covered);
  §8.8 battery shows no personality collapse.
- **Stuck-unit rate: NO regression (measured properly).** A first single-seed
  probe suggested 7 → ~25 recoveries per match; a 3-seed A/B (old world at
  9289118 vs new, 10 sim-min 4-AI each) shows **82 recoveries / 49 unique
  stuck units vs 84 / 49** — identical. The initial number was one calm
  old-world run vs one noisy new-world run (per-process id() jitter makes
  even fixed-seed runs vary — same reason the balance battery runs as
  parallel single matches). The REAL, pre-existing signal both worlds share:
  ~25 unique wedges/match, almost all units squeezed into **AI base-packing
  pockets** (gaps of 4-30 px between placed buildings — instrumented probe:
  24/24 events touching a building). Mountains contribute ~nothing (2/23
  near a ridge). Watchdog self-heals every case. Cure remains §6 local
  steering; a cheap mitigation candidate: minimum building-gap of one unit
  diameter in `building_placer`.

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

- [x] Hoist `TERRAIN_TYPES`, `BLOCKED_TERRAIN`, `BUILDABLE_TERRAIN`,
  `SPAWN_SAFE_TERRAIN`, `RESOURCE_TERRAIN` into `core/config.py` and route all sites
  through them. *Landed 2026-07-18* — plus `LEGACY_TERRAIN` (old-save name mapping)
  when the roster simplified the same day. Two drifts found and resolved: a phantom
  "mountain" tile in one blocked set, and the two resource-suitability copies
  disagreeing about cracked_dirt.
- **✅ Verified:** suite green incl. the navigation sweep; grep for the literals
  returns zero hits outside config.

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

## 7. §8.12/§9 — AI depth: behavior diagnosis (2026-07-17) & improvement plan

**Evidence base:** 12-match instrumented behavior battery, 2026-07-17 — varied
maps (50×50–90×90), 2–4 players, forced personality matchups. Dataset:
`tools/behavior_battery_2026-07-17/`; harness: `tools/instrumented_match.py`
(per-tick chosen-goal histograms + 30 sim-s tactical samples),
`tools/launch_behavior_battery.py`, `tools/analyze_behavior_battery.py`.
11/12 completed, avg 1130 sim-s. Wins: boomer 5/8, turtle 4/8, rusher 1/7,
balanced 1/7 (matchup-bias caveat applies). User-reported complaints (no
healers, few cavalry, no formations/ram protection, no mid control, no
expansion) **all reproduced**, plus two structural defects underneath them.

### Measured defects, ranked by leverage

1. **Placement starvation** *(structural — the biggest single lever)*. Probe on
   seed 2001: `BuildingPlacer.find_position` returned None **180/180** times for
   mine, 171/172 quarry, **162/162 temple**, 40/43 house for the turtle player —
   whole minutes wanting a building it can never place. Two causes
   (`systems/ai/building_placer.py`): (a) `_find_near_resource` ring-searches
   80–220 px around ONE chosen cluster with no lattice fallback and no
   next-best-cluster retry; (b) `_find_near_castle`'s fallback lattice is capped
   at ~356 px (`_fallback_cap`) to respect the §8.10 wall-line invariant — for
   **walls that are currently `buildable:false`**. A congested base exhausts the
   disc permanently. Downstream: 15/30 players never built a stable, temples
   missing in 17/30, `build_*` goals topped-but-failed thousands of ticks
   (rusher `build_farm` 4451, boomer `build_stable` 1457, boomer `build_temple`
   664 across the battery).
2. **One-action-per-tick contention.** Only one goal executes per tick, and
   `AttackGoal`'s always-succeeding floor (70 + 8/unit) crowds out build/train
   goals — already documented per-goal in code comments (stable "lost 557/560
   ticks", cavalry "279/281"); the battery shows it is systemic, not per-goal.
3. **Composition collapse.** Every personality converges to the same army:
   spearman 33–34 %, ram 24–31 %, warrior 14–19 % — signature targets (rusher
   warrior 0.45, turtle archer 0.40) never realized. Cause: `can_afford` zeroes
   the score, so under chronic gold scarcity the cheapest-gold unit (spearman
   60 g) or gold-free unit (ram) wins the tick — affordability overrides
   composition (the 2026-07-14 instrumented finding, still unfixed).
4. **Rams march alone.** 70 % of 2372 ram-samples had the ram >150 px from the
   nearest friendly fighter (mean 557 px, max 3213 px). §8.12's squad
   interleaving mixes the *order commands go out*, but speed difference splits
   the march and nothing re-binds escorts to rams.
5. **No commanded formation.** Archers ended up behind melee in only 64 % of
   engaged samples, mean separation just ~56 px — an emergent side-effect of
   range+kiting, not positioning. No front/back lines, no counter-targeting in
   engagements (spearman doesn't seek cavalry; `strong_against` affects
   training and damage, never target selection).
6. **No mid/fountain play.** Fountain presence 7–22 % of samples (peaks are
   transient retreat rallies — the only fountain logic is the §8.9 regroup
   rally). Nobody *holds* the healing fountain.
7. **No expansion.** **0/30** players built a second castle; no goal exists
   (`RebuildCastleGoal` only fires after castle loss).
8. **Healers half-landed.** The §9 enablement works where support weight is
   high and the game runs long: 12/30 players trained healers (boomer up to 8,
   turtle 7). Rusher/balanced almost never (weighted temple 35/70 vs attack
   floor 70+); 5 players built the temple then trained 0 healers.

### Improvement plan — **P1–P6 LANDED 2026-07-18** (evidence below)

Validation: full test suite 380 passed (+1 fixture updated for the new
farm worker-gate); same-seed §8.8 balance battery
(`tools/balance_12_2026-07-18_after_ai_depth.json`); behavior battery
"after" dataset `tools/behavior_battery_2026-07-18_after/` vs the
2026-07-17 baseline.

- [x] **P1 — Placement starvation fix**: dropoffs ring-search up to 5 ranked
  clusters (`ranked_resources_for_dropoff`) with a lattice fallback + 10 s
  backoff; the castle-ring lattice cap lifts to 600 px when no wall line can
  exist (walls disabled or `wall_segments==0`). Probe on the baseline's worst
  seed: temple went 162/162 failures → places first try; mine/quarry 100 % →
  0 failures. Residual `build_mine` fallthrough (~600-800/battery) is bounded
  backoff retries where no gold cluster has buildable ground.
- [x] **P2 — Two-lane goal selection** (`Goal.kind` behavior|action):
  defend/attack/scout claim the mode, build/train/research/trade claim the
  spend — one of each per tick. Games turned decisive: balance battery 12/12
  completed (0 timeouts, avg 514 sim-s) with the win spread collapsing to
  0.43-0.57 across all four personalities (was 0.33/0.43/0.57/0.75 in
  `balance_12_final2.json`). **Meta is faster and deadlier — watch human-game
  difficulty.**
- [x] **P3 — Roles, escorts, counters** (`military_brain`): counter-weighted
  target selection in defense and attack (`strong_against`, 260 px bonus,
  400 px anchor radius); ram escort contract (2 fighters per working ram,
  and a ram never advances beyond its escort — it falls back to the nearest
  fighter instead); archer back-line leash (follow the front at 110 px with a
  90 px standoff behind it, support-fire the front's target once engaged).
  Ram-alone samples: 70 % → 36 %, mean alone distance 557 → 347 px.
  **Formation caveat:** the crude "archers farther than melee" proxy went
  64 % → 46 % — counter-targeting now marches archers *at* enemy melee, which
  the proxy reads as "in front". Needs an eyeball pass in a real game (F4)
  before believing either number.
- [x] **P4 — Fountain control** (`ControlFountainGoal`, support/behavior lane
  + `post_fountain_guards`/`_maintain_fountain_guards`, per-personality
  `FOUNTAIN_GUARD_TARGETS` turtle 3 / boomer 3 / balanced 2 / rusher 0):
  fountain presence turtle 45 %, boomer 38 %, balanced 25 %, rusher 10 % of
  samples (baseline 14/22/7/8 — and those were transient retreats).
- [x] **P5 — Expansion** (`ExpandCastleGoal` + placer
  `find_expansion_anchor/position`, castle cap 2, first castle stays the
  ctx.castle anchor, any idle castle trains workers): implemented and fired
  in one battery game, but the post-P2 meta keeps AI gold banks ~100 — the
  1.2× bank gate mostly won't trigger in AI-vs-AI. Expect it vs passive
  humans/big maps; see watch-items before tuning the threshold.
- [x] **P6 — Composition under scarcity**: filler training goes silent while
  a sibling composition unit is under target, unaffordable, and trainable
  (bank for the right unit). Signature comps re-emerged: rusher warrior-led
  33 % (was 18 %), turtle/boomer archer 24 % / low warrior; the spearman
  monoculture (33-34 % for every personality) is gone. Cavalry 3-5 %
  everywhere (was 0 for 17/30 players); healers trained by 12/30 players
  incl. balanced (baseline: turtle/boomer only).

### Standing candidates (pre-battery list, still valid)

- [ ] **Timing pushes on power spikes** *(low)* — attack commitment bonus for ~30 s
  after a combat tech lands; sharpens personality timing identity.
- [ ] **Coordinated multi-prong attacks** *(med–high)* — main push + simultaneous
  cavalry economy raid from another bearing. Squad layer exists; needs a second
  command channel. Natural extension of P3's role tags (flank role = raid channel).
- [ ] **Map control / expansion denial** *(med)* — guard posted at contested rich
  nodes; generalizes P4.
- [ ] **Tower-aware army pathing** *(med)* — route around known tower coverage using the
  existing threat map (flow-field + threat infra already in place).
- [x] **Reactive counters vs fortifications** — landed for rams (`TrainRamGoal`
  counts enemy fortifications since §8.12 batch 3); battery confirms rams pull
  toward towered enemies. Generalize only if P3's counter-targeting leaves a gap.
- **⚠ Watch-items after the 2026-07-18 pass:**
  - **Meta speed**: two-lane selection made AI games fast and decisive (avg
    514 sim-s, 0 timeouts in the balance battery). Against humans this is a
    sharper early game — if playtests feel oppressive, the lever is
    personality attack thresholds, NOT re-coupling the lanes.
  - **Formation proxy vs reality**: the archers-behind metric dropped while
    commanded positioning was added (see P3 note). Verify by eye (F4 debug
    panel, a spectator game) before any tuning; the proxy conflates
    counter-charges with bad formation.
  - **Expansion reachability**: `ExpandCastleGoal` needs ~600 banked gold;
    the aggressive meta never banks that in AI-vs-AI. If expansions should
    appear there, build an income-reservation mechanism (boomer saves toward
    a chosen expansion) — do not just lower the threshold, it will bankrupt
    army production.
  - **Cavalry share** (3-5 % trained vs 10-15 % targets for rusher/balanced)
    — stables now get built (P1) and banking helps (P6), but stable timing is
    late in short games. Revisit only with same-seed evidence.
  - **FFA mop-up tails**: 90×90 4-player games can stalemate at the 2400 s
    cap with crippled survivors scattered (seed 2010). A "finish the map"
    endgame push for the last standing army would close it.
  - Per-personality win rates still carry **matchup bias** — check
    matches_detail before concluding.
- **✅ Verify (P1-P6, done 2026-07-18):** 380 tests pass; balance battery
  12/12 decisive with win spread 0.43-0.57 (no personality dominating);
  behavior battery: action-lane fallthrough noise ~10× down (worst residue is
  bounded mine-placement backoff), ram-alone 70 %→36 %, fountain presence up
  for every holder personality, signature compositions restored, healers
  trained by 3 of 4 personalities. Formation and expansion remain
  watch-items above.

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
- [ ] **Combat visual feedback still leaks through fog** *(low, watch)* — floating
  damage numbers and attack particles spawn for fights the human can't see
  (`combat_system.py` damage-events loop: `add_damage_notification` +
  `spawn_attack_particles`). The companion **audio** leak (hit/death SFX audible
  through fog — user-reported) was fixed 2026-07-17 by gating on
  `_audible_to_human` (= `fog.is_object_visible`); the visuals should use the same
  gate. Left unfixed pending a report that the popups/sparks are actually visible
  through fog — the numbers may already be clipped at render.

---

## 9. Preserved backlog

Fully closed — see PLAN_ARCHIVE.md §9. Nothing open.

## 10. References

See PLAN_ARCHIVE.md §10 (unchanged): flow fields, JPS, HPA*, D*-Lite, context
steering, ORCA, RTS AI (utility/LOD/influence maps/blackboard), pygame perf, and
the Track B/C design-research sources with their verification status.

## 11. Track D

See §4 above. *(Numbered §11 so §9/§10 keep their archive meanings.)*
