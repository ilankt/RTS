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
            size=[1.5, 1.5],
            hp=1,  # unused — invulnerable; kept for duck-typed hp reads
            sprite=None,  # procedural visual in the renderer until art exists
            x=x,
            y=y,
            radius=40,
            player=None,
        )
        self.invulnerable = True
