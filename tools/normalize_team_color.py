"""Snap a unit's 'team-blue' pixels onto the two shades the tinter keys on.

Units are recoloured to the player's colour by managers/sprite_manager.tint_surface_blue,
which only replaces pixels within +/-25 of navy (72,88,132) or teal (70,151,172).
AI-generated art often uses a blue just outside that window, so barely any of the
unit recolours. This pass detects the saturated-blue team regions (plume, shield,
tabard, barding, cloth) and snaps each to the nearer key shade, so the existing
tinter catches them. Grey steel and non-blue pixels are left untouched.

Run with --dry-run first; overwrites in place unless --out-dir is given.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image

# Must match managers/sprite_manager.tint_surface_blue.
KEY_NAVY = np.array([72, 88, 132])
KEY_TEAL = np.array([70, 151, 172])
ALPHA_THRESH = 10


def team_blue_mask(rgb: np.ndarray, alpha: np.ndarray, gap: int, min_b: int) -> np.ndarray:
    """Saturated blue where blue clearly dominates red (excludes grey steel)."""
    r = rgb[..., 0].astype(int)
    g = rgb[..., 1].astype(int)
    b = rgb[..., 2].astype(int)
    return (alpha > ALPHA_THRESH) & (b >= min_b) & (b - r >= gap) & (b >= g - 30)


def snap_to_key(sheet: np.ndarray, gap: int, min_b: int) -> tuple[np.ndarray, int]:
    rgb = sheet[..., :3]
    alpha = sheet[..., 3]
    mask = team_blue_mask(rgb, alpha, gap, min_b)
    if not mask.any():
        return sheet, 0
    out = sheet.copy()
    px = rgb[mask].astype(int)
    d_navy = np.abs(px - KEY_NAVY).sum(axis=1)
    d_teal = np.abs(px - KEY_TEAL).sum(axis=1)
    choose_teal = d_teal < d_navy
    snapped = np.where(choose_teal[:, None], KEY_TEAL, KEY_NAVY).astype(np.uint8)
    out_rgb = out[..., :3]
    out_rgb[mask] = snapped
    return out, int(mask.sum())


def process(path: Path, out_path: Path, args) -> None:
    sheet = np.asarray(Image.open(path).convert("RGBA")).copy()
    vis = int((sheet[..., 3] > ALPHA_THRESH).sum())
    snapped, changed = snap_to_key(sheet, args.gap, args.min_b)
    pct = 100 * changed / max(1, vis)
    print(f"{path.name:24s} snapped {changed:6d}px ({pct:4.1f}% of body) to team key")
    if not args.dry_run:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(snapped, "RGBA").save(out_path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sheets", nargs="+")
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--gap", type=int, default=35,
                        help="Min (blue - red) for a pixel to count as team-blue.")
    parser.add_argument("--min-b", type=int, default=80,
                        help="Min blue channel for a pixel to count as team-blue.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.out_dir) if args.out_dir else None
    for text in args.sheets:
        path = Path(text)
        out_path = (out_dir / path.name) if out_dir else path
        process(path, out_path, args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
