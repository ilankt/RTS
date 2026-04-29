"""Military AI logic - defense, training, and attack commands."""
import math
from utils.debug_logger import debug_log


class MilitaryBrain:
    """Every tick: defend base, train units, send army to attack."""

    DEFENSE_RADIUS = 300  # Enemies within this distance of castle trigger defense

    def __init__(self, game):
        self.game = game

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

        # 1. Emergency defense
        if enemies_near_base:
            debug_log.log(f"AI {player.name}: {len(enemies_near_base)} enemies near base! Defending.", "AI")
            for unit in military:
                if not unit.in_combat and not unit.is_engaging:
                    closest_enemy = min(enemies_near_base, key=lambda e: math.hypot(unit.x - e.x, unit.y - e.y))
                    self._command_attack(unit, closest_enemy)
            return  # Defense takes priority over everything

        # 2. Attack phase: send idle military to attack nearest enemy building
        if should_attack:
            target = self._find_attack_target(player)
            if target:
                for unit in military:
                    if self._is_idle_military(unit):
                        debug_log.log(f"AI {player.name}: Sending {unit.name} to attack {target.name} at ({target.x:.0f}, {target.y:.0f})", "AI")
                        self._command_attack(unit, target)

    def train_units(self, player, max_queue: int = 2):
        """Train military units if barracks/stable exists and we can afford them.

        Returns True if a unit was queued.
        """
        # Try barracks first
        barracks_list = [b for b in self.game.buildings
                         if b.player == player and b.name == "barracks"]
        stable_list = [b for b in self.game.buildings
                       if b.player == player and b.name == "stable"]
        
        queued = False
        
        # Train from barracks
        for barracks in barracks_list:
            queue_len = len(barracks.production_queue)
            if barracks.current_production:
                queue_len += 1
            if queue_len >= max_queue:
                continue

            # 40% warriors, 30% archers, 30% spearmen
            warriors = len([u for u in self.game.units if u.player == player and u.name == "warrior"])
            archers = len([u for u in self.game.units if u.player == player and u.name == "archer"])
            spearmen = len([u for u in self.game.units if u.player == player and u.name == "spearman"])
            total = warriors + archers + spearmen
            
            if total == 0 or (warriors / max(total, 1)) < 0.4:
                unit_type = "warrior"
            elif (archers / max(total, 1)) < 0.3:
                unit_type = "archer"
            else:
                unit_type = "spearman"

            if not self._check_pop_space(player):
                debug_log.log(f"AI {player.name}: No pop space for {unit_type}", "AI")
                return False

            success, msg = self.game.production_manager.start_production(barracks, unit_type)
            if success:
                debug_log.log(f"AI {player.name}: Training {unit_type} from barracks", "AI")
                queued = True
            else:
                debug_log.log(f"AI {player.name}: Cannot train {unit_type}: {msg}", "AI")
        
        # Train cavalry from stable
        for stable in stable_list:
            queue_len = len(stable.production_queue)
            if stable.current_production:
                queue_len += 1
            if queue_len >= max_queue:
                continue
            
            cavalry_count = len([u for u in self.game.units if u.player == player and u.name == "cavalry"])
            if cavalry_count < 3:
                if not self._check_pop_space(player):
                    return False
                success, msg = self.game.production_manager.start_production(stable, "cavalry")
                if success:
                    debug_log.log(f"AI {player.name}: Training cavalry from stable", "AI")
                    queued = True

        return queued

    def get_military_count(self, player) -> int:
        """Count of military units (warriors + archers)."""
        return len(self._get_military_units(player))

    def get_military_breakdown(self, player) -> dict:
        """Return {unit_type: count} for debug display."""
        breakdown = {}
        for unit in self._get_military_units(player):
            breakdown[unit.name] = breakdown.get(unit.name, 0) + 1
        return breakdown

    # --- Private helpers ---

    def _get_military_units(self, player):
        """All military units for this player."""
        return [u for u in self.game.units
                if u.player == player and u.name in ("warrior", "archer", "spearman", "cavalry", "healer")]

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
        self.game.selection_manager._attack_target(unit, target, self.game.pathfinder)

    def _get_castle(self, player):
        """Find the player's castle."""
        for building in self.game.buildings:
            if building.player == player and building.name == "castle":
                return building
        return None

    def _check_pop_space(self, player) -> bool:
        """Check if player has population space for another unit."""
        current_pop = len([u for u in self.game.units if u.player == player])
        max_pop = 5  # Base castle limit
        houses = [b for b in self.game.buildings
                  if b.player == player and b.name == "house"]
        max_pop += len(houses) * 5
        return current_pop < max_pop
