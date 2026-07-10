"""Re-anchor baked sprite sheets so frames stop 'wiggling' during animation.

AI-generated frames (ChatGPT/Gemini) place the character at a slightly
different spot inside each frame, so cycling them makes the unit slide or
dance instead of animating in place. This tool re-registers every frame of an
already-baked NxFRAME sheet to a common anchor:

  * Horizontal: register each frame to the animation's MEAN silhouette by the
    integer shift that maximises alpha overlap. Overlap is dominated by the big
    body/cart mass, so thin extensions (a thrusting spear, an extending ram
    log) barely move it -- the torso stays locked while the weapon extends.
  * Vertical: align each frame's feet (lowest alpha row) to a common baseline
    so units stay planted on the ground (no hovering / bobbing).

Frames are only translated (never rescaled), so art is untouched -- only its
position inside the 192px cell changes. Run against a --out dir first and
preview with tools/preview_sprite_animations.py before overwriting assets.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image

FRAME = 192
ALPHA_THRESH = 10


def split_frames(sheet: np.ndarray, frame_size: int) -> list[np.ndarray]:
    h, w = sheet.shape[:2]
    if h != frame_size or w % frame_size != 0:
        raise ValueError(
            f"expected a {frame_size}px-high sheet with width divisible by "
            f"{frame_size}; got {w}x{h}"
        )
    return [sheet[:, i * frame_size:(i + 1) * frame_size, :].copy()
            for i in range(w // frame_size)]


def translate(a: np.ndarray, dx: int, dy: int) -> np.ndarray:
    """Shift an array by (dx, dy) pixels, filling exposed area with zeros."""
    h, w = a.shape[:2]
    out = np.zeros_like(a)
    sx0, sx1 = max(0, -dx), min(w, w - dx)
    sy0, sy1 = max(0, -dy), min(h, h - dy)
    if sx0 >= sx1 or sy0 >= sy1:
        return out
    dx0, dy0 = max(0, dx), max(0, dy)
    out[dy0:dy0 + (sy1 - sy0), dx0:dx0 + (sx1 - sx0)] = a[sy0:sy1, sx0:sx1]
    return out


def mask_of(frame: np.ndarray) -> np.ndarray:
    return (frame[:, :, 3] > ALPHA_THRESH).astype(np.float32)


def bottom_row(mask: np.ndarray) -> int | None:
    rows = np.nonzero(mask.any(axis=1))[0]
    return int(rows.max()) if len(rows) else None


def weighted_cx(mask: np.ndarray) -> float:
    xs = np.nonzero(mask.any(axis=0))[0]
    if len(xs) == 0:
        return FRAME / 2.0
    col_mass = mask.sum(axis=0)
    return float((np.arange(mask.shape[1]) * col_mass).sum() / col_mass.sum())


def content_bbox(mask: np.ndarray):
    xs = np.nonzero(mask.any(axis=0))[0]
    ys = np.nonzero(mask.any(axis=1))[0]
    if len(xs) == 0:
        return None
    return int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())


def clamp_shift(mask: np.ndarray, dx: int, dy: int) -> tuple[int, int]:
    """Cap a shift so no content leaves the frame (weapon-tip safety)."""
    box = content_bbox(mask)
    if box is None:
        return 0, 0
    left, right, top, bottom = box
    h, w = mask.shape[:2]
    dx = max(-left, min(w - 1 - right, dx))
    dy = max(-top, min(h - 1 - bottom, dy))
    return dx, dy


def register_x_to_mean(masks: list[np.ndarray], window: int, iters: int) -> list[int]:
    """Integer x-shift per frame that best overlaps the (iterated) mean silhouette."""
    n = len(masks)
    shifts = [0] * n
    offsets = range(-window, window + 1)
    for _ in range(iters):
        mean = np.mean([translate(m, sx, 0) for m, sx in zip(masks, shifts)], axis=0)
        for i, m in enumerate(masks):
            scores = [float((translate(m, dx, 0) * mean).sum()) for dx in offsets]
            shifts[i] = list(offsets)[int(np.argmax(scores))]
        avg = int(round(sum(shifts) / n))
        shifts = [s - avg for s in shifts]  # keep the sheet centred, don't let it drift
    return shifts


def reanchor_sheet(
    sheet: np.ndarray,
    frame_size: int,
    window: int,
    iters: int,
    target_cx: float,
    do_plant: bool,
    baseline: int | None,
) -> tuple[np.ndarray, dict]:
    frames = split_frames(sheet, frame_size)
    masks = [mask_of(f) for f in frames]
    n = len(frames)

    sx = register_x_to_mean(masks, window, iters)

    # Uniform nudge so the aligned body core sits at the frame centre (target_cx).
    aligned_mean = np.mean([translate(m, s, 0) for m, s in zip(masks, sx)], axis=0)
    core_cx = weighted_cx(aligned_mean)
    sx = [s + int(round(target_cx - core_cx)) for s in sx]

    # Vertical: plant every frame's feet on a shared baseline.
    sy = [0] * n
    if do_plant:
        bottoms = [bottom_row(m) for m in masks]
        valid = [b for b in bottoms if b is not None]
        base = baseline if baseline is not None else int(round(np.median(valid)))
        sy = [(base - b) if b is not None else 0 for b in bottoms]

    # Never let a shift push a weapon tip off the frame: clamp to the content
    # box. Where clamping bites (peak-thrust frames) the body lunges a few px
    # instead of clipping the blade -- which reads as a natural strike.
    desired_x = list(sx)
    residual = [0] * n
    out = np.zeros_like(sheet)
    lost = 0
    for i, frame in enumerate(frames):
        cx, cy = clamp_shift(masks[i], sx[i], sy[i])
        residual[i] = desired_x[i] - cx
        sx[i], sy[i] = cx, cy
        shifted = translate(frame, cx, cy)
        lost += int(masks[i].sum() - (shifted[:, :, 3] > ALPHA_THRESH).sum())
        out[:, i * frame_size:(i + 1) * frame_size, :] = shifted

    info = {"frames": n, "shift_x": sx, "shift_y": sy,
            "lost_px": max(0, lost), "residual_x": residual}
    return out, info


def process(path: Path, out_path: Path, args) -> None:
    sheet = np.asarray(Image.open(path).convert("RGBA"))
    baked, info = reanchor_sheet(
        sheet,
        frame_size=args.frame_size,
        window=args.window,
        iters=args.iters,
        target_cx=args.center_x,
        do_plant=not args.no_plant,
        baseline=args.baseline,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(baked, "RGBA").save(out_path)
    warn = f"  WARN lost {info['lost_px']}px" if info["lost_px"] else ""
    res = info["residual_x"]
    res_note = f"  lunge={res}" if any(res) else ""
    print(f"{path.name:24s} {info['frames']}f  dx={info['shift_x']}  "
          f"dy={info['shift_y']}{res_note}{warn}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sheets", nargs="+", help="Sprite sheet PNGs to re-anchor.")
    parser.add_argument("--out-dir", default=None,
                        help="Write here instead of overwriting in place.")
    parser.add_argument("--frame-size", type=int, default=FRAME)
    parser.add_argument("--window", type=int, default=30,
                        help="Max horizontal search radius in px.")
    parser.add_argument("--iters", type=int, default=4)
    parser.add_argument("--center-x", type=float, default=FRAME / 2.0,
                        help="Frame-x the body core is nudged onto.")
    parser.add_argument("--no-plant", action="store_true",
                        help="Skip vertical feet-baseline alignment.")
    parser.add_argument("--baseline", type=int, default=None,
                        help="Force a specific feet baseline row (default: median).")
    args = parser.parse_args()

    out_dir = Path(args.out_dir) if args.out_dir else None
    for sheet_text in args.sheets:
        path = Path(sheet_text)
        out_path = (out_dir / path.name) if out_dir else path
        process(path, out_path, args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
