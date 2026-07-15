"""Healing fountain — neutral map objective (§8.9 depth round 3).

WC3-style: any unit standing near it regenerates. Both sides' wounded want
it, which makes the map center contested ground without any extra
win-condition plumbing. Indestructible, blocks movement, owned by no one.
"""
from entities.game_object import GameObject


class Fountain(GameObject):
    def __init__(self, x, y):
        super().__init__(
            name="fountain",
            size=[3, 3],  # doubled 2026-07-14 (user request) — a landmark
            hp=1,  # unused — invulnerable; kept for duck-typed hp reads
            sprite=None,  # drop-in art via the renderer (Fountain.png)
            x=x,
            y=y,
            radius=70,
            player=None,
        )
        self.invulnerable = True
