"""Build the simplified 6-tile placeholder sheet (§11.1 roster redesign)
from the legacy 12-tile sheet, until the hand-painted set lands.

New sheet: 3x2 grid of 128x112 hexes -> 384x224.
  row 0: grass, desert, swamp        row 1: dirt, water_shallow, water_deep
Sources: grass/desert/dirt copied from the legacy sheet; swamp = legacy
forest hue-shifted murky; water_deep = legacy water darkened.

Usage: python tools/build_placeholder_tileset.py  (reads the LEGACY sheet
from git history if the working sheet is already 6-tile — pass a path to
override). Writes assets/tiles/tileset.png + tileset.json.
"""
import json
import os
import subprocess
import sys

from PIL import Image, ImageEnhance

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHEET = os.path.join(ROOT, "assets", "tiles", "tileset.png")
MANIFEST = os.path.join(ROOT, "assets", "tiles", "tileset.json")
TILE_W, TILE_H = 128, 112

LEGACY_LOCS = {  # name -> (col, row) in the legacy 3x4 sheet
    "desert": (0, 0), "grass": (2, 0), "dirt": (1, 1),
    "forest": (2, 2), "water": (2, 3),
}


def load_legacy_sheet():
    """The 12-tile sheet: from disk if still legacy-sized, else from git."""
    if os.path.exists(SHEET):
        img = Image.open(SHEET)
        if img.size == (384, 448):
            return img.convert("RGBA")
    blob = subprocess.run(
        ["git", "-C", ROOT, "show", "HEAD:assets/tiles/tileset.png"],
        capture_output=True, check=True).stdout
    from io import BytesIO
    img = Image.open(BytesIO(blob)).convert("RGBA")
    assert img.size == (384, 448), f"unexpected legacy sheet size {img.size}"
    return img


def cut(sheet, col, row):
    return sheet.crop((col * TILE_W, row * TILE_H,
                       (col + 1) * TILE_W, (row + 1) * TILE_H))


def make_swamp(forest_tile):
    """Murky bog: hue toward brown-green, darker, less saturated."""
    r, g, b, a = forest_tile.split()
    # Push toward muddy brown-green by remixing channels
    murky = Image.merge("RGBA", (
        g.point(lambda v: int(v * 0.55 + 25)),
        g.point(lambda v: int(v * 0.72 + 10)),
        b.point(lambda v: int(v * 0.45 + 8)),
        a,
    ))
    murky = ImageEnhance.Color(murky).enhance(0.75)
    return ImageEnhance.Brightness(murky).enhance(0.85)


def make_deep_water(water_tile):
    """Deep water: darker, bluer, calmer."""
    deep = ImageEnhance.Brightness(water_tile).enhance(0.55)
    r, g, b, a = deep.split()
    return Image.merge("RGBA", (
        r.point(lambda v: int(v * 0.75)),
        g.point(lambda v: int(v * 0.85)),
        b.point(lambda v: min(255, int(v * 1.1 + 10))),
        a,
    ))


def main():
    legacy = load_legacy_sheet()
    tiles = {
        "grass": cut(legacy, *LEGACY_LOCS["grass"]),
        "desert": cut(legacy, *LEGACY_LOCS["desert"]),
        "swamp": make_swamp(cut(legacy, *LEGACY_LOCS["forest"])),
        "dirt": cut(legacy, *LEGACY_LOCS["dirt"]),
        "water_shallow": cut(legacy, *LEGACY_LOCS["water"]),
        "water_deep": make_deep_water(cut(legacy, *LEGACY_LOCS["water"])),
    }

    layout = [["grass", "desert", "swamp"],
              ["dirt", "water_shallow", "water_deep"]]
    sheet = Image.new("RGBA", (TILE_W * 3, TILE_H * 2), (0, 0, 0, 0))
    manifest = {"tile_width": TILE_W, "tile_height": TILE_H, "tiles": []}
    for row, names in enumerate(layout):
        for col, name in enumerate(names):
            sheet.paste(tiles[name], (col * TILE_W, row * TILE_H))
            manifest["tiles"].append({"name": name, "location": [col, row]})

    sheet.save(SHEET)
    with open(MANIFEST, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"wrote {SHEET} ({sheet.size[0]}x{sheet.size[1]}) and tileset.json")


if __name__ == "__main__":
    sys.exit(main())
