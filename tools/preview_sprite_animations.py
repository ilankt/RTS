"""Create local animation previews for horizontal 192px sprite sheets."""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw


FRAME_SIZE = 192


def split_frames(sheet: Image.Image) -> list[Image.Image]:
    if sheet.height != FRAME_SIZE or sheet.width % FRAME_SIZE != 0:
        raise ValueError(
            f"Expected a {FRAME_SIZE}px-high sheet with width divisible by {FRAME_SIZE}; "
            f"got {sheet.width}x{sheet.height}"
        )

    return [
        sheet.crop((x, 0, x + FRAME_SIZE, FRAME_SIZE)).convert("RGBA")
        for x in range(0, sheet.width, FRAME_SIZE)
    ]


def composite_on_checker(frame: Image.Image) -> Image.Image:
    tile = 16
    bg = Image.new("RGBA", frame.size, (0, 0, 0, 255))
    draw = ImageDraw.Draw(bg)
    for y in range(0, frame.height, tile):
        for x in range(0, frame.width, tile):
            color = (28, 28, 28, 255) if ((x // tile + y // tile) % 2) else (58, 58, 58, 255)
            draw.rectangle((x, y, x + tile - 1, y + tile - 1), fill=color)
    bg.alpha_composite(frame)
    return bg.convert("P")


def write_gif(frames: list[Image.Image], out: Path, duration_ms: int) -> None:
    preview_frames = [composite_on_checker(frame) for frame in frames]
    preview_frames[0].save(
        out,
        save_all=True,
        append_images=preview_frames[1:],
        duration=duration_ms,
        loop=0,
        disposal=2,
    )


def write_contact(frames: list[Image.Image], out: Path) -> None:
    canvas = Image.new("RGBA", (FRAME_SIZE * len(frames), FRAME_SIZE), (20, 20, 20, 255))
    draw = ImageDraw.Draw(canvas)
    for i, frame in enumerate(frames):
        x = i * FRAME_SIZE
        checker = composite_on_checker(frame).convert("RGBA")
        canvas.alpha_composite(checker, (x, 0))
        draw.rectangle((x, 0, x + FRAME_SIZE - 1, FRAME_SIZE - 1), outline=(90, 120, 160, 255), width=1)
        draw.text((x + 5, 5), str(i + 1), fill=(235, 235, 235, 255))
    canvas.save(out)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("sheets", nargs="+", help="Sprite sheets to preview.")
    parser.add_argument("--out-dir", default="tmp/asset_previews")
    parser.add_argument("--duration-ms", type=int, default=120)
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for sheet_path_text in args.sheets:
        sheet_path = Path(sheet_path_text)
        sheet = Image.open(sheet_path).convert("RGBA")
        frames = split_frames(sheet)
        stem = sheet_path.stem
        write_gif(frames, out_dir / f"{stem}.gif", args.duration_ms)
        write_contact(frames, out_dir / f"{stem}_contact.png")
        print(f"wrote previews for {sheet_path} ({len(frames)} frames)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
