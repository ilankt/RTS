"""Build assets/tiles/tileset.png from six AI-generated SEAMLESS textures.

The generator is never asked for transparency or hexagon shapes — both are
things image models reliably get wrong. It paints six flat square terrain
textures; THIS tool applies the pixel-exact flat-top hex mask the renderer
interlocks, and cuts several wrap-around crops per texture so every terrain
gets real variants (replacing the flip-derived ones) from a single image.

Input:   assets/tiles/source_textures/<name>.png
         for: grass, desert, swamp, dirt, water_shallow, water_deep
         (square, >= 512 px, seamless/tileable — see the prompts in
         REQUIRED_VISUAL_ASSET_PROMPTS.md)
Output:  assets/tiles/tileset.png + assets/tiles/tileset.json
         3 columns x (2 base + variant) rows; tileset.json records the
         extra crops per tile as "variants": [[col,row], ...], which
         world/map.py already consumes (sheet variants override the
         derived flips automatically).

    python tools/build_tileset_from_textures.py            # build
    python tools/build_tileset_from_textures.py --variants 4

Missing textures fall back to the current sheet's tile for that name, so
the set can be delivered incrementally.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE_DIR = os.path.join(ROOT, "assets", "tiles", "source_textures")
SHEET = os.path.join(ROOT, "assets", "tiles", "tileset.png")
MANIFEST = os.path.join(ROOT, "assets", "tiles", "tileset.json")

TILE_W, TILE_H = 128, 112
COLS = 3
# Base layout must match what world generation expects (tileset.json rules)
BASE_LAYOUT = [["grass", "desert", "swamp"],
               ["dirt", "water_shallow", "water_deep"]]
# The texture is scaled so roughly this many hex-widths span it — controls
# how "zoomed" the painted detail appears on a tile.
HEXES_ACROSS_TEXTURE = 3.5
# Deterministic wrap-around crop origins (fractions of the working texture);
# spread out so variants share no obvious features.
CROP_ORIGINS = [(0.00, 0.00), (0.53, 0.17), (0.21, 0.61), (0.68, 0.74),
                (0.37, 0.33), (0.83, 0.49)]


def hex_mask():
    from PIL import ImageDraw

    mask = Image.new("L", (TILE_W, TILE_H), 0)
    ImageDraw.Draw(mask).polygon(
        [(TILE_W // 4, 0), (TILE_W * 3 // 4, 0), (TILE_W - 1, TILE_H // 2),
         (TILE_W * 3 // 4, TILE_H - 1), (TILE_W // 4, TILE_H - 1), (0, TILE_H // 2)],
        fill=255)
    return mask


def wrap_crop(texture, ox, oy, w, h):
    """Crop (w, h) at (ox, oy) treating the texture as an endless tile."""
    tw, th = texture.size
    canvas = Image.new("RGBA", (w, h))
    for dy in (0, th):
        for dx in (0, tw):
            canvas.paste(texture, (dx - ox % tw, dy - oy % th))
    return canvas


def cut_variants(texture, count, mask):
    working_w = int(TILE_W * HEXES_ACROSS_TEXTURE)
    scale = working_w / texture.width
    working = texture.convert("RGBA").resize(
        (working_w, max(TILE_H, int(texture.height * scale))), Image.LANCZOS)
    tiles = []
    for ox_f, oy_f in CROP_ORIGINS[:count]:
        crop = wrap_crop(working, int(ox_f * working.width),
                         int(oy_f * working.height), TILE_W, TILE_H)
        tile = Image.new("RGBA", (TILE_W, TILE_H), (0, 0, 0, 0))
        tile.paste(crop, (0, 0), mask)
        tiles.append(tile)
    return tiles


def fallback_tile(name):
    """Reuse the current sheet's tile when a source texture is missing."""
    if not (os.path.exists(SHEET) and os.path.exists(MANIFEST)):
        return None
    with open(MANIFEST) as f:
        manifest = json.load(f)
    entry = next((t for t in manifest["tiles"] if t["name"] == name), None)
    if entry is None:
        return None
    sheet = Image.open(SHEET).convert("RGBA")
    col, row = entry["location"]
    return sheet.crop((col * TILE_W, row * TILE_H,
                       (col + 1) * TILE_W, (row + 1) * TILE_H))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--variants", type=int, default=4,
                        help="crops per terrain (1-%d)" % len(CROP_ORIGINS))
    args = parser.parse_args()
    count = max(1, min(args.variants, len(CROP_ORIGINS)))
    mask = hex_mask()

    names = [n for row in BASE_LAYOUT for n in row]
    tiles_by_name = {}
    for name in names:
        source_path = os.path.join(SOURCE_DIR, name + ".png")
        if os.path.exists(source_path):
            tiles_by_name[name] = cut_variants(Image.open(source_path), count, mask)
            print(f"{name}: {count} variants cut from source texture")
        else:
            fallback = fallback_tile(name)
            if fallback is None:
                print(f"ERROR: no source texture and no fallback for '{name}'")
                return 1
            tiles_by_name[name] = [fallback]
            print(f"{name}: source texture missing -> kept current tile")

    # Sheet layout: base 3x2 exactly as today, variant crops appended below
    cells = {}   # name -> [(col,row), ...]
    for row, row_names in enumerate(BASE_LAYOUT):
        for col, name in enumerate(row_names):
            cells[name] = [(col, row)]
    next_slot = len(names)
    for name in names:
        for _ in tiles_by_name[name][1:]:
            cells[name].append((next_slot % COLS, next_slot // COLS))
            next_slot += 1

    rows = (next_slot + COLS - 1) // COLS
    sheet = Image.new("RGBA", (COLS * TILE_W, rows * TILE_H), (0, 0, 0, 0))
    manifest = {"tile_width": TILE_W, "tile_height": TILE_H, "tiles": []}
    for name in names:
        for tile, (col, row) in zip(tiles_by_name[name], cells[name]):
            sheet.paste(tile, (col * TILE_W, row * TILE_H))
        entry = {"name": name, "location": list(cells[name][0])}
        if len(cells[name]) > 1:
            entry["variants"] = [list(loc) for loc in cells[name][1:]]
        manifest["tiles"].append(entry)

    sheet.save(SHEET)
    with open(MANIFEST, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"wrote {SHEET} ({sheet.size[0]}x{sheet.size[1]}, {rows} rows) "
          f"and tileset.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
