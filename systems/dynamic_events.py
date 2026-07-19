"""Dynamic map events (§7.5): periodic neutral happenings that force
adaptation. Opt-in via the `random_events` mutator so the balance baseline
and default matches stay deterministic-boring.

V1 events: resource booms (a rich 3-node cluster of gold/wood appears
on open ground away from every castle) and bumper harvests (every farm's
food tick fires immediately). Wandering hostiles/weather need neutral-unit
AI and stay future work.
"""
import math
import random

from core.config import TILE_WIDTH, TILE_HEIGHT, FARM_FOOD_INTERVAL
from utils.debug_logger import debug_log


class DynamicEventSystem:
    EVENT_INTERVAL = 180.0     # sim seconds between events
    JITTER = 60.0              # +- randomization per interval
    BOOM_CLUSTER = 3           # nodes per discovered deposit
    BOOM_RICHNESS = 2.0        # x the normal node amount
    MIN_CASTLE_DISTANCE = 400  # events never pop inside a base
    PLACEMENT_TRIES = 40

    EVENTS = ("boom_gold", "boom_wood", "bumper_harvest")

    def __init__(self, game):
        self.game = game
        self._timer = self.EVENT_INTERVAL

    def update(self, delta_time):
        if "random_events" not in getattr(self.game, "mutators", ()):
            return
        self._timer -= delta_time
        if self._timer > 0:
            return
        self._timer = self.EVENT_INTERVAL + random.uniform(-self.JITTER, self.JITTER)
        self.trigger(random.choice(self.EVENTS))

    def trigger(self, event):
        if event == "bumper_harvest":
            self._bumper_harvest()
        elif event.startswith("boom_"):
            self._resource_boom(event.split("_", 1)[1])

    # --- Events -------------------------------------------------------------

    def _bumper_harvest(self):
        farms = [b for b in self.game.buildings if b.name == "farm" and b.hp > 0]
        for farm in farms:
            farm.food_timer = FARM_FOOD_INTERVAL  # tick fires next frame
        if farms:
            self._announce("Bumper harvest! Farms yield extra food.", None)
            debug_log.log(f"Event: bumper harvest ({len(farms)} farms)", "GENERAL")

    def _resource_boom(self, resource_name):
        spot = self._find_open_spot()
        if spot is None:
            debug_log.log(f"Event: no open ground for a {resource_name} boom", "GENERAL")
            return
        from entities import Resource

        template = self.game.game_data["resources"].get(resource_name)
        if template is None:
            return
        x, y = spot
        offsets = [(0, 0), (56, 24), (-40, 48)][: self.BOOM_CLUSTER]
        for dx, dy in offsets:
            node = Resource(name=template.name, sprite=template.sprite,
                            radius=template.radius)
            node.x, node.y = x + dx, y + dy
            node.amount_remaining = int(node.amount_remaining * self.BOOM_RICHNESS)
            self.game.resources.append(node)
            self.game.pathfinder.notify_blocker_added(node)
        self._announce(f"A rich {resource_name} deposit was discovered!", (x, y))
        debug_log.log(f"Event: {resource_name} boom at ({x:.0f}, {y:.0f})", "GENERAL")

    # --- Helpers ------------------------------------------------------------

    def _find_open_spot(self):
        game_map = self.game.game_map
        map_w = game_map.width * TILE_WIDTH
        map_h = game_map.height * TILE_HEIGHT
        castles = [b for b in self.game.buildings if b.name == "castle" and b.hp > 0]
        collision = getattr(self.game, "collision_system", None)
        for _ in range(self.PLACEMENT_TRIES):
            x = random.uniform(100, map_w - 100)
            y = random.uniform(100, map_h - 100)
            grid_pos = game_map.world_to_grid(x, y)
            if not grid_pos:
                continue
            col, row = grid_pos
            if game_map.grid[row][col] not in ("grass", "plains", "dirt"):
                continue
            if any(math.hypot(x - c.x, y - c.y) < self.MIN_CASTLE_DISTANCE for c in castles):
                continue
            if collision is not None and any(
                math.hypot(x - obj.x, y - obj.y) < 80 + obj.radius
                for obj in collision.query_nearby_static(x, y, 160)
            ):
                continue
            return (x, y)
        return None

    def _announce(self, text, world_pos):
        ui = getattr(self.game, "ui_manager", None)
        if ui is not None:
            ui.add_alert(text, world_pos)
