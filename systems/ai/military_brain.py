"""Military AI logic - defense, training, and attack commands."""
import math
from systems.combat_rules import is_building_target
from utils.debug_logger import debug_log


class MilitaryBrain:
    """Every tick: defend base, micro units, send army to attack."""

    DEFENSE_RADIUS = 300  # Enemies within this distance of castle trigger defense

    def __init__(self, game):
        self.game = game

    RETREAT_HP_PERCENT = 0.30  # Retreat when below 30% HP
    ARCHER_KITE_DISTANCE = 80  # Minimum distance archers try to maintain from melee

    def update(self, player, should_attack: bool):
        """Run military logic for one AI player.

        Args:
            player: The AI player.
            should_attack: True if the AI is in ATTACK phase.
        """
        castle = self._get_castle(player)
        if not castle:
            return

        military = self._get_military_units(player)
        enemies_near_base = self._find_enemies_near(castle, self.DEFENSE_RADIUS)

        # Pre-compute max HP for retreat checks
        max_hp_cache = {}
        for unit in military:
            max_hp_cache[unit] = self._get_unit_max_hp(unit)

        # 0. Micro: retreat damaged units, kite with archers, focus fire
        self._apply_micro(military, castle, max_hp_cache)

        # 1. Emergency defense
        if enemies_near_base:
            debug_log.log(f"AI {player.name}: {len(enemies_near_base)} enemies near base! Defending.", "AI")
            for unit in military:
                if not unit.in_combat and not unit.is_engaging:
                    # Don't send retreating units to defense
                    if self._should_retreat(unit, max_hp_cache.get(unit, unit.hp)):
                        continue
                    closest_enemy = min(enemies_near_base, key=lambda e: math.hypot(unit.x - e.x, unit.y - e.y))
                    self._command_attack(unit, closest_enemy)
            return  # Defense takes priority over everything

        # 2. Attack phase: send idle military to attack nearest enemy building
        if should_attack:
            target = self._find_attack_target(player)
            if target:
                # Find the weakest enemy for focus fire
                focus_target = self._find_focus_fire_target(player, military)
                if focus_target:
                    target = focus_target
                for unit in military:
                    if self._is_idle_military(unit):
                        # Don't attack if retreating
                        if self._should_retreat(unit, max_hp_cache.get(unit, unit.hp)):
                            continue
                        debug_log.log(f"AI {player.name}: Sending {unit.name} to attack {target.name} at ({target.x:.0f}, {target.y:.0f})", "AI")
                        self._command_attack(unit, target)

    def _apply_micro(self, military, castle, max_hp_cache):
        """Apply micro-management: retreat, kiting"""
        for unit in military:
            max_hp = max_hp_cache.get(unit, unit.hp)
            
            # Retreat if heavily damaged
            if self._should_retreat(unit, max_hp):
                if unit.is_engaging or unit.in_combat:
                    debug_log.log(f"AI: {unit.name} retreating to castle at {unit.hp}/{max_hp} HP", "AI")
                    unit.clear_all_movement_state()
                    unit.current_target = None
                    unit.in_combat = False
                    unit.is_engaging = False
                    # Move to castle
                    self.game.selection_manager._move_unit_to_position(
                        unit, (castle.x + 30, castle.y + 30), self.game.pathfinder
                    )
                continue
            
            # Archer kiting: if engaged and enemy melee is close, move away
            if unit.name == "archer" and unit.is_engaging and unit.current_target:
                target = unit.current_target
                dist = math.hypot(unit.x - target.x, unit.y - target.y)
                # If enemy is melee (short range) and getting close, kite backward
                if hasattr(target, 'attack_range') and target.attack_range <= 60 and dist < self.ARCHER_KITE_DISTANCE:
                    dx = unit.x - target.x
                    dy = unit.y - target.y
                    if dist > 0:
                        kite_x = unit.x + (dx / dist) * 40
                        kite_y = unit.y + (dy / dist) * 40
                        unit.destination = (kite_x, kite_y)
                        unit.path = None
                        unit.path_index = 0
                        unit.status = "run"
    
    def _should_retreat(self, unit, max_hp):
        """Check if a unit should retreat due to low HP"""
        if max_hp <= 0:
            return False
        return unit.hp / max_hp < self.RETREAT_HP_PERCENT
    
    def _find_focus_fire_target(self, player, military):
        """Find the weakest enemy unit/building for focus fire"""
        enemies = []
        for unit in self.game.units:
            if unit.player != player and unit.hp > 0:
                enemies.append(unit)
        for building in self.game.buildings:
            if building.player != player and building.hp > 0:
                enemies.append(building)
        
        if not enemies:
            return None
        
        # Focus on units with lowest HP percentage that are in range of our army
        best = None
        best_score = float('inf')
        for enemy in enemies:
            max_hp = getattr(enemy, 'hp', 100)  # buildings don't have max hp easily accessible
            if hasattr(enemy, 'name'):
                # Estimate max HP from data
                max_hp = self._get_unit_max_hp(enemy) if enemy in self.game.units else getattr(enemy, 'hp', 1000)
            hp_pct = enemy.hp / max(max_hp, 1)
            
            # Check if any of our military is near this enemy
            nearest_dist = min(
                (math.hypot(u.x - enemy.x, u.y - enemy.y) for u in military),
                default=float('inf')
            )
            
            # Score: prioritize low HP and nearby enemies
            score = hp_pct * 200 + nearest_dist
            if score < best_score:
                best_score = score
                best = enemy
        
        return best
    
    def _get_unit_max_hp(self, unit):
        """Get max HP for a unit from cached game data."""
        template = self.game.game_data["units"].get(unit.name)
        if template:
            return template.hp
        return getattr(unit, 'hp', 100)

    # --- Private helpers ---

    def _get_military_units(self, player):
        """All military units for this player."""
        return [u for u in self.game.units
                if u.player == player and u.name in ("warrior", "archer", "spearman", "cavalry", "ram", "healer")]

    def _is_idle_military(self, unit) -> bool:
        """Military unit with nothing to do."""
        if unit.in_combat or unit.is_engaging:
            return False
        if unit.status == "idle" or (unit.status == "run" and not unit.destination and not unit.path):
            return True
        return False

    def _find_enemies_near(self, castle, radius):
        """Find enemy units/buildings within radius of castle."""
        enemies = []
        for unit in self.game.units:
            if unit.player != castle.player and unit.hp > 0:
                if math.hypot(unit.x - castle.x, unit.y - castle.y) <= radius:
                    enemies.append(unit)
        for building in self.game.buildings:
            if building.player != castle.player and building.hp > 0:
                if math.hypot(building.x - castle.x, building.y - castle.y) <= radius:
                    enemies.append(building)
        return enemies

    def _find_attack_target(self, player):
        """Find the best enemy target to attack. Prefer castle, then nearest building, then units."""
        castle = self._get_castle(player)
        ref_x = castle.x if castle else 0
        ref_y = castle.y if castle else 0

        # Prefer enemy castle
        for building in self.game.buildings:
            if building.player != player and building.name == "castle" and building.hp > 0:
                return building

        # Then nearest enemy building
        best = None
        best_dist = float("inf")
        for building in self.game.buildings:
            if building.player != player and building.hp > 0:
                dist = math.hypot(building.x - ref_x, building.y - ref_y)
                if dist < best_dist:
                    best_dist = dist
                    best = building
        if best:
            return best

        # Then nearest enemy unit
        for unit in self.game.units:
            if unit.player != player and unit.hp > 0:
                dist = math.hypot(unit.x - ref_x, unit.y - ref_y)
                if dist < best_dist:
                    best_dist = dist
                    best = unit
        return best

    def _command_attack(self, unit, target):
        """Send a military unit to attack a target."""
        if getattr(unit, "building_only_attack", False) and not is_building_target(target):
            target = self._find_attack_target(unit.player)
            if not target:
                return
        self.game.selection_manager._attack_target(unit, target, self.game.pathfinder)

    def _get_castle(self, player):
        """Find the player's castle."""
        for building in self.game.buildings:
            if building.player == player and building.name == "castle":
                return building
        return None
