"""Cut a flat generated background off an icon/glyph, leaving true alpha.

Image generators routinely ignore "transparent background" and hand back an
opaque canvas with a painted backdrop (measured 2026-07-17: 3 of 5 cost glyphs
came back 1254x1254 fully opaque on white). This is the fix-up step, in the
spirit of the rest of the sprite pipeline.

Safety: the background is found by flood-filling INWARD FROM THE BORDER over
near-background-colored pixels, so light detail enclosed by the art's outline
is never touched -- the stone glyph's near-white top face survives, because the
glyph's thick dark outline seals it off from the border. A naive "erase every
near-white pixel" would punch a hole straight through it.

    python tools/cutout_glyph_background.py assets/ui/Glyphs/gold_glyph.png
    python tools/cutout_glyph_background.py --dry-run --size 1024 <files>

Overwrites in place unless --out-dir is given. Run --dry-run first.
"""
from __future__ import annotations

import argparse
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image


def find_border_background(near_bg: np.ndarray) -> np.ndarray:
    """Flood fill inward from every border pixel over the near_bg mask.

    Pure-Python BFS over flat lists: per-pixel numpy indexing would be ~100x
    slower here, and this runs over ~1.5M pixels.
    """
    height, width = near_bg.shape
    flat = near_bg.ravel().tolist()
    seen = bytearray(height * width)
    queue: deque[int] = deque()

    def seed(index: int) -> None:
        if flat[index] and not seen[index]:
            seen[index] = 1
            queue.append(index)

    for x in range(width):
        seed(x)                                  # top row
        seed((height - 1) * width + x)           # bottom row
    for y in range(height):
        seed(y * width)                          # left column
        seed(y * width + width - 1)              # right column

    while queue:
        index = queue.popleft()
        y, x = divmod(index, width)
        if x > 0:
            seed(index - 1)
        if x < width - 1:
            seed(index + 1)
        if y > 0:
            seed(index - width)
        if y < height - 1:
            seed(index + width)

    return np.frombuffer(bytes(seen), dtype=np.uint8).reshape(height, width).astype(bool)


def normalize_padding(img: Image.Image, fill: float) -> Image.Image:
    """Re-pad so the art occupies `fill` of the canvas on its longest axis.

    The glyphs sit side by side on one cost row, so inconsistent generated
    padding would render them at visibly different sizes.
    """
    bbox = img.getchannel("A").getbbox()
    if not bbox:
        return img
    art = img.crop(bbox)
    side = max(img.size)
    target = max(1, int(round(side * fill)))
    scale = target / max(art.size)
    art = art.resize((max(1, round(art.width * scale)),
                      max(1, round(art.height * scale))), Image.LANCZOS)
    out = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    out.paste(art, ((side - art.width) // 2, (side - art.height) // 2))
    return out


def coverage(img: Image.Image) -> str:
    bbox = img.getchannel("A").getbbox()
    if not bbox:
        return "empty"
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    return f"bbox {w}x{h} = {max(w, h) / max(img.size) * 100:.0f}% of canvas"


def process(path: Path, out_path: Path, args) -> bool:
    img = Image.open(path).convert("RGBA")
    arr = np.asarray(img).copy()
    alpha = arr[:, :, 3]

    if alpha.min() < 255:
        clear = (alpha == 0).mean() * 100
        print(f"  {path.name}: already has alpha ({clear:.0f}% transparent) - "
              f"skipping cutout, {coverage(img)}")
        cut = img
    else:
        corner = tuple(int(c) for c in arr[0, 0, :3])
        rgb = arr[:, :, :3].astype(np.int16)
        distance = np.abs(rgb - np.array(corner, dtype=np.int16)).max(axis=2)
        near_bg = distance <= args.tolerance

        background = find_border_background(near_bg)
        removed = background.mean() * 100
        if removed < 1.0:
            print(f"  {path.name}: no border background found near {corner} "
                  f"(tolerance {args.tolerance}) - left alone")
            return False
        arr[background, 3] = 0
        cut = Image.fromarray(arr, "RGBA")
        print(f"  {path.name}: cut {removed:.0f}% background (bg color {corner}), "
              f"{coverage(cut)}")

    if args.normalize:
        cut = normalize_padding(cut, args.fill)
        print(f"    normalized -> {coverage(cut)}")
    if args.size and cut.size != (args.size, args.size):
        print(f"    resized {cut.width}x{cut.height} -> {args.size}x{args.size}")
        cut = cut.resize((args.size, args.size), Image.LANCZOS)

    if args.dry_run:
        return True
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cut.save(out_path)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("images", nargs="+")
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--tolerance", type=int, default=18,
                        help="Max per-channel distance from the corner color to "
                             "count as background (default 18).")
    parser.add_argument("--size", type=int, default=None,
                        help="Resize the result to SIZExSIZE.")
    parser.add_argument("--normalize", action="store_true",
                        help="Re-pad so the art fills --fill of the canvas.")
    parser.add_argument("--fill", type=float, default=0.90,
                        help="Target fill fraction for --normalize (default 0.90).")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.out_dir) if args.out_dir else None
    for text in args.images:
        path = Path(text)
        if not path.exists():
            print(f"  {path}: missing")
            continue
        process(path, (out_dir / path.name) if out_dir else path, args)
    if args.dry_run:
        print("\n(dry run - nothing written)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
