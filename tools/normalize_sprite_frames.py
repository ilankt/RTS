"""Normalize generated sprite-sheet poses into exact 192px game frames."""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


def alpha_bbox(image: Image.Image):
    alpha = image.getchannel("A")
    return alpha.point(lambda p: 255 if p > 10 else 0).getbbox()


def split_equal_bands(image: Image.Image, frame_count: int) -> list[Image.Image]:
    band_width = image.width / frame_count
    bands = []
    for index in range(frame_count):
        left = round(index * band_width)
        right = round((index + 1) * band_width)
        bands.append(image.crop((left, 0, right, image.height)).convert("RGBA"))
    return bands


def expanded_bbox(bbox, size, padding: float):
    left, top, right, bottom = bbox
    width = right - left
    height = bottom - top
    pad_x = int(width * padding)
    pad_y = int(height * padding)
    left = max(0, left - pad_x)
    right = min(size[0], right + pad_x)
    top = max(0, top - pad_y)
    bottom = min(size[1], bottom + pad_y)
    return left, top, right, bottom


def remove_edge_artifacts(frame: Image.Image, edge_margin: int = 4, max_area: int = 350) -> Image.Image:
    """Remove tiny disconnected remnants that touch a frame edge."""
    alpha = frame.getchannel("A")
    width, height = frame.size
    pixels = alpha.load()
    seen = set()
    clear_pixels: list[tuple[int, int]] = []

    for y in range(height):
        for x in range(width):
            if (x, y) in seen or pixels[x, y] <= 10:
                continue

            stack = [(x, y)]
            seen.add((x, y))
            component = []
            min_x = max_x = x
            while stack:
                cx, cy = stack.pop()
                component.append((cx, cy))
                min_x = min(min_x, cx)
                max_x = max(max_x, cx)
                for nx in range(max(0, cx - 1), min(width, cx + 2)):
                    for ny in range(max(0, cy - 1), min(height, cy + 2)):
                        if (nx, ny) in seen or pixels[nx, ny] <= 10:
                            continue
                        seen.add((nx, ny))
                        stack.append((nx, ny))

            touches_edge = min_x <= edge_margin or max_x >= width - edge_margin - 1
            if touches_edge and len(component) <= max_area:
                clear_pixels.extend(component)

    if not clear_pixels:
        return frame

    cleaned = frame.copy()
    cleaned_alpha = cleaned.getchannel("A")
    cleaned_pixels = cleaned_alpha.load()
    for x, y in clear_pixels:
        cleaned_pixels[x, y] = 0
    cleaned.putalpha(cleaned_alpha)
    return cleaned


def remove_tiny_components(frame: Image.Image, max_area: int = 120) -> Image.Image:
    """Remove very small disconnected alpha components left by generation artifacts."""
    alpha = frame.getchannel("A")
    width, height = frame.size
    pixels = alpha.load()
    seen = set()
    clear_pixels: list[tuple[int, int]] = []

    for y in range(height):
        for x in range(width):
            if (x, y) in seen or pixels[x, y] <= 10:
                continue

            stack = [(x, y)]
            seen.add((x, y))
            component = []
            while stack:
                cx, cy = stack.pop()
                component.append((cx, cy))
                for nx in range(max(0, cx - 1), min(width, cx + 2)):
                    for ny in range(max(0, cy - 1), min(height, cy + 2)):
                        if (nx, ny) in seen or pixels[nx, ny] <= 10:
                            continue
                        seen.add((nx, ny))
                        stack.append((nx, ny))

            if len(component) <= max_area:
                clear_pixels.extend(component)

    if not clear_pixels:
        return frame

    cleaned = frame.copy()
    cleaned_alpha = cleaned.getchannel("A")
    cleaned_pixels = cleaned_alpha.load()
    for x, y in clear_pixels:
        cleaned_pixels[x, y] = 0
    cleaned.putalpha(cleaned_alpha)
    return cleaned


def clear_side_margins(frame: Image.Image, margin: int) -> Image.Image:
    if margin <= 0:
        return frame

    cleaned = frame.copy()
    alpha = cleaned.getchannel("A")
    pixels = alpha.load()
    width, height = frame.size
    for y in range(height):
        for x in range(margin):
            pixels[x, y] = 0
            pixels[width - x - 1, y] = 0
    cleaned.putalpha(alpha)
    return cleaned


def normalize_frames(
    image: Image.Image,
    frame_count: int,
    frame_width: int,
    frame_height: int,
    padding: float,
    bottom_padding: int,
    clear_margin: int,
) -> Image.Image:
    bands = split_equal_bands(image, frame_count)
    bboxes = [alpha_bbox(band) for band in bands]
    if any(bbox is None for bbox in bboxes):
        missing = [str(i + 1) for i, bbox in enumerate(bboxes) if bbox is None]
        raise ValueError(f"No visible pixels found in frame(s): {', '.join(missing)}")

    expanded = [
        expanded_bbox(bbox, band.size, padding)
        for bbox, band in zip(bboxes, bands)
    ]
    max_width = max(right - left for left, top, right, bottom in expanded)
    max_height = max(bottom - top for left, top, right, bottom in expanded)
    scale = min(frame_width / max_width, frame_height / max_height, 1.0)

    sheet = Image.new("RGBA", (frame_width * frame_count, frame_height), (0, 0, 0, 0))
    for index, (band, crop_box) in enumerate(zip(bands, expanded)):
        cropped = band.crop(crop_box)
        new_width = max(1, round(cropped.width * scale))
        new_height = max(1, round(cropped.height * scale))
        resized = cropped.resize((new_width, new_height), Image.Resampling.LANCZOS)

        x = index * frame_width + (frame_width - new_width) // 2
        y = frame_height - bottom_padding - new_height
        y = max(0, min(frame_height - new_height, y))
        frame = Image.new("RGBA", (frame_width, frame_height), (0, 0, 0, 0))
        frame.alpha_composite(resized, (x - index * frame_width, y))
        frame = remove_edge_artifacts(frame)
        frame = remove_tiny_components(frame)
        frame = clear_side_margins(frame, clear_margin)
        sheet.alpha_composite(frame, (index * frame_width, 0))

    return sheet


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--frames", type=int, required=True)
    parser.add_argument("--frame-width", type=int, default=192)
    parser.add_argument("--frame-height", type=int, default=192)
    parser.add_argument("--padding", type=float, default=0.10)
    parser.add_argument("--bottom-padding", type=int, default=12)
    parser.add_argument("--clear-margin", type=int, default=6)
    args = parser.parse_args()

    image = Image.open(args.input).convert("RGBA")
    normalized = normalize_frames(
        image=image,
        frame_count=args.frames,
        frame_width=args.frame_width,
        frame_height=args.frame_height,
        padding=args.padding,
        bottom_padding=args.bottom_padding,
        clear_margin=args.clear_margin,
    )

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    normalized.save(args.out)
    print(
        f"wrote {args.out} {normalized.width}x{normalized.height} "
        f"({args.frames} frames)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
