# Changelog

What changed in each version of RTS, newest first.

Every version here has a [GitHub release](https://github.com/ilankt/RTS/releases)
with a Windows installer and a portable zip — see the
[Download page](DOWNLOAD.md) for the latest one.

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
