# Projectile System Implementation

## Overview
A complete projectile system has been added to the RTS game to visualize combat attacks. The system uses pygame's built-in drawing functions to create projectiles without requiring external sprites.

## Features Implemented

### 1. Core Projectile System (`systems/projectile_system.py`)
- **Base Projectile Class**: Foundation for all projectile types with position, velocity, and trail effects
- **Arrow Projectile**: Used by archers - brown color with directional arrow shape
- **CannonBall Projectile**: Used by watchtowers - dark gray with shadow effects
- **MagicBolt Projectile**: Purple projectile with particle effects (for future magic units)
- **ProjectileSystem Manager**: Handles creation, updating, and rendering of all projectiles

### 2. Integration Points

#### Combat System Integration
- Added `projectile_system` reference to `CombatSystem`
- Created `attack_trackers` to monitor when units/buildings perform attacks
- Added `check_for_attacks_and_spawn_projectiles()` method to detect new attacks
- Added `create_attack_projectile()` method to spawn projectiles

#### Rendering System Integration
- Modified `_draw_ui_overlays()` to include projectile rendering
- Projectiles are drawn after game objects but before UI elements

#### Game Loop Integration
- Added `self.projectile_system.update(self.delta_time)` to main update loop
- Linked projectile system to combat system after initialization

### 3. Projectile Types and Properties

**Arrow (Archer)**
- Color: Brown (139, 69, 19)
- Speed: 300 units/second
- Visual: Line with arrowhead, short trail

**CannonBall (Watchtower)**
- Color: Dark gray (64, 64, 64)
- Speed: 200 units/second
- Visual: Circle with shadow and highlight, long trail

**MagicBolt (Future use)**
- Color: Purple (128, 0, 255)
- Speed: Variable
- Visual: Glowing core with particle effects

### 4. Visual Features
- **Trail Effects**: Projectiles leave fading trails showing their path
- **Dynamic Sizing**: Projectiles scale with camera zoom
- **Particle Systems**: MagicBolt includes particle generation and physics
- **Shadow Effects**: CannonBalls have 3D-like shadow rendering

## Usage

When a unit or building performs an attack:
1. The combat system detects the attack via `last_attack_time` tracking
2. A projectile is automatically spawned at the attacker's position
3. The projectile travels toward the target at its defined speed
4. The projectile disappears when it reaches the target
5. Visual effects (trails, particles) update each frame

## Future Enhancements
- Impact effects when projectiles reach targets
- Different projectile types for different unit types
- Projectile collision detection for intercepting
- Area-of-effect explosions for siege weapons
- Sound effects synchronized with projectile impacts

## Files Modified
- `/systems/projectile_system.py` - New file containing projectile classes
- `/systems/combat_system.py` - Added projectile spawning logic
- `/systems/rendering_system.py` - Added projectile rendering
- `/core/game.py` - Integrated projectile system into game loop
- `/entities/objects.py` - Removed old projectile spawning attempts

## Testing
To see projectiles in action:
1. Build a watchtower near enemy units
2. Train archers and attack enemies
3. Projectiles will automatically appear during combat