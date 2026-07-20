# Balance Report — 2026-07-19 (post-stone-removal baseline)

**Status: changes 1–5 APPLIED and same-seed validated the same day — see the
Validation addendum at the end. Change 6 (endgame push) remains open.**
Per §1 ("balance changes require same-seed validation before they're believed"),
every proposal below must go through the re-validation protocol at the end.

## Method

Three independent instruments, run against HEAD after the stone removal:

1. **30-match matrix battery** (`tools/launch_balance_matrix.py` →
   `tools/balance_matrix_2026-07-19/`): all 6 personality pairings twice
   (seats swapped), 50/70/90 maps, 3p/4p FFA, 4 personality mirrors,
   5 difficulty-axis matches (easy/normal/hard). 30/30 completed, 0 crashes.
2. **Arena duels** (`tools/arena_match.py` → `tools/arena_2026-07-19_v2.json`):
   equal-count and equal-cost unit matchups on open ground with attack-move
   orders, AI brains disabled — isolates raw stats from AI behavior. 3 seeds
   per duel. Mirror-duel noise band: **±~100 gold-equivalent (ge)** — margins
   inside that are ties. (v1 of the arena produced 240s standoffs — back
   spawn ranks sat outside the 200px idle-aggro radius; v2 issues attack-move
   like a real army order. Use v2 only.)
3. **New combat instrumentation** (landed with this work): per-unit-type
   damage dealt/taken, kills, losses, healing (`game.stats_damage_dealt` et
   al., exported by `instrumented_match.py`, aggregated by
   `tools/analyze_balance_matrix.py`).

**Cost normalization:** "ge" = gold-equivalent, gold 1.0 / wood 0.5 / food 0.5
(wood gathers at 2× gold's rate; food is farm-produced). Unit ge: spearman
77.5, ram 100, warrior 105, archer 120, healer 125, cavalry 130.

**Caveats.** AI-vs-AI is a proxy for human play — AI micro (archer leash,
counter-targeting) and AI blind spots (no wall play, no harass timing) both
color the numbers. Personality win rates carry matchup bias. 10/30 matches
timed out (see F4), which suppresses everyone's win counts.

---

## Headline numbers

**Win rate by personality** (25 non-difficulty matches): rusher 0.36,
boomer 0.31, turtle 0.27, balanced 0.23.

**Unit economics across the battery** (all players, all matches):

| unit | ge | trained | lost | survival | kills | K/D | dmg/1000ge |
|---|---|---|---|---|---|---|---|
| archer | 120 | 1,685 | 1,125 | 0.33 | 3,396 | **3.02** | **2,472** |
| cavalry | 130 | 583 | 286 | 0.51 | 664 | 2.32 | 1,674 |
| ram | 100 | **1,426** | 798 | 0.44 | 132 | 0.17 | 856 |
| warrior | 105 | 1,882 | 1,366 | 0.27 | 1,236 | 0.90 | 765 |
| spearman | 77.5 | **2,269** | 1,704 | 0.25 | 1,073 | 0.63 | **655** |
| healer | 125 | 126 | 42 | 0.67 | — | — | 93,671 hp healed total |
| worker | 12.5 | 2,258 | **2,032** | 0.10 | — | — | — |

**Late-game army composition** (last sample, all matches): ram **24%**,
spearman 21%, archer 21%, warrior 20%, cavalry 11%, healer 3%.

**Arena, equal cost (~900ge, open field, ± ~100ge noise):**
warrior beats archer (+173), cavalry (+220), spearman (+97 ≈ tie);
archer beats spearman (+184); cavalry beats archer (+468);
spearman beats cavalry (+440). Equal-count: cavalry > archer > warrior > spearman.

**Structures:** watchtowers dealt 137,362 damage / 680 kills (3.1 kills per
tower built — the defensive workhorse). Castles: 14 built vs **29 lost**.
Techs: 61–91% uptake across all six. Walls/gates: never built (disabled, expected).

---

## Findings, ranked

### F1 — CRITICAL: the ram is the de-facto army core and deletes buildings near-instantly

- 24% of late-game armies — the **single most common combat unit**; 1,426
  trained ≈ 48 per match. The §8.15 archive fear ("the wood-priced ram became
  the de-facto army" — a pre-stone failure mode) is measured reality again:
  it is the only gold-free combat unit in a gold-starved meta.
- Arena: **2 rams kill a 5,000hp castle in 17.1s and a watchtower in 12.4s,
  taking 0 damage**. The math: avg 100 base × 2.25 (siege-vs-fortified) ×
  1.5 (strong-vs-'building' tag) − 10 armor ≈ 327/hit ≈ **147 dps per ram** —
  the two multipliers double-dip on every building.
- The defense can't answer: tower pierce vs siege armor is 0.45× → **≈7
  hp/hit, 10.8 dps** — a tower needs 28s to kill one ram and dies in 12s.
  Only melee kills rams (warrior: ~45 dps vs ram), so an unescorted base
  with a tower still loses it to 400w of rams.

**Recommend (apply together, then re-measure):**
1. `EFFECTIVENESS_TABLE[("siege","fortified")]` **2.25 → 1.5**. Combined
   multiplier falls 3.375 → 2.25 (−33%); 2-ram castle TTK ≈ 26s, tower ≈ 18s.
   Prefer the table change over stripping the ram's `strong_against` tags —
   the tags also drive AI counter-targeting (§7 P3), so removing them would
   silently change AI behavior too.
2. **Give the ram a gold cost: 60g + 160w** (≈ same total ge). This restores
   a hard gate on spam — the stone cost used to be that gate — and directly
   attacks the 24% share. (This was flagged as the prime suspect in the §8.15
   plan before this battery; the data confirms it.)
3. Do **not** touch ram hp or the 85–115 damage band — PLAN_ARCHIVE records
   "ram hp 280 made sieges fail; 300/armor-0/85-115 is the keeper".

### F2 — HIGH: spearman is the most-trained and least-effective unit

- 2,269 trained (#1) yet worst on every axis: K/D 0.63, 655 dmg/1000ge,
  survival 0.25. The §7-defect-3 composition collapse ("cheapest-gold unit
  wins the tick under scarcity") is back — stone removal made gold scarcer,
  spearman is 60g, and P6's banking gate isn't holding against it.
- Arena: its **only** winning matchup is cavalry (+440, the intended
  counter, which works). It loses the archer matchup by design *and* by tag:
  archer has `strong_against: [spearman]` at 1.5× — the game's most
  cost-efficient unit hard-counters the dedicated anti-cavalry specialist,
  making spears strictly bad against 2 of 3 comps.

**Recommend:** remove `spearman` from the archer's `strong_against`. Keep
cost and stats as-is for now (making it cheaper-in-gold worsens the spam;
buffing stats risks re-creating the pre-P6 monoculture from the other side).
If the next battery still shows K/D < 0.8, then +15 hp (200 → 215).

### F3 — HIGH: archer is the practical efficiency king; warrior↔archer mutual counters are incoherent

- Battery: K/D 3.02 and 2,472 dmg/1000ge — **3.2× the warrior, 3.8× the
  spearman**. Arena says raw stats are sane (warrior beats archer at equal
  cost in a straight fight, +173), so the gap is range 200 + speed 60 +
  the AI's back-line leash micro (P3) — which a human opponent will feel as
  oppressive AI archer play.
- Design smell: warrior and archer each carry `strong_against` the *other* —
  a mutual 1.5×/1.5× counter that cancels into "range decides".

**Recommend:** archer `strong_against` → `[]` (F2 removes spearman; this
removes warrior). Warrior keeps `strong_against: [archer, ram]` and becomes
the unambiguous at-cost answer; cavalry keeps the mobility answer (arena:
+468). Touch archer damage (12–16 → 11–15) **only** if the next battery
still shows >2× efficiency after the tag fix.

### F4 — HIGH (AI defect, not costs): the winner refuses to finish the map

- 10/30 timeouts. In **every** 2p/3p timeout, one side holds overwhelming
  force and a huge bank against a crippled opponent and never closes — e.g.
  seed 3015: 214g / **28,814w** banked, 128-supply army vs an opponent with
  literally 1 ram; seed 3004: 5,650g/17,895w vs 3 units. All four 4p FFAs
  timed out the same way (the §7 "FFA mop-up tails" watch-item, now
  confirmed in 2p).
- This suppresses every personality's measured win rate and inflates match
  length (avg 1,268 sim-s vs 514 in the 07-18 battery) — fix it before
  trusting any future win-rate numbers.

**Recommend (Track: §7 AI, not data files):** a "finish the map" endgame
push — when the enemy's known army is ~0 and the player holds a decisive
force advantage, AttackGoal should floor at max priority and sweep scouts
for the last buildings instead of idling on a bank. Also (small, one-line):
`MarketTradeGoal.SELL_GOLD_CAP` 200 → ~350 — seed 3015's winner sat at 214
gold with 28.8k wood *just above* the sell trigger, so the market never
converted the mountain.

### F5 — MEDIUM: techs are a no-brainer

- Uptake 61–91% on all six; one rusher researched the **entire tree during a
  409-second rush** (seed 3003) while winning militarily. Uniform adoption =
  no decisions, and free power inflation for whoever is already ahead.

**Recommend:** raise `research_time` across the board ~+75% (20–30s →
35–50s) as the first knob — it costs nothing from the economy coupling and
creates real timing windows. Revisit costs (in gold, not wood) only if
uptake stays >80% after the time change.

### F6 — MEDIUM (watch): worker attrition is 90%

2,032 of 2,258 workers trained died. Towers are `strong_against: worker`
(1.5×) and raids feast. Could be fine (greed punished), could be why
economies collapse into F4's cripple states. **No change now** — instrument
"worker deaths by killer type" if the next battery still shows >80%.

### F7 — LOW: difficulty gradient holds at hard; normal ≈ easy

hard beat easy twice and normal once, all decisive; **normal failed to
finish easy in 2,400s** (timeout, partly F4's fault). Re-test after F4;
if still flat, widen normal-vs-easy via `DIFFICULTY_MODS` tick_interval
(1.0 easy → 1.2) rather than touching hard.

### F8 — OK: healer is healthy

743 hp healed per healer per match, 0.67 survival, near-zero in-fight value
(arena A/B: 8 warriors + 2 healers still lose to 10 warriors) — a sustain
unit between fights, not a combat multiplier. Matches its design. No change.

### F9 — LOW (watch): personality spread 0.23–0.36

Rusher ahead, balanced behind — but matchup bias + F4's stolen wins make
this unreliable. Re-measure after F1–F4 land; only then compare against the
07-18 baseline spread (0.43–0.57).

### F10 — Context: gold is the binding constraint, as intended — F1/F2 are its pathologies

Many players idle at 0–5 gold while wood piles into 5-figure banks. That's
the *intended* post-stone shape (gold = army limiter) — but it's exactly
what funnels the AI into gold-free rams and cheapest-gold spearmen. F1's
gold-gate on the ram and F4's market fix are the correct pressure valves;
do not add gold to the map beyond the §8.15 changes without new evidence.

---

## Proposed change list (none applied)

| # | Change | File | Finding |
|---|---|---|---|
| 1 | siege-vs-fortified 2.25 → 1.5 | `systems/combat_rules.py` | F1 |
| 2 | ram costs 60g + 160w | `data/units.json` | F1 |
| 3 | archer `strong_against` → `[]` | `data/units.json` | F2, F3 |
| 4 | research times 20–30 → 35–50 | `data/techs.json` | F5 |
| 5 | `SELL_GOLD_CAP` 200 → 350 | `systems/ai/utility/goals/economy.py` | F4 |
| 6 | Endgame "finish the map" push | `systems/ai/utility/goals/tactical.py` | F4 (AI work, separate change) |

**Re-validation protocol** (per §1, after changes 1–5 land): re-run
`tools/arena_match.py` (expect: ram castle-TTK ≈ 26s, towers threaten rams,
archer-vs-spearman inside the noise band), then the 30-match matrix with the
**same seeds**, then `analyze_balance_matrix.py` and diff against
`tools/balance_matrix_2026-07-19_summary.json`. Gates: ram army share < 15%,
spearman K/D > 0.8, archer dmg/1000ge < 2× warrior's, timeouts < 4/30 (after
change 6), no personality outside 0.35–0.65. Change 6 validates separately
(it changes AI behavior, so it must not ride along with the data re-tune).

---

## Validation addendum (2026-07-19, changes 1–5 applied)

Same-seed re-run: arena → `tools/arena_2026-07-19_v3.json` (246s wall),
matrix → `tools/balance_matrix_2026-07-19_v2/` (**637s wall**, 30/30, 0
failures; note the full pytest suite shared the machine during wave 1).
Diff vs `tools/balance_matrix_2026-07-19_summary.json`.

| Gate | Before | After | Verdict |
|---|---|---|---|
| Ram late-game share < 15% | 24% | **23%** | **FAIL** — see below |
| Spearman K/D > 0.8 | 0.63 | **0.79** | marginal (survival 0.25→0.31) |
| Archer < 2× warrior dmg/1000ge | 3.23× | **2.17×** | marginal |
| Timeouts < 4/30 | 10 | **8** (both 3p now resolve) | gated on change 6 — N/A yet |
| Personalities 0.35–0.65 | 0.23–0.36 | **0.23–0.50** | FAIL — judged after change 6 |

**What clearly worked (arena, same seeds):**
- Warrior is now the archer answer at cost (+477, was +173 under mutual-tag
  cancellation); battery K/D 0.90 → **1.19**.
- Spearman is a real unit: at equal cost it now beats archer (+347, was
  −184) *and* cavalry (+461), and ties warrior. Cavalry's role unchanged
  (beats archer +480, loses at-cost to both infantry).
- Ram castle TTK 17.1s → **21.6s**; both 3-player matches now finish.

**What the price knobs did NOT fix — and why to stop turning them:**
- Ram share barely moved (24→23%) despite +40% effective cost, and spearman
  spam *rose* to #1 (24% share) as gold shifted. The spam is structural: the
  AI's train-goal scoring under gold scarcity buys the cheapest thing every
  tick regardless of price ordering. The next lever is **AI-side** — army-mix
  targets in the train goals / `personality.py` unit preferences and the
  change-6 endgame push — not further stat/price nerfs, which would wreck
  the (now healthy) arena balance to compensate for AI behavior.
- Tech uptake 61–91% → 57–89%: the research-time knob (+75%) barely bit.
  Next knob per F5: gold-denominated cost increases — but only after the AI
  stops auto-researching everything (same structural cause).
- Rusher jumped to 0.50 (warrior buff feeds rushers); balanced/turtle/boomer
  flat. Re-judge the whole spread after change 6 — 8 timeouts still eat wins
  (one timed-out winner sat on a **204-supply army** without closing; the
  market-cap fix didn't cure F4, e.g. a winner at 80g/24,568w with no market
  standing).

**Verdict:** data-side re-tune landed and holds its arena gates; the two
failed gates are AI-behavior problems wearing balance costumes. Next work
item is report change 6 (§7 endgame push + train-goal composition caps),
then re-run this battery and judge gates 1, 4, 5.

---

## Final addendum (2026-07-20): residue fixes + the 240-game verdict

After change 6, three more close-out fixes landed (commit f365175): the
remnant sweep went 3x3 → 5x5 and skips already-visible anchors; dominance
is judged against the **weakest enemy player** (FFA mop-up starts);
AttackGoal accepts known enemy *foundations* as targets (killing the
raze-rebuild-in-fog treadmill measured in seed 3012). Same-seed v4
(`tools/balance_matrix_2026-07-20_v4/`, 538s): timeouts 10→8→7, both
formerly-stalled 3p/4p classes now produce winners, and the **difficulty
ladder is 5/5 decisive** (was 3/5 with a normal-beats-hard upset).
Discovered along the way: same-seed matches are knife-edge nondeterministic
ACROSS PROCESSES (id()-keyed tie-breaks) — seed 3012 closes at t=949 in one
process and times out in another. Same-seed comparisons carry that noise
floor; only aggregates are trustworthy.

### Personality gate: **effectively PASSED** (240 matches, 63 min, 0 failures)

`tools/personality_battery_2026-07-20/` — 6 pairings × 20 seeds × both
seats, judged on Wilson 95% intervals (`analyze_personalities.py`):

| personality | wins | rate | 95% CI | verdict |
|---|---|---|---|---|
| boomer | 62/120 | 0.52 | [0.43, 0.60] | IN BAND |
| turtle | 55/120 | 0.46 | [0.37, 0.55] | IN BAND |
| rusher | 52/120 | 0.43 | [0.35, 0.52] | in band on the point, CI touches 0.35 |
| balanced | 46/120 | 0.38 | [0.30, 0.47] | in band on the point, CI dips to 0.30 |

No head-to-head is a stomp (worst: boomer 24–14 rusher). **Do not tune**:
every point estimate is inside 0.35–0.65, and the archive's history of
confident personality re-tunes losing same-seed validation applies with
force. Watch item only: `balanced` is mildly weakest (loses all three
matchups 14–21 at worst); revisit after any future combat change.
2p timeout rate in this battery: 10% (25/240).

### F6 census: the worker-slaughter hypothesis flips

9,956 worker deaths credited by killer type: **archer 39%, warrior 27%,
spearman 23%, cavalry 11%, watchtower 1%.** Not towers (my F6 guess), not
primarily cavalry raids — it's the ARMY MAINLINE sweeping worker lines,
archers first. The §8.12 flee (trigger-on-hit → run/garrison) loses the
footrace: archers outrange (200) and outrun (60 vs 40) a worker that only
starts running after the first hit. A real fix is a design decision
(pre-emptive flee on enemy sighting? garrison at forward dropoffs? danger
memory on nodes?) — parked for the user, census attached.

### F5 residual: tech uptake barely moved

52–92% uptake after the +75% research-time change (was 57–89%). Time is
not the binding constraint; the next knob is **gold-denominated cost
increases**, which couples to army budgets and deserves its own validated
pass. Not applied.

---

## Change 6 addendum (2026-07-20, applied + validated)

Implementation (§8.16, `systems/ai/`): `MilitaryBrain.overwhelming()`
(>=12 fighters and >=3x the visible enemy force); dominant musters launch
the FULL eligible army instead of 5-unit waves; a 3x3 map-lattice remnant
sweep when the map is explored but the last enemy workers hide in fog
(§8.12 last-worker rule); AttackGoal bypasses the regroup pause and may
target remnant units under dominance; TrainRamGoal cap 25% -> 12%.
Covered by `tests/test_endgame_closeout.py` (7 tests).

Same-seed battery: `tools/balance_matrix_2026-07-19_v3/` (**642s wall**,
30/30, 0 failures; avg 1,133 sim-s).

| Gate | v1 | v2 | v3 | Verdict |
|---|---|---|---|---|
| Ram share < 15% | 24% | 23% | **12%** | **PASS** — the cap was the dial |
| Timeouts < 4/30 | 10 | 8 | 8 | improved in class, see below |
| Personalities 0.35–0.65 | 0.23–0.36 | 0.23–0.50 | 0.23–0.44 | inconclusive at N=30 |

- Ram K/D rose 0.17 → 0.28 with the smaller corps (fewer, better escorted);
  late-game armies now archer 25 / spear 24 / warrior 22 / cavalry 12 /
  ram 12 / healer 4 — the first battery with no unit type above 25%.
- Timeouts: the targeted class — a 2p winner idling beside a cripple —
  fell from 4 cases to 2, and the difficulty ladder unstuck (normal beats
  easy in 656s; was a 2,400s timeout). The remaining 8: all four 4p FFAs
  (§7 mop-up tails, pre-existing), one genuine 3-way peer stalemate
  (27/30/43 armies — dominance correctly never triggers), and seed 3044,
  where the loser's last 2 buildings sit in never-explored fog and the
  3x3 sweep lattice is too sparse to walk between anchors. Follow-ups:
  densify/route the sweep by fog coverage, and a separate FFA close-out.
- Personality spread swings wildly across the three batteries (rusher
  0.36 → 0.50 → 0.29 on the same seeds) — at 13–16 appearances, single
  wins move the rate by ±0.07. Judging this gate needs a ~3x bigger
  battery; do that after the sweep/FFA follow-ups.

---

## F5 close-out addendum (2026-07-20, applied + validated)

**Change applied: `improved_tools` I/II/III cost 75w → 100g + 75w** (flat
across levels per the §8.17 tier-pacing decision). Reached in two same-seed
iterations after a fresh baseline; datasets:
`tools/balance_matrix_2026-07-20_head/` (HEAD baseline), `_f5_50g/` (50g
probe), `_f5_100g/` (100g, kept), with `*_summary.json` for each. *(The
50g run was briefly written over the committed `_v5` dataset — a name
collision, restored from e9a1b19 before this commit; always name new
battery dirs after their experiment, not the next version number.)*

**Why a fresh baseline was required:** the 3-level tech chains (§8.17
follow-up) landed AFTER the v3 battery, so v3's tech table is level-1-only —
the tiering itself was an unmeasured F5 change. Measuring HEAD first showed
it had already done most of F5's work: uptake now falls by level and family
(fletching 70/57/47, forged 61/43/31, padded 36/23/21, siege 29/20/14) —
nothing like the old "full tree during a 409s rush". The one no-brainer left
was improved_tools at **87/86/84** — wood-only, self-financing, bought by
everyone. So the gold knob narrowed to that family alone; fletching/forged/
padded/siege costs were deliberately NOT raised (they are genuine decisions
already, and the report's own gate said revisit costs only where uptake
stays >80%).

| family (I/II/III %) | baseline | 50g probe | 100g (kept) |
|---|---|---|---|
| improved_tools | 87/86/84 | 86/84/79 | **69/56/51** |
| reinforced_frames | 80/74/69 | 83/77/76 | **86/86/81** ⚠ |
| fletching | 70/57/47 | 64/56/44 | 67/57/49 |
| forged_blades | 61/43/31 | 50/40/30 | 59/44/30 |
| padded_armor | 36/23/21 | 36/24/19 | 27/21/17 |
| siege_engineering | 29/20/14 | 26/24/20 | 24/17/13 |

- **50g was a no-op** (Δ within noise): the gather-rate tech pays for itself,
  so half a warrior of gold only delays the buy. 100g — a warrior-plus per
  level, 300g for the family — makes it compete with army production for
  real: full-family completion 84% → 51%.
- **⚠ reinforced_frames is the new top family (86/86/81)** — as the only
  gold-free tech it absorbs the blocked research spend. This is the
  *intended consequence* of the stone-removal principle (defense stays
  gold-free — "every tower an unbuilt warrior"), and it buffs building armor
  only, which distorts no army composition (see gates). **Watch-item:** if a
  future battery shows it driving tower-heavy metas, the lever is its
  research TIME (30/50/80s), never gold — raising its wood is a no-op (wood
  is non-binding) and gold would break the decided principle.
- **Gates, all three runs:** late-game ram share 11/11/11% (<15 ✓, via new
  `tools/army_composition.py`, which reproduces v3's published numbers
  exactly); no unit type above 27% of armies; timeouts 6/4/5 on the same
  seeds — the documented cross-process noise floor, not a signal;
  personality win rates swing inside the ±0.07-per-win N=30 band (turtle
  0.27/0.40/0.20) — the 240-match Wilson verdict remains the authority.

### F6 re-census (cowardly workers, landed 2026-07-19)

`analyze_balance_matrix.py` now aggregates the `worker_killers` census as a
standing section (it existed per-match since the personality battery but was
never rolled up). Worker attrition across the three 2026-07-20 batteries:
**72% / 74% / 71%** of workers trained died — down from the 90% that
triggered F6, with workers-trained also down (~1450/battery vs 2258: fewer
replacement workers needed). Killer mix is unchanged (archer ~34%, warrior
~31%, spearman ~22%, cavalry ~12%, towers ~1%) — the flee helps against
everything roughly equally. Further reduction (garrison capacity at forward
dropoffs, per-node danger memory) is a design decision left open; ~70%
attrition may simply be greed being punished, which is working as intended.
