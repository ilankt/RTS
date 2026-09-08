# Ages

New matches begin in **Stone Age**. Workers remain available; the initial
military roster is Clubman, Slinger and Wooden Spearman at the Barracks.

Select the **Town Center** to research **Advance to Bronze Age**:

- Own three living, completed Stone Age buildings: barracks, house, farm,
  lumbermill or mine. Duplicates count; town centers and foundations do not.
- Pay 400 food and 200 wood. Advancement takes 60 game seconds.
- Cancellation follows research's existing 50% refund rule.
- Once started, losing a prerequisite building does not cancel research;
  losing the researching town center does.
- Worker production and advancement can run concurrently, matching the
  game's separate production/research queues.

Bronze Age unlocks Mounted Spearmen, Healers and Ballistae, plus the
watchtower, stable, blacksmith, market, temple and siege workshop.

At the barracks, buy each unit-line upgrade once:

| Upgrade | Cost | Time | Effect |
|---|---|---|---|
| Swordsmen | 180 food, 120 gold | 35s | Clubmen gain +5 damage, +1 armor |
| Archers | 180 wood, 120 gold | 35s | Slingers gain +3 damage, +20 range; arrows |
| Bronze Spearmen | 140 food, 100 wood | 30s | Wooden Spearmen gain +3 damage, +1 armor |

Select the **Town Hall** to research **Iron Age**: own a completed Blacksmith
and two different specialist buildings (Stable, Temple, Market, Siege Workshop
or Watchtower), then pay 800 food, 400 wood and 200 gold; 90 game seconds.
Duplicates do not count toward the two specialists. Paid Iron line upgrades
unlock Iron Swordsman, Crossbowman, Pikeman, Heavy Cavalry, Priest and Heavy
Ballista at their respective production buildings. Infantry requires its
Bronze line upgrade first. Workers change appearance automatically on age-up.

Upgrades affect existing and future recruits. Existing wounds and orders
are preserved. Stable internal IDs (`castle`, `warrior`, `archer`, `ram`) keep
combat counters, AI composition, commands and saved references compatible.
Costs and timing live in `data/techs.json`; shared age gates live in
`systems/ages.py`.

All fourteen approved Bronze/Iron unit variants are live, including portraits,
player colors, sixteen animation frames and eight directions. Variant metadata
lives in `data/age_units.json`; Ballista uses the old `ram` ID with ranged bolt
attacks, and Crossbowman fires shorter bolts. Unit gallery: `units/index.html`.
The thirty approved painted building sprites are integrated for all three ages.

The approved Option B foot-unit readability and animation corrections are live
through `art/readability/install.py`: larger identifying equipment, corrected
two-handed Worker strokes, bow/slingshot draw and release, common spear motion,
and edge-leading Swordsman swings. Mounted units and ballistas retain their
existing art. `art/readability/installed.json` maps final Blender sources and
frame validation to this installation.
`data/age_buildings.json` maps the runtime PNGs to their preserved sources;
`buildings/index.html` remains the full-resolution gallery. Buildings, placement
previews, construction overlays and portraits follow their owner's age.

Save format v7 persists completed ages and research using the existing
technology/queue fields. Pre-v6 saves enter Bronze Age to retain access to
their previously unrestricted roster; they do not receive free unit-line
stat upgrades. Pre-v7 Rams become Ballistae while keeping their saved identity.

Verification: `tests/test_ages.py`, `tests/test_age_integration.py` and
`tools/smoke_age_integration.py` (real production, paid upgrades, wounded-unit
preservation, mid-Iron and completed-Iron save/load, world/HUD rendering and
loaded simulation). Runtime screenshots are `integrated-bronze-units.png` and
`integrated-iron-units.png`. Balance costs are initial values; the broader
proposal's economy/Blacksmith simplification remains pending in MASTER_PLAN.
