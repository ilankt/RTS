# CLAUDE.md

Guidance for Claude Code when working with this RTS game codebase.

## Quick Start

```bash
python main.py         # Run game
python -r requirements.txt  # Install deps
```

## Architecture Overview

### Core Systems
- **Coordinates**: Hex grid (row,col) for tiles, World (x,y) for smooth movement
- **Pathfinding**: A* with LOS→Pathfinding→Fallback strategies, 8-unit grid cells
- **Combat**: Type effectiveness (Slash/Pierce/Siege), auto-approach to range
- **Resources**: Gold/Stone (1/s), Wood (2/s), Food (3/s) gathering rates
- **Collision**: 2-unit buffer, sliding mechanics, no push-away

## File Structure

```
core/           - game.py (main loop), config.py, game_state.py
entities/       - objects.py (units/buildings), player.py
systems/        - pathfinding, movement, combat, building, collision, etc.
managers/       - selection_manager.py, sprite_manager.py  
ui/             - ui_manager.py, minimap.py, floating_ui.py
world/          - map.py (hex terrain), camera.py
```

## Key Features
- **Controls**: RTS standard - drag select, right-click move/attack, WASD camera
- **Units**: Workers (gather/build), Warriors/Archers (combat)
- **Buildings**: Castle, Barracks, Farm, House, Mine, Quarry, Lumbermill
- **UI**: Resource bar, minimap, selection panels, health bars
- **AI**: Full economic/military AI with state machine (Building/Attacking/Defending)

## Debug Keys
- **F3**: Pathfinding/coordinate overlay
- **F4**: AI debug panel

## Configuration (core/config.py)
```python
SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
GRID_SIZE = 8  # Pathfinding cell size
GATHERING_RATES = {"gold": 1, "stone": 1, "wood": 2, "food": 3}

## Current State (2025-01-20)

### Working ✅
- Core RTS gameplay (selection, movement, combat, gathering)
- AI with economic/military strategy
- Resource buildings required for distant resources (>200 units)
- Food costs for units (Worker:25, Warrior:50, Archer:40)
- Forest clusters, integer resource display

### AI Behavior
1. **Early**: 5 workers → resource gathering → houses
2. **Mid**: Barracks at 3+ workers → military production  
3. **Late**: Attack with 3+ units, defend base

### Balance
- Start: 200 gold/wood, 100 stone/food
- AI decisions: 2s interval
- Building distance threshold: 200 units

## Recent Feature History

### Completed Features ✅
- **UI**: Floating resource notifications, unit panels with health/stats
- **Cursors**: Smart context-aware cursor system (gather/attack/move/deposit)
- **Pathfinding**: Fixed worker resource pathfinding, LOS collision consistency
- **AI System**: Full economic/military AI with state machine
- **Debug Cleanup**: Removed all non-AI debug prints

### Known Issues ⚠️

1. **Combat-Style Gathering** (BROKEN): Attempted unification of combat/gathering movement failed
   - Workers stuck in resources, state management issues
   - Files affected: selection_manager.py, movement_system.py, collision_system.py
   - Recommendation: DO NOT FIX - needs complete redesign

2. **AI Worker Assignment**: Second+ workers may idle after training
   - EconomyModule timing issues with worker detection
   - AI only gathers gold, ignores resource diversification







```