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
    from PIL import Image
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
MIN_CONTRAST = 3.0      # a glyph pixel counts as "reads" at this contrast
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


def lit_fraction(img: Image.Image):
    """Share of the glyph's opaque pixels bright enough to clear MIN_CONTRAST,
    measured on the worst (lightest) tile surface.

    This is the honest readability proxy: a glyph reads on a dark tile because
    a meaningful part of it is bright, NOT because its *mean* is — averaging in
    the thick dark outline (and, for the drumstick, the dark meat) understates
    a glyph that plainly reads. Returns (fraction, worst_surface_label).
    """
    small = img.resize((96, 96), Image.LANCZOS)
    pixels = list(small.getdata())
    per_surface = {label: [0, 0] for label in SURFACES}  # [opaque, bright]
    for r, g, b, a in pixels:
        if a <= 128:
            continue
        for label, bg in SURFACES.items():
            per_surface[label][0] += 1
            if contrast((r, g, b), bg) >= MIN_CONTRAST:
                per_surface[label][1] += 1
    worst_label, worst_frac = min(
        ((label, (bright / opaque if opaque else 0.0))
         for label, (opaque, bright) in per_surface.items()),
        key=lambda item: item[1],
    )
    return worst_frac, worst_label


# A properly transparent glyph reads if at least this share of its body is
# bright against the worst tile. Deliberately lenient — the rendered preview
# below is the real aesthetic gate; this only catches an all-dark glyph.
MIN_LIT_FRACTION = 0.18


def check(name: str, path: Path, failures: list, warnings: list) -> Image.Image | None:
    if not path.exists():
        failures.append(f"{name}: missing {path.relative_to(ROOT)}")
        return None
    img = Image.open(path).convert("RGBA")

    if img.size != (1024, 1024):
        failures.append(f"{name}: expected 1024x1024, got {img.width}x{img.height}")

    alpha = img.getchannel("A")
    alpha_min, _ = alpha.getextrema()
    transparent = alpha.histogram()[0] / float(img.width * img.height)
    # Hard failure — the mechanical break that actually bit us: a generator
    # returning an opaque canvas with a painted backdrop renders as a square.
    if alpha_min == 255:
        failures.append(
            f"{name}: fully opaque (alpha_min=255) — the generator painted a "
            f"background instead of leaving alpha 0; it will render as a solid square")
    elif transparent < 0.20:
        failures.append(
            f"{name}: only {transparent*100:.0f}% transparent — expected a bare "
            f"cut-out with a margin, not a filled plate")

    # Readability is a WARNING, not a hard fail: the metric is a proxy and the
    # rendered preview is the real judge. Flag the all-dark case, trust the eye.
    frac, worst = lit_fraction(img)
    tag = "ok " if frac >= MIN_LIT_FRACTION else "DIM"
    print(f"  {tag} {name:6s} {frac*100:4.0f}% of body reads on '{worst}'")
    if frac < MIN_LIT_FRACTION:
        warnings.append(
            f"{name}: only {frac*100:.0f}% of the glyph is bright enough to read on "
            f"'{worst}' — likely too dark; confirm in the preview before shipping")
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
    warnings: list = []
    images = {name: check(name, path, failures, warnings)
              for name, path in paths.items()}

    out = Path(args.out) if args.out else ROOT / "cost_glyph_preview.png"
    build_preview(images, out)

    for warning in warnings:
        print(f"WARN {warning}")
    if failures:
        print()
        for failure in failures:
            print(f"FAIL {failure}")
        return 1
    print("\nno hard failures — now LOOK at the preview to make the final call")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
