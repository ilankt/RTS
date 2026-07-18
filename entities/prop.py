"""Generic world props (§11.2 round 2): rocks, dead trees, ruins.

One entity class + a type registry instead of a class per prop. Follows
the Mountain/Fountain pattern: neutral, indestructible; BLOCKING types
register with nav + the collision static index, decorative types are
draw-only. Placement only spawns types whose sprite file exists, so new
props ship art-first with zero code risk.
"""
import os

from entities.game_object import GameObject

PROP_SPRITE_DIR = os.path.join("assets", "sprites", "Props")

PROP_TYPES = {
    # small blocking outcrop scattered on open ground — tactical texture
    "rocks": {"file": "Rocks.png", "blocks": True, "radius": 30, "tiles": 2},
    # non-blocking swamp atmosphere
    "dead_tree": {"file": "DeadTree.png", "blocks": False, "radius": 26, "tiles": 2},
    # rare blocking landmark
    "ruins": {"file": "Ruins.png", "blocks": True, "radius": 55, "tiles": 3},
}


def prop_sprite_path(name):
    spec = PROP_TYPES.get(name)
    return os.path.join(PROP_SPRITE_DIR, spec["file"]) if spec else None


def available_prop_types():
    """Prop types whose art is on disk — placement spawns only these."""
    return {name for name in PROP_TYPES
            if os.path.exists(prop_sprite_path(name))}


class Prop(GameObject):
    def __init__(self, name, x, y):
        spec = PROP_TYPES[name]
        tiles = spec["tiles"]
        super().__init__(
            name=name,
            size=[tiles, tiles],
            hp=1,  # unused — invulnerable; kept for duck-typed hp reads
            sprite=None,  # loaded by the renderer via prop_sprite_path
            x=x,
            y=y,
            radius=spec["radius"],
            player=None,
        )
        self.invulnerable = True
        self.blocks = spec["blocks"]
