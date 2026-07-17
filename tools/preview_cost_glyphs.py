"""Verify §8.2.2 HUD cost glyphs: alpha, contrast, and the 14 px read.

The command card draws these at ~14 px onto dark tiles. Judging them at 1024
is how mud ships: measured 2026-07-17, today's framed `assets/ui/*_icon.png`
set is fully opaque and blurs gold/lumber into identical warm smears at tile
size. This checks what the player actually sees.

    python tools/preview_cost_glyphs.py            # check + write a preview
    python tools/preview_cost_glyphs.py --old      # same, on the legacy icons

Exit code is nonzero if any glyph fails, so it can gate a batch.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from PIL import Image, ImageStat
except ImportError:  # pragma: no cover - tooling-only dependency
    print("Pillow is required: pip install pillow")
    raise SystemExit(2)

ROOT = Path(__file__).resolve().parent.parent

# Real command-card surfaces (ui/components/command_card.py:_draw_tile,
# :draw_tooltip). Every one is dark — that is what drives the palette.
SURFACES = {
    "tile enabled": (42, 52, 42),
    "tile locked": (45, 42, 32),
    "tile cant-afford": (50, 38, 38),
    "tile hovered": (67, 77, 67),
    "tooltip": (10, 10, 14),
}

GLYPHS = ["gold", "wood", "stone", "food", "time"]
LEGACY = {
    "gold": "assets/ui/gold_icon.png",
    "wood": "assets/ui/lumber_icon.png",
    "stone": "assets/ui/stone_icon.png",
    "food": "assets/ui/food_icon.png",
}

TILE_GLYPH_PX = 14      # size the cost row blits at
MIN_CONTRAST = 3.0      # of the glyph's mean lit color vs the worst surface
CELL = 120              # preview cell size


def _relative_luminance(rgb) -> float:
    channels = []
    for value in rgb[:3]:
        value /= 255.0
        channels.append(value / 12.92 if value <= 0.03928
                        else ((value + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast(fg, bg) -> float:
    high, low = sorted((_relative_luminance(fg), _relative_luminance(bg)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def mean_opaque_color(img: Image.Image):
    """Average color of the glyph's own pixels, ignoring transparency."""
    mask = img.getchannel("A").point(lambda a: 255 if a > 128 else 0)
    if not mask.getbbox():
        return None
    stat = ImageStat.Stat(img.convert("RGB"), mask)
    return tuple(int(channel) for channel in stat.mean)


def check(name: str, path: Path, failures: list) -> Image.Image | None:
    if not path.exists():
        failures.append(f"{name}: missing {path.relative_to(ROOT)}")
        return None
    img = Image.open(path).convert("RGBA")

    if img.size != (1024, 1024):
        failures.append(f"{name}: expected 1024x1024, got {img.width}x{img.height}")

    alpha = img.getchannel("A")
    alpha_min, _ = alpha.getextrema()
    transparent = alpha.histogram()[0] / float(img.width * img.height)
    if alpha_min == 255:
        failures.append(
            f"{name}: fully opaque (alpha_min=255) — the generator painted a "
            f"background instead of leaving alpha 0; it will render as a solid square")
    elif transparent < 0.20:
        failures.append(
            f"{name}: only {transparent*100:.0f}% transparent — expected a bare "
            f"cut-out with a margin, not a filled plate")

    mean = mean_opaque_color(img)
    if mean is not None:
        worst_surface, worst = min(
            ((label, contrast(mean, bg)) for label, bg in SURFACES.items()),
            key=lambda item: item[1],
        )
        if worst < MIN_CONTRAST:
            failures.append(
                f"{name}: mean color {mean} scores {worst:.2f} contrast on "
                f"'{worst_surface}' (need >={MIN_CONTRAST}) — too dark for the tile; "
                f"brighten the fill")
        else:
            print(f"  {name:6s} mean={str(mean):16s} worst contrast {worst:.2f} "
                  f"on {worst_surface}")
    return img


def build_preview(images: dict, out_path: Path) -> None:
    """Rows = real surfaces, cols = glyphs, each drawn at 14 px then
    nearest-upscaled so the actual read is visible."""
    names = [n for n in GLYPHS if images.get(n) is not None]
    if not names:
        return
    sheet = Image.new("RGB", (CELL * len(names), CELL * len(SURFACES)), (0, 0, 0))
    for row, (_, bg) in enumerate(SURFACES.items()):
        for col, name in enumerate(names):
            tiny = images[name].resize((TILE_GLYPH_PX, TILE_GLYPH_PX), Image.LANCZOS)
            zoomed = tiny.resize((CELL, CELL), Image.NEAREST)
            plate = Image.new("RGBA", (CELL, CELL), tuple(bg) + (255,))
            plate.alpha_composite(zoomed)
            sheet.paste(plate.convert("RGB"), (col * CELL, row * CELL))
    sheet.save(out_path)
    print(f"\npreview -> {out_path}")
    print(f"  rows (top-down): {', '.join(SURFACES)}")
    print(f"  cols (left-right): {', '.join(names)}")
    print("  Each cell is the glyph at 14 px, magnified. If you cannot name the")
    print("  resource, or gold/wood/food read alike, regenerate it.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--old", action="store_true",
                        help="Check the legacy assets/ui/*_icon.png set instead.")
    parser.add_argument("--out", default=None, help="Preview PNG path.")
    args = parser.parse_args()

    paths = ({name: ROOT / rel for name, rel in LEGACY.items()} if args.old else
             {name: ROOT / "assets" / "ui" / "Glyphs" / f"{name}_glyph.png"
              for name in GLYPHS})

    print(f"checking {len(paths)} glyph(s) at {TILE_GLYPH_PX}px against "
          f"{len(SURFACES)} real surfaces")
    failures: list = []
    images = {name: check(name, path, failures) for name, path in paths.items()}

    out = Path(args.out) if args.out else ROOT / "cost_glyph_preview.png"
    build_preview(images, out)

    if failures:
        print()
        for failure in failures:
            print(f"FAIL {failure}")
        return 1
    print("\nall glyphs pass the automated checks — now LOOK at the preview")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
