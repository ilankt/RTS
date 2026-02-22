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

## Current State (2026-02-22)

### Working ✅
- Core RTS gameplay (selection, movement, combat, gathering)
- **AI V2**: Simple 4-phase state machine (EARLY→GROW→ARMY→ATTACK) in `systems/ai/`
- Resource buildings required for distant resources (>200 units)
- Food costs for units (Worker:25, Warrior:50, Archer:40)
- Forest clusters, integer resource display
- Unit watchdog: detects and recovers stuck units

### AI Behavior (V2 - branch: ai-v2)
1. **EARLY**: Scripted build order: 3 workers → farm → 4th worker → house → barracks
2. **GROW**: Expand to 6 workers, build houses + resource buildings
3. **ARMY**: Train warriors (60%) and archers (40%), keep economy running
4. **ATTACK**: Send army to nearest enemy building, train replacements

### AI Files (V2)
- `systems/ai/simple_ai.py` - Main orchestrator (~530 lines)
- `systems/ai/worker_brain.py` - Idle worker detection + assignment
- `systems/ai/military_brain.py` - Defense, training, attack
- `systems/ai/building_placer.py` - Ring-search placement

### Balance
- Start: 200 gold/wood, 100 stone/food
- AI tick: 0.5s interval
- Building distance threshold: 200 units

### Pathfinding
- A* only checks static obstacles (buildings, resources, construction sites, terrain)
- Unit-unit avoidance handled by real-time collision system (NOT pathfinding)
- Failed paths are NOT cached (world state changes between ticks)

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

6. **Critical Pathfinding Fix** ✅:
   - **Root cause found**: Construction sites were NOT in pathfinding system!
   - Added construction_sites to spatial grid
   - Added building_target exclusion (like gathering_target)
   - Pathfinder now properly routes workers to construction sites
   - Increased emergency recovery timeout to 15s

### Known Issues ⚠️

1. **Construction Works!** ✅: Debug logs show workers successfully building
   - Workers reach sites and progress construction
   - Buildings complete successfully

2. **AI Improvements** ✅: AI is now more responsive
   - Decisions every 1s instead of 2s
   - Module updates every 0.5s
   - Barracks built with 2 workers instead of 3
   - Higher priority for military buildings

3. **Combat-Style Gathering** (BROKEN): Attempted unification failed
   - Workers stuck in resources, state management issues
   - Recommendation: DO NOT FIX - needs complete redesign

### Recent Fixes (2025-01-20) ✅ ALL COMPLETED

1. **AI Building Placement** ✅:
   - Fixed AI placing buildings near enemy castle (500-unit check)
   - Buildings now placed strategically near own castle

2. **Worker Crash Fix** ✅:
   - Fixed worker vanishing/crash when reaching construction sites
   - Added builder existence checks and increased nudge distance

3. **F4 Debug Panel** ✅:
   - Fixed silent game exit when toggling debug panel
   - Added try/catch with error logging to debug.dat

4. **Debug System Conversion** ✅:
   - Created convert_prints.py script
   - Converted all print() to debug_log.log() (14 files)
   - All debug output now goes to debug.dat

5. **AI Deadlock Resolution** ✅:
   - Fixed AI refusing to gather far resources
   - Added critical resource detection (0 amount = must gather)
   - Resource buildings get CRITICAL priority (150+) when needed

6. **Building Affordability** ✅:
   - Enhanced _can_afford() with detailed logging
   - Double-check resources before spending
   - Final affordability filter prevents selecting unaffordable buildings

7. **Worker Assignment** ✅:
   - Fixed multiple workers on same construction site
   - Added 50-unit proximity check for construction sites
   - Enhanced worker state verification

8. **Worker Ghosting** ✅:
   - Fixed workers teleporting after construction
   - Added position logging and proper collision re-enabling
   - Terrain validation for nudge positions

9. **Farm Building** ✅:
   - First farm gets priority score of 80
   - Reduced threshold for second farm
   - AI now builds farms consistently

10. **Barracks Building** ✅:
    - Reduced worker requirement from 3 to 2
    - Scaling priority based on worker count
    - Enhanced affordability logging

### Technical Improvements
- Comprehensive debug logging for all AI decisions
- Multiple resource verification checks
- Immediate AI re-evaluation after construction
- Force economy module updates when needed
- Smart building prioritization (need + affordability)

## Known Bugs

### Units Getting Stuck - Pathfinding and Overlapping Issues
**Status**: Mostly fixed (2026-02-22)

Major fix: Removed unit-unit collision from A* pathfinding. Units are dynamic obstacles
and should only be avoided by the real-time collision system, not treated as static walls
during path computation. Unit watchdog recovers any remaining stuck units after 5 seconds.

Remaining edge cases:
- Units can still get stuck at tight spots between static obstacles
- Collision sliding can sometimes prevent units from reaching exact positions

## Recent Bug Fixes (2025-08-10)

### Critical AI Resource Vanishing Bug ✅ FIXED
- **Problem**: AI's wood was disappearing when trying to build farms
- **Root Cause**: Silent exception handling was hiding `AttributeError` when accessing `building_template.radius`
- **Solution**: 
  - Fixed radius calculation from building size
  - Added proper error logging and resource refunding
  - Fixed import scope issues in exception handler
- **Result**: AI can now successfully build farms without losing resources

### AI Early Game Strategy ✅ FIXED  
- **Problem**: AI tried to build farm with only 1 worker, leaving no idle workers
- **Solution**: Corrected build order - train 2 workers first, then build farm
- **Build Order**: Workers (2) → Farm → Workers (5) → Barracks

## Recent Updates (2025-08-16) - Branch: newer-file-system

### Code Refactoring - File Structure Improvements ✅

1. **UI Manager Refactoring** (1,532 lines → 7 modular components):
   - `ui/components/cursor_manager.py` - Cursor operations and command modes
   - `ui/components/building_menu.py` - Two-tier building selection menu
   - `ui/components/unit_panel.py` - Unit selection display
   - `ui/components/production_panel.py` - Unit production UI
   - `ui/components/resource_bar.py` - Top resource bar
   - `ui/components/icon_loader.py` - Icon loading/caching
   - `ui/ui_manager.py` - Coordinator using delegation pattern

2. **Entity System Refactoring** (563 lines → 6 modular files):
   - `entities/game_object.py` - Base GameObject class
   - `entities/building.py` - Building class with combat/production
   - `entities/unit.py` - Unit class with movement/combat/gathering
   - `entities/resource.py` - Resource class
   - `entities/construction_site.py` - ConstructionSite class
   - `entities/data_loader.py` - JSON data loading

3. **Backward Compatibility**:
   - Added property delegation in UIManager for seamless integration
   - Example: `@property def command_cursors(self): return self.cursor_manager.command_cursors`

### Bug Fixes During Refactoring ✅

1. **Building System Issues**:
   - Fixed building menu closing before passing building data
   - Fixed mouse position boundary check (was using wrong constant)
   - Added missing debug_log import in building_system.py
   - Changed affordability colors from subtle grays to clear green/red

2. **Worker Construction Bug** ✅:
   - **Problem**: Worker would approach construction site, teleport to center, but not start building
   - **Root Cause**: Multiple issues:
     - Worker was pathed to "safe position" near site, not the site itself
     - `stop()` method was clearing `is_building` flag
     - Construction site builder link wasn't properly established
   - **Solution**:
     - Changed pathfinding to target construction site directly
     - Modified `stop()` to preserve `is_building` if `building_target` exists
     - Ensured builder link is always established when worker arrives
     - Added comprehensive debug logging for construction states

### Technical Details

- **Modular Design**: Each component is self-contained with clear responsibilities
- **Import Organization**: Fixed circular import issues with proper structure
- **State Management**: Improved state preservation during unit actions
- **Debug Enhancement**: Added BUILD_TRACK category for construction debugging

### Critical Building Bug Fix (Post-refactor) ✅

- **Problem**: Worker would reach construction site but building wouldn't start until right-clicking
- **Root Cause**: Early `return` statement in `_check_movement_targets` prevented further updates
- **Symptoms**:
  - Worker appeared to "teleport" (actually just stopped abruptly)
  - Building state was set but movement system stopped updating
  - Right-clicking fixed it by giving worker new path/destination
- **Solution**: Removed the early return, allowing movement system to continue updating
- **Result**: Workers now properly start building when reaching construction sites