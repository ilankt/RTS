"""Healing fountain system (§8.9 depth round 3).

Any unit within FOUNTAIN_HEAL_RADIUS of a fountain regenerates
FOUNTAIN_HEAL_RATE hp per game-time second, capped at its max hp. Works for
every player — the fountain is a neutral objective, and holding the ground
around it is the whole point.
"""

FOUNTAIN_HEAL_RADIUS = 220.0   # world px around the fountain center
FOUNTAIN_HEAL_RATE = 5.0       # hp per game-time second


class FountainSystem:
    def __init__(self, game):
        self.game = game

    def _unit_max_hp(self, unit):
        template = self.game.game_data["units"].get(unit.name) if hasattr(self.game, "game_data") else None
        return template.hp if template else unit.hp

    def update(self, delta_time):
        fountains = getattr(self.game, "fountains", None)
        if not fountains:
            return
        collision = getattr(self.game, "collision_system", None)
        if collision is None:
            return
        for fountain in fountains:
            radius_sq = FOUNTAIN_HEAL_RADIUS * FOUNTAIN_HEAL_RADIUS
            for unit in collision.query_nearby_units(fountain.x, fountain.y, FOUNTAIN_HEAL_RADIUS):
                if unit.hp <= 0:
                    continue
                if (unit.x - fountain.x) ** 2 + (unit.y - fountain.y) ** 2 > radius_sq:
                    continue
                max_hp = self._unit_max_hp(unit)
                if unit.hp >= max_hp:
                    continue
                unit.hp = min(max_hp, unit.hp + FOUNTAIN_HEAL_RATE * delta_time)
