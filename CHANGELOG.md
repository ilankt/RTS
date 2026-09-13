# Changelog

What changed in each version of RTS, newest first.

Every version here has a [GitHub release](https://github.com/ilankt/RTS/releases)
with a Windows installer and a portable zip — see the
[Download page](DOWNLOAD.md) for the latest one.

---

## 0.13.1-beta — 2026-09-13

- Rebuilt the offline field manual with current unit and building artwork,
  searchable rosters, readable layouts, and guides to ages, factions, economy,
  combat, worker shelter, controls, saving and victory conditions.
- Added a player wiki on GitHub, generated from the same explanations and game
  data as the in-game manual.
- Added the gameplay trailer and a screenshot gallery to the repository.
- Corrected the Healer's outdated description. Gameplay balance is unchanged.
- Refreshed the Windows installer and portable download with the new manual
  and the complete current graphics set.

## 0.13.0-beta — 2026-09-12

Three ages, two factions, new unit and building artwork, stronger AI coordination,
and a broad set of repairs driven by playtesting.

### Added

- **Stone, Bronze and Iron Ages.** Advance your settlement, unlock buildings and
  research military-line upgrades. Workers and buildings change appearance with
  your age; military upgrades are paid research.
- **Two factions.** Steppe Clans recruit Horse Archers; Highland Clans recruit
  Axemen. Both signature units unlock in Bronze Age alongside the shared roster.
  Choose human and AI factions independently in Match Setup.
- **New artwork throughout the ages.** Eight-direction unit animations, mounted
  troops, ranged Ballistas, age-specific building art and matching portraits.
- **Attack warnings.** A dedicated alarm, readable messages and minimap rings
  show where your workers, army or base are taking damage, including lethal hits.
- **Automatic worker shelter.** Threatened workers seek room in a nearby defensive
  building, keep their work assignment and resume after the danger passes.
  Manual orders still take priority.

### Changed

- **AI coordination.** Better age progression, construction recovery, army
  assembly, siege escorts, local defense and endgame production. Accepted attack
  orders retain their objective while nearby defense is assigned separately.
- **Forty-minute annihilation limit.** Matches still unresolved after 40 minutes
  of game time end as a draw; conquest on the deadline takes precedence.
- **Fragile siege.** Ballista and Heavy Ballista health is now 120 instead of 300,
  with light armor. Their high damage and range are preserved; Siege Engineering
  improves damage without adding armor.
- **Food production.** Farms produce 5 food every 4 game seconds. Timer carry-over
  prevents lost production, especially at higher game speeds.
- **Quieter idle-worker reminders.** Workers must stay idle for four seconds before
  the alert appears, and its sound cooldown is doubled to eight seconds.
- **Clearer UI.** Consistent unit-line names, separate training and upgrade views,
  fitted labels and tooltips, readable fonts, larger faction portraits and a
  shared frame around the resource bar and battlefield.

### Fixed

- Workers losing their wood-gathering assignment after getting stuck among other
  workers. Recovery preserves their job and cargo, retries blocked approaches,
  and survives save/load. Forest selection also follows visible tree artwork.
- Units flickering between facing directions, including during combat. Turning
  uses stable direction selection while keeping animation phase and foot position.
- Horses appearing to run backward. All mounted run cycles now use the corrected
  stance and swing sequence in both the source models and shipped sprites.
- Upgrade tabs remaining selected after switching buildings or reselecting one.
- Mixed training queues being labeled as repeated copies of the first unit.
  Waiting units now show their actual order and counts, including single queued
  units; Ctrl-click cancels the selected waiting entry with the correct refund.
- Combat sounds revealing fighting in unexplored or fog-covered areas.
- Enemy targeting indicators appearing above your own units.
- Duplicate combat updates, lost cooldown carry-over, small research bonuses
  being rounded away, and missing damage credit on killing blows.
- Queued paths losing their place or overriding replacement orders, and scouts
  repeatedly choosing unreachable terrain.

### Compatibility and remaining work

- Save format 9 reads older saves and migrates factions, ages and Ballista health.
  Saves and settings remain outside the install folder during upgrades.
- Large-map AI games can still stall, and tight crowds can still need movement
  recovery. Faction balance and reliable conquest remain under active testing.

---

## 0.12.0-beta — 2026-07-27

The first update after launch: four rounds of fixes driven by release-day
feedback, real audio, a rebuilt economy, and a world that finally moves.

### Added

- **Real sound.** The placeholder bleeps are gone. 24 sound effects, plus
  victory and defeat stingers. Audio is now **spatial** — hits, deaths,
  gathering and collapses are heard from your camera's viewpoint, loudest at
  the centre of the screen, panned left and right, and silent off-screen.
  Previously the enemy base was audible through the fog. Repeated sounds
  rotate between variants so a long melee doesn't turn into a metronome, and
  units bark in their own voice (archers twang, everyone else swings).
- **Idle-worker alert.** A soft chime and a pulsing badge in the top bar
  whenever a worker falls idle. "Workers stop for no reason" was the most
  common complaint at launch — they were idling silently.
- **Demolish.** Hold to destroy any one of your own buildings (red X, radial
  charge, no refund).
- **Onboarding hints** that fire when you are actually stuck — a farm with no
  worker, a drop-off built while workers idle, workers idling mid-game — on top
  of timed tips. Both can be turned off or replayed from Settings.
- **Object shadows.** Soft grounding pools under every unit, building and prop,
  shaped from the sprite's own outline. Toggleable.
- **A living world.** Trees sway in the wind, cloud shadows drift across the
  map, and chimneys smoke. One shared wind direction drives all three, so the
  world agrees with itself. Buildings below 65% health smoke visibly — you can
  read a wounded building without checking its health bar. All of it is behind
  an **Ambient effects** setting.

### Changed

- **Economy rebalance.** Validated across three 200-game AI batteries.
  - The **population cap is now actually enforced**, for you and the AI, at the
    moment you order a unit. It used to be decorative for the player and the AI
    quietly played by a different rule. Base 10, +5 per house; the top bar turns
    red at the cap.
  - **Army costs shifted from gold to food** (warrior 65g/70f, archer
    60g/50w/55f, spearman 45g/50f, cavalry 65g/120f, healer 85g/70f). Gold stays
    the contested currency without throttling every soldier, and food finally
    matters.
  - Farm now costs 100 wood + 25 gold; wood gathers at 1.6/s (down from 2.0 —
    forests got much bigger this release).
- **Better maps.** Wood grows in real **forests** (14–28 trees) instead of
  scattered single trees, and forests keep clear of your castle and gold. Spawns
  now sit at least 5 tiles from water — they used to land 1–2 tiles away on
  every seed. Lakes are bigger, deeper and more common (water went from 16% to
  23% of the map), with a guard that regenerates any map that comes out drowned.
- **Match-start home survey.** The area around your castle starts explored, so
  your minimap shows your surroundings — and the AI can actually find the forest
  it spawned next to. It only gathers from explored ground, and was starving on
  wood.
- **Settings** split into Video / Audio / Gameplay. Opened from the pause menu,
  it now appears over the paused battlefield instead of cutting back to the main
  menu splash.

### Fixed

- **Units in combat ignored your orders.** A unit mid-fight would shrug off a
  right-click move and keep swinging. A move order now always means disengage
  and go — and it stays gone, even while an enemy chases and hits it.
  Attack-move still fights on the way; shift-queued orders still wait for the
  fight to finish.
- **Buildings could be placed on mountains.**
- **The healing fountain could spawn inside a base**, which turned neutral
  ground into a base buff. Map corners were also drowning by construction,
  which is what pushed a spawn to the middle of the map in the first place.
- Crash when cancelling a construction site whose builder was mid-task.
- A 5-unit move played five stacked copies of the same acknowledgement, and a
  gather order buried its own sound under the move blip.
- An AI finishing a building across the map no longer beeps at you.
- Razed buildings play a collapse instead of a human death cry.

### Performance

- **Large battles cost ~20% less per frame.** At 200 units the typical frame
  went from 15.5 ms to 12.3 ms and the worst 1-in-20 frame from 22.9 ms to
  19.5 ms, measured across 15 runs per side. The crowd also **jams 22% less** —
  fewer units wedge and need rescuing.
- The 8-player stress benchmark now meets five of its six performance targets,
  carrying more units than the run that used to fail.

### Removed

- **Walls and gates.** They were never usable — no buildable flag, no
  orientation-aware art — so the half-built content and all its plumbing is
  gone rather than sitting in the build pretending to be a feature.
- The ambient background bed, which played far too loud.

---

## 0.11.0-beta — 2026-07-23

**Initial release.** First public build: the complete game as it stood on launch
day — hex-tile procedural island maps, the full gather/build/tech/fight loop on
gold, wood and food, 7 units, 12 buildings, 6 technology lines, fog of war, and
four AI personalities to play against or spectate.

Versions before this one were not released publicly, so this is where the
history starts.
