"""Peel magenta-contaminated edge pixels off a keyed-out sprite.

The magenta-background cutout (cutout_glyph_background.py) keeps hard
alpha, but anti-aliased silhouette pixels retain a baked pink tint that
reads as fringe specks in-game (found on the first mountain: ~2,800 px).
This peels up to --rings rings of boundary pixels whose color is
magenta-dominant. Safe on clean sprites (removes nothing).

    python tools/defringe_magenta.py assets/sprites/Props/Mountain.png [...]
"""
import argparse
import sys

import numpy as np
from PIL import Image


def defringe(path, rings=3):
    img = Image.open(path).convert("RGBA")
    a = np.array(img).astype(int)
    removed = 0
    for _ in range(rings):
        alpha = a[:, :, 3] > 0
        pad = np.pad(alpha, 1, constant_values=False)
        boundary = alpha & ~(pad[:-2, 1:-1] & pad[2:, 1:-1]
                             & pad[1:-1, :-2] & pad[1:-1, 2:])
        r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
        magenta = (r > 120) & (b > 120) & (g < (r + b) // 4)
        kill = boundary & magenta
        if not kill.any():
            break
        a[kill, 3] = 0
        removed += int(kill.sum())
    if removed:
        Image.fromarray(a.astype("uint8")).save(path)
    print(f"{path}: removed {removed} fringe px")
    return removed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+")
    parser.add_argument("--rings", type=int, default=3)
    args = parser.parse_args()
    for path in args.files:
        defringe(path, args.rings)
    return 0


if __name__ == "__main__":
    sys.exit(main())
