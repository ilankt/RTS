"""Normalize a generated alpha sprite sheet to exact game dimensions."""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


def alpha_bbox(image: Image.Image):
    alpha = image.getchannel("A")
    return alpha.point(lambda p: 255 if p > 10 else 0).getbbox()


def expanded_aspect_bbox(bbox, image_size, target_aspect: float, padding: float):
    left, top, right, bottom = bbox
    width = right - left
    height = bottom - top

    pad_x = int(width * padding)
    pad_y = int(height * padding)
    left -= pad_x
    right += pad_x
    top -= pad_y
    bottom += pad_y

    width = right - left
    height = bottom - top
    aspect = width / max(1, height)

    if aspect < target_aspect:
        new_width = int(height * target_aspect)
        delta = new_width - width
        left -= delta // 2
        right += delta - delta // 2
    elif aspect > target_aspect:
        new_height = int(width / target_aspect)
        delta = new_height - height
        top -= delta // 2
        bottom += delta - delta // 2

    img_w, img_h = image_size
    crop_w = right - left
    crop_h = bottom - top
    canvas = Image.new("RGBA", (crop_w, crop_h), (0, 0, 0, 0))

    src_left = max(0, left)
    src_top = max(0, top)
    src_right = min(img_w, right)
    src_bottom = min(img_h, bottom)
    paste_x = src_left - left
    paste_y = src_top - top

    return (src_left, src_top, src_right, src_bottom), (paste_x, paste_y), canvas


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--padding", type=float, default=0.08)
    args = parser.parse_args()

    image = Image.open(args.input).convert("RGBA")
    bbox = alpha_bbox(image)
    if not bbox:
        raise SystemExit(f"No non-transparent pixels found in {args.input}")

    target_aspect = args.width / args.height
    crop_rect, paste_pos, canvas = expanded_aspect_bbox(
        bbox,
        image.size,
        target_aspect,
        args.padding,
    )
    canvas.alpha_composite(image.crop(crop_rect), paste_pos)
    normalized = canvas.resize((args.width, args.height), Image.Resampling.LANCZOS)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    normalized.save(args.out)
    print(f"wrote {args.out} {args.width}x{args.height}")


if __name__ == "__main__":
    raise SystemExit(main())
