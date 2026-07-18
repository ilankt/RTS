"""Impassable mountain prop (§11.2 — props, not terrain).

Follows the Fountain pattern exactly: neutral, indestructible, blocks
navigation and placement, drawn once explored. Radius varies (mountains
can be huge); the sprite footprint scales with it. Placement ridges the
high ground the old stone/mountain TILES used to mark — see
game_state._place_mountains.
"""
from entities.game_object import GameObject


class Mountain(GameObject):
    def __init__(self, x, y, radius=80):
        footprint_tiles = max(3, int(round(radius / 26)))
        super().__init__(
            name="mountain",
            size=[footprint_tiles, footprint_tiles],
            hp=1,  # unused — invulnerable; kept for duck-typed hp reads
            sprite=None,  # drop-in art via the renderer (Props/Mountain.png)
            x=x,
            y=y,
            radius=radius,
            player=None,
        )
        self.invulnerable = True
