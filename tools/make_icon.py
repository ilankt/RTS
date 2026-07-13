"""Generate installer/app.ico (the exe/app icon) from a source PNG.

Windows needs a real multi-size .ico for the executable; PyInstaller won't
take a .png. This converts the source art once so RTS.spec can pick it up.

Usage:
    python tools/make_icon.py [source_png]

With no argument it looks for assets/ICON.png (then assets/icon.png). Called
automatically by build_installer.bat before the PyInstaller step, so the icon
always matches the current source art. The generated installer/app.ico is a
build artifact (git-ignored); the source PNG in assets/ is the thing to commit.
"""
import os
import sys

try:
    from PIL import Image
except ImportError:
    print("make_icon: Pillow not installed - skipping "
          "(run 'pip install pillow' to enable a custom icon)")
    raise SystemExit(0)

CANDIDATES = [
    os.path.join("assets", "ICON.png"),
    os.path.join("assets", "icon.png"),
]
OUT = os.path.join("installer", "app.ico")
# Sizes Windows picks between for taskbar / desktop / alt-tab / title bar.
SIZES = [16, 24, 32, 48, 64, 128, 256]


def find_source():
    if len(sys.argv) > 1:
        return sys.argv[1]
    for path in CANDIDATES:
        if os.path.exists(path):
            return path
    return CANDIDATES[0]


def main():
    src = find_source()
    if not os.path.exists(src):
        print(f"make_icon: no source PNG at {src} - "
              "skipping (exe will use PyInstaller's default icon)")
        return 0

    img = Image.open(src).convert("RGBA")
    w, h = img.size
    side = max(w, h)
    # Pad non-square art to a centered transparent square so it isn't stretched.
    if w != h:
        square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        square.paste(img, ((side - w) // 2, (side - h) // 2))
        img = square

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    img.save(OUT, format="ICO", sizes=[(s, s) for s in SIZES])
    print(f"make_icon: wrote {OUT} from {src} ({w}x{h} source)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
