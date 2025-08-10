# CLAUDE.md

Guidance for Claude Code when working with this RTS game codebase.

## Quick Start

```bash
python main.py         # Run game
python -r requirements.txt  # Install deps

# Debug mode (writes to debug.dat)
# Set DEBUG_TO_FILE = True in config.py
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
- **[/]**: Decrease/increase game speed (1x-5x)

## Configuration (core/config.py)
```python
SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
GRID_SIZE = 8  # Pathfinding cell size
GATHERING_RATES = {"gold": 1, "stone": 1, "wood": 2, "food": 3}
DEBUG_TO_FILE = True  # Write debug output to debug.dat
```

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

### Recent Updates (2025-08-09) - Branch: refactor/pathfinding-system (NOT MERGED)

1. **Building Menu System** ✅:
   - Two-tier menu: Economy and Military categories
   - Icons: build_econ_icon.png and build_mil_icon.png (70x70)
   - Neutral gray buttons, proper sizing

2. **Pathfinding Improvements**:
   - Fixed water tile collision (full radius checking with 8 points)
   - Simplified stuck detection, removed ghost mode
   - Emergency recovery teleports stuck units to castle after 6s
   - Fixed worker spawn speed bug (was 5x too fast)

3. **Debug System** ✅:
   - File-based debug logging to `debug.dat`
   - Categories: AI_BUILD, CONSTRUCTION, BUILD_UPDATE, BUILD_TRACK
   - Enable with DEBUG_TO_FILE = True

4. **Game Speed Control** ✅:
   - Use [ and ] keys to control speed (1x-5x)
   - Speed affects ALL time-based systems
   - Visual indicator in top-right

5. **AI Fixes** ✅:
   - Fixed AI assigning same worker to multiple construction sites
   - Added proper idle worker detection before assignment
   - Memory cache invalidation after worker assignments

### Known Issues ⚠️

1. **Worker Emergency Recovery**: Workers get teleported to castle after 6s stuck
   - Emergency recovery system may be too aggressive
   - Workers "ghost" to castle center when stuck near construction

2. **Construction Start Detection**: Workers may not trigger is_building = True
   - Movement system detection may need adjustment
   - Debug with BUILD_TRACK logs

3. **Combat-Style Gathering** (BROKEN): Attempted unification failed
   - Workers stuck in resources, state management issues
   - Recommendation: DO NOT FIX - needs complete redesign

4. **AI Worker Assignment**: Second+ workers may idle after training
   - EconomyModule timing issues with worker detection
   - AI only gathers gold, ignores resource diversification







```