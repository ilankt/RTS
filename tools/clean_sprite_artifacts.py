"""Erase floating alpha fragments (generation ghosts) from sprite sheets.

Only removes a disconnected blob when it is BOTH small and clearly isolated
from the main body (a wide transparent gap). This spares real parts that are
merely separated by a hairline gap -- e.g. a ram's spike tip at full extension.
Run with --dry-run first; overwrites in place unless --out-dir is given.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image

FRAME = 192
ALPHA_THRESH = 10


def components(mask: np.ndarray) -> list[dict]:
    h, w = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    comps = []
    for sy in range(h):
        for sx in range(w):
            if not mask[sy, sx] or seen[sy, sx]:
                continue
            stack = [(sy, sx)]
            seen[sy, sx] = True
            pts = []
            while stack:
                y, x = stack.pop()
                pts.append((y, x))
                for ny in range(max(0, y - 1), min(h, y + 2)):
                    for nx in range(max(0, x - 1), min(w, x + 2)):
                        if mask[ny, nx] and not seen[ny, nx]:
                            seen[ny, nx] = True
                            stack.append((ny, nx))
            comps.append(np.array(pts))
    comps.sort(key=len, reverse=True)
    return comps


def gap_to(main: np.ndarray, blob: np.ndarray) -> float:
    """Minimum pixel distance between a blob and the main body."""
    best = 1e9
    for by, bx in blob:
        d = np.hypot(main[:, 0] - by, main[:, 1] - bx).min()
        if d < best:
            best = d
            if best <= 1.0:
                break
    return float(best)


def clean_frame(frame: np.ndarray, gap: float, max_area: int, min_area: int):
    mask = frame[:, :, 3] > ALPHA_THRESH
    comps = components(mask)
    if not comps:
        return frame, []
    main = comps[0]
    removed = []
    out = frame.copy()
    for blob in comps[1:]:
        area = len(blob)
        if area <= min_area:
            reason = "tiny"
        elif area <= max_area and gap_to(main, blob) >= gap:
            reason = f"isolated gap={gap_to(main, blob):.0f}"
        else:
            continue
        out[blob[:, 0], blob[:, 1], 3] = 0
        removed.append((area, int(blob[:, 1].mean()), int(blob[:, 0].mean()), reason))
    return out, removed


def process(path: Path, out_path: Path, args) -> None:
    sheet = np.asarray(Image.open(path).convert("RGBA")).copy()
    n = sheet.shape[1] // FRAME
    any_removed = False
    for i in range(n):
        sl = slice(i * FRAME, (i + 1) * FRAME)
        cleaned, removed = clean_frame(sheet[:, sl, :], args.gap, args.max_area, args.min_area)
        if removed:
            any_removed = True
            for area, cx, cy, reason in removed:
                print(f"  {path.name} frame {i+1}: remove {area}px @({cx},{cy}) [{reason}]")
        if not args.dry_run:
            sheet[:, sl, :] = cleaned
    if not any_removed:
        print(f"  {path.name}: clean")
    if not args.dry_run:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(sheet, "RGBA").save(out_path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sheets", nargs="+")
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--gap", type=float, default=8.0,
                        help="Min empty-pixel gap from body to count as a floating ghost.")
    parser.add_argument("--max-area", type=int, default=400,
                        help="Never erase a blob larger than this (safety for real parts).")
    parser.add_argument("--min-area", type=int, default=20,
                        help="Blobs this small are always erased (specks).")
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
