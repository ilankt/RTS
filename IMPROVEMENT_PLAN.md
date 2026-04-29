# RTS Game Improvement Plan

## Executive Summary

This document outlines a strategic improvement plan for the RTS game codebase. The game has a solid foundation with working core systems (pathfinding, combat, gathering, construction, AI), but lacks depth in content, advanced systems, and polish. Improvements are organized by priority and dependency.

---

## Current State Analysis

### Strengths
- **Solid Architecture**: Clean separation between core/, entities/, systems/, managers/, ui/, and world/
- **Functional Core Loop**: Selection, movement, combat, gathering, building, and production all work
- **AI V2**: Simple but functional 4-phase state machine (EARLY -> GROW -> ARMY -> ATTACK)
- **Pathfinding**: A* with LOS fallback, spatial grid, caching, and construction site support
- **Type Effectiveness System**: Slash/Pierce/Siege vs Light/Heavy/Fortified armor
- **Debug Infrastructure**: File-based logging (debug.dat), F3/F4 overlays, game speed control
- **Data-Driven**: Units, buildings, and resources defined in JSON
- **Modular UI**: Recently refactored into components (cursor, building menu, unit panel, etc.)

### Critical Weaknesses
- **Minimal Content**: Only 3 units (Worker, Warrior, Archer) and 8 buildings
- **No Progression**: No tech tree, upgrades, or ages
- **Shallow AI**: Scripted build order, no scouting, no micro, no retreat, no formation awareness
- **Single Game Mode**: Human vs AI only; no multiplayer, skirmish options, or victory conditions
- **Missing Core RTS Features**: No fog of war, control groups, unit stances, or formations
- **No Persistence**: No save/load system or game replays
- **Visual Polish Gap**: No particles, screen shake, or dynamic lighting
- **Audio Deficit**: Sound system exists but is underutilized
- **Map Limitations**: Procedural only; no custom maps, scenarios, or editor

---

## Phase 1: Core Experience Hardening (Foundation)

Goal: Fix remaining bugs and add missing foundational RTS features before building content on top.

### 1.1 Save / Load System
- What: Serialize GameState to JSON/binary - units, buildings, resources, player data, camera position, AI state
- Why: Essential for any serious RTS; enables testing mid-game scenarios
- Implementation: Add SaveManager in managers/. Serialize entity lists with template references + state deltas. Handle Animation and pygame.Surface carefully (re-link on load)
- Files: New managers/save_manager.py, modify core/game.py to hook F5 (save) / F9 (load)

### 1.2 Control Groups
- What: Ctrl+1-9 to assign selected units to a group; 1-9 to recall selection; Shift+1-9 to add
- Why: Fundamental RTS UX; currently impossible to quickly manage army
- Implementation: Add control_groups dict to SelectionManager. Handle multi-key combos in handle_events
- Files: managers/selection_manager.py, core/game.py

### 1.3 Unit Stances
- What: Aggressive / Defensive / Stand Ground / No Attack
- Why: Prevents units from suicidally chasing enemies across the map
- Implementation: Add stance enum to Unit. Modify combat_system.py auto-engage logic to respect stance
- Files: entities/unit.py, systems/combat_system.py, ui/components/unit_panel.py

### 1.4 Formation Movement
- What: When multiple units are given a move order, they maintain a formation (line, box, wedge) instead of converging to a single point
- Why: Prevents unit blobbing and enables tactical positioning
- Implementation: In SelectionManager.handle_right_click, calculate formation offsets based on unit count and spread units across destination area. Use movement_system.py to path each unit individually to its assigned formation slot
- Files: managers/selection_manager.py, systems/movement_system.py

### 1.5 Victory / Defeat Conditions
- What: Standard RTS conditions - destroy enemy castle, conquest, annihilation. Add a victory screen
- Why: Game currently has no win/lose state
- Implementation: Check each frame if any player has zero castles. If human player loses, show defeat screen. If all AI defeated, show victory screen. Add screens/ package for menu flows
- Files: New screens/victory_screen.py, screens/defeat_screen.py, modify core/game.py

---

## Phase 2: Content Expansion (Breadth)

Goal: Add more units, buildings, and factions so the game has strategic variety.

### 2.1 New Unit Types
Add at least 2-3 more units to create a rock-paper-scissors dynamic:

- Spearman: Anti-cavalry melee, counters Cavalry, low cost
- Cavalry: Fast raider/flanking, counters Archers, high cost
- Siege Weapon (e.g. Catapult): Anti-building ranged, counters melee, high wood/gold/stone cost
- Healer/Monk: Support/healing, countered by archers, gold cost

Implementation: Add entries to data/units.json. Add sprites. Add production entries in entities/building.py. Update systems/combat_system.py for new mechanics (healing, splash damage)
Files: data/units.json, entities/building.py, systems/combat_system.py

### 2.2 New Buildings
- Stable: Produces cavalry (wood/stone)
- Workshop: Produces siege (wood/stone)
- Temple/Monastery: Produces healers, techs (gold/stone)
- Blacksmith: Enables unit upgrades (wood/gold)
- Market: Trade resources, economic techs (wood/gold)
- Wall / Gate: Defensive barriers (stone)
- Keep: Upgraded watchtower (stone/wood)

Implementation: Add to data/buildings.json. Update building_system.py placement rules. Update simple_ai.py build order and placer logic
Files: data/buildings.json, systems/building_system.py, systems/ai/simple_ai.py

### 2.3 Tech Tree & Upgrades
- What: Basic upgrades - +1 attack, +1 armor, faster gathering, increased carry capacity
- Why: Adds strategic decision-making and economic scaling
- Implementation: Create data/techs.json. Add researched_techs set to Player. Modify Unit.calculate_damage() and armor values to check techs. Add research queue to Blacksmith and similar buildings. UI: show tech buttons in building panel
- Files: New data/techs.json, entities/player.py, entities/unit.py, ui/components/production_panel.py

### 2.4 Resource Depletion & Renewal
- What: Gold/stone deposits deplete permanently; trees regrow slowly; farms can be replanted
- Why: Creates map control tension and late-game resource scarcity
- Implementation: Add amount_remaining logic to gold/stone (like trees). Add regrowth timer for trees. Add reseed farm task for workers
- Files: entities/resource.py, systems/gathering_manager.py

---

## Phase 3: AI & Simulation Depth (Brain)

Goal: Make the AI feel intelligent and unpredictable, not scripted.

### 3.1 AI Scouting
- What: AI sends a fast unit (or its first worker) to explore the map and find enemy bases / resources
- Why: Currently AI knows player location implicitly via find_attack_target
- Implementation: Add ScoutBrain class in systems/ai/. Track explored tiles. Scout visits unseen areas. Once enemy castle found, store location. Share vision with other AI modules
- Files: New systems/ai/scout_brain.py, modify systems/ai/simple_ai.py

### 3.2 Adaptive Build Orders
- What: AI chooses build order based on map context (e.g., if far from wood, prioritize lumbermill early; if enemy rushes, skip economy and build army)
- Why: Scripted build orders are exploitable and boring
- Implementation: Replace EARLY_BUILD_ORDER list with a priority scoring system. Each tick, score possible actions (train worker, build farm, build barracks, scout) based on current state + map knowledge. Pick highest score
- Files: systems/ai/simple_ai.py

### 3.3 Military Micro & Retreat
- What: AI retreats heavily damaged units. AI uses hit-and-run with archers. AI focuses fire
- Why: Dramatically increases AI combat effectiveness without giving it unfair bonuses
- Implementation: In MilitaryBrain.update, check unit HP. If < 30%, command retreat to castle. If archer and enemy melee approaching, kite backward. For focus fire, group military and target weakest enemy first
- Files: systems/ai/military_brain.py

### 3.4 Multiple AI Personalities
- What: Different AI players have distinct strategies - Rusher, Boomer, Turtle, Balanced
- Why: Increases replayability
- Implementation: Add personality attribute to AI Player. Parametrize SimpleAISystem thresholds (e.g., Rusher transitions to ATTACK at 4 units instead of 6; Boomer trains 8 workers before army). Pick personality at game start
- Files: entities/player.py, systems/ai/simple_ai.py

### 3.5 Fog of War
- What: Players can only see areas within unit/building sight range. Minimap shows explored but not currently visible areas as dimmed
- Why: Core RTS feature; enables ambushes, scouting, and hidden bases
- Implementation: Add visibility_grid per player (2D array: unexplored / explored-but-fogged / visible). Update each frame based on unit sight radii. Only render visible objects. AI uses its own visibility for decision making
- Files: New systems/fog_of_war.py, world/map.py, systems/rendering_system.py, ui/minimap.py

---

## Phase 4: Polish & Presentation (Feel)

Goal: Make the game feel satisfying and professional to play.

### 4.1 Particle Effects
- What: Simple particles for attacks (sparks, blood), building completion (confetti/dust), resource gathering (wood chips), death (smoke)
- Why: Adds visual feedback and makes actions feel impactful
- Implementation: Create Particle class and ParticleSystem in systems/. Spawn particles on attack events, construction completion, death events
- Files: New systems/particle_system.py, systems/combat_system.py, systems/building_system.py

### 4.2 Screen Shake & Camera Effects
- What: Subtle screen shake on building destruction, heavy attacks, and castle death
- Why: Adds weight to major events
- Implementation: Add shake_offset to Camera. Decay shake over time. Trigger from combat and building destruction events
- Files: world/camera.py, systems/combat_system.py

### 4.3 Sound Design
- What: Attack sounds, construction sounds, unit selection responses, ambient map audio, UI clicks
- Why: Audio is half the experience. Currently almost silent
- Implementation: Add SoundManager in managers/. Load sounds in __init__. Play sounds at relevant game events. Add volume controls to config
- Files: New managers/sound_manager.py, core/config.py, core/game.py

### 4.4 Improved UI Feedback
- What: Damage numbers floating on hit, building progress bar, unit production progress in UI, resource gain/loss floating text
- Why: Gives players immediate understanding of what is happening
- Implementation: Extend floating_ui.py. Hook into combat_system for damage numbers, building_system for progress, production_manager for queue status
- Files: ui/floating_ui.py, systems/combat_system.py, systems/building_system.py

### 4.5 Main Menu & Game Flow
- What: Main menu with Start Game, Load Game, Settings, Exit. Pause menu (Esc). Settings for resolution, volume, game speed default
- Why: Professional presentation. Currently game starts instantly with no menu
- Implementation: Create screens/main_menu.py, screens/pause_menu.py, screens/settings_menu.py. Transition between Game and menus in core/game.py or new core/game_app.py
- Files: New screens/main_menu.py, screens/pause_menu.py, screens/settings_menu.py, core/game.py

---

## Phase 5: Code Quality & Maintainability (Tech Debt)

Goal: Clean up issues that slow down future development.

### 5.1 Remove Debug Passthroughs
- What: Many files have comment + pass where debug prints were removed (e.g., # Debug: Unit stuck + pass). Either restore useful debug logs or remove the dead comments entirely
- Why: Clutters codebase and makes it harder to read
- Files: systems/movement_system.py, systems/combat_system.py, systems/pathfinding.py

### 5.2 Centralize Magic Numbers
- What: Hardcoded values scattered everywhere - stuck thresholds (60, 120, 300 frames), collision buffers (2 units), attack range multipliers (0.9, 0.85)
- Why: Makes balancing difficult and bugs likely
- Implementation: Move all balance-relevant numbers to core/config.py or new core/balance.py
- Files: core/config.py, entities/unit.py, systems/movement_system.py, systems/combat_system.py, systems/pathfinding.py

### 5.3 Add Unit Tests for Critical Systems
- What: Tests for pathfinding (can find path around obstacle), combat (damage calculation correct), production (resources deducted, unit spawned), AI (build order progresses)
- Why: Prevents regressions as the game grows
- Implementation: Create tests/ directory. Use pytest. Test pure functions first (calculate_damage, _can_afford, pathfinding on simple grids)
- Files: New tests/test_pathfinding.py, tests/test_combat.py, tests/test_production.py

### 5.4 Decouple Game from Pygame for Headless Simulation
- What: Extract pure logic (AI, combat, pathfinding, economy) so it can run without pygame initialization
- Why: Enables faster AI training, automated testing, and potential multiplayer server
- Implementation: Move all pygame-dependent code (drawing, input, sound) out of systems/. Keep systems/ as pure Python logic. Core game loop becomes: update logic -> render (optional)
- Files: Gradual refactor across core/game.py, systems/*.py

---

## Recommended Priority Order

Start with Phase 1 items first because everything else depends on a solid foundation:

1. Victory/Defeat (1.5) - gives the game a point
2. Control Groups (1.2) - essential UX
3. Unit Stances (1.3) - fixes common player frustration
4. Save/Load (1.1) - enables longer play sessions
5. Formation Movement (1.4) - makes army control tolerable

Then move to Phase 2 for content:
6. New Units (2.1) and Buildings (2.2)
7. Tech Tree (2.3)
8. Resource Depletion (2.4)

Then Phase 3 for AI depth:
9. Fog of War (3.5)
10. AI Scouting (3.1)
11. Adaptive Build Orders (3.2)
12. Military Micro (3.3)
13. AI Personalities (3.4)

Then Phase 4 for polish:
14. Particles, Screen Shake, Sound, UI Feedback
15. Main Menu & Game Flow

Finally Phase 5 as ongoing maintenance alongside other work.

---

## Quick Wins (Can be done in 1-2 sessions each)

- Victory/Defeat screens
- Control groups
- Unit stances
- Removing debug passthrough comments
- Centralizing magic numbers into config
- Basic floating damage numbers
- Screen shake on castle destruction
- Adding 1-2 new units with existing sprites

---

*Document generated from codebase analysis on 2026-04-29*
