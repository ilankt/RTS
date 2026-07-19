"""Verify generated RTS visual assets and data references."""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]


EXPECTED_DIMS = {
    "assets/ui/Units/ram_icon.png": (1024, 1024),
    "assets/ui/Units/spearman_icon.png": (1024, 1024),
    "assets/ui/Units/cavalry_icon.png": (1024, 1024),
    "assets/ui/Techs/improved_tools_icon.png": (1024, 1024),
    "assets/ui/Techs/reinforced_frames_icon.png": (1024, 1024),
    "assets/ui/Techs/forged_blades_icon.png": (1024, 1024),
    "assets/ui/Techs/fletching_icon.png": (1024, 1024),
    "assets/ui/Techs/padded_armor_icon.png": (1024, 1024),
    "assets/ui/Techs/siege_engineering_icon.png": (1024, 1024),
    "assets/sprites/Buildings/Stable.png": (1000, 1000),
    "assets/sprites/Buildings/Blacksmith.png": (1000, 1000),
    "assets/sprites/Buildings/SiegeWorkshop.png": (1000, 1000),
    "assets/sprites/Units/Spearman/Spearman_Idle.png": (1536, 192),
    "assets/sprites/Units/Spearman/Spearman_Run.png": (1152, 192),
    "assets/sprites/Units/Spearman/Spearman_Attack.png": (768, 192),
    "assets/sprites/Units/Spearman/Spearman_Guard.png": (1152, 192),
    "assets/sprites/Units/Cavalry/Cavalry_Idle.png": (1536, 192),
    "assets/sprites/Units/Cavalry/Cavalry_Run.png": (1152, 192),
    "assets/sprites/Units/Cavalry/Cavalry_Attack.png": (768, 192),
    "assets/sprites/Units/Cavalry/Cavalry_Guard.png": (1152, 192),
    "assets/sprites/Units/Ram/Ram_Idle.png": (1152, 192),
    "assets/sprites/Units/Ram/Ram_Run.png": (1152, 192),
    "assets/sprites/Units/Ram/Ram_Attack.png": (768, 192),
    "assets/sprites/Units/Ram/Ram_Guard.png": (1152, 192),
    # §8.2.2 HUD cost glyphs — bare transparent cut-outs (not framed icons)
    "assets/ui/Glyphs/gold_glyph.png": (1024, 1024),
    "assets/ui/Glyphs/wood_glyph.png": (1024, 1024),
    "assets/ui/Glyphs/food_glyph.png": (1024, 1024),
    "assets/ui/Glyphs/time_glyph.png": (1024, 1024),
}


# Assets that must have transparent corners: all sprite sheets, plus the HUD
# cost glyphs (a baked background there renders as an opaque square in-game).
TRANSPARENT_ASSETS = {
    path for path in EXPECTED_DIMS
    if path.startswith("assets/sprites/") or path.startswith("assets/ui/Glyphs/")
}


def exact_case_exists(relative_path: str) -> bool:
    current = ROOT
    for part in Path(relative_path).parts:
        matches = [child for child in current.iterdir() if child.name == part]
        if not matches:
            return False
        current = matches[0]
    return current.exists()


def referenced_asset_paths() -> set[str]:
    paths: set[str] = set()
    for data_file in ("units.json", "buildings.json", "techs.json"):
        records = json.loads((ROOT / "data" / data_file).read_text())
        for record in records:
            for key in ("icon", "sprite"):
                if record.get(key):
                    paths.add(record[key])
            for path in record.get("animations", {}).values():
                paths.add(path)
    return paths


def assert_image(relative_path: str, expected_size: tuple[int, int] | None) -> None:
    path = ROOT / relative_path
    with Image.open(path) as image:
        image = image.convert("RGBA")
        if expected_size and image.size != expected_size:
            raise AssertionError(f"{relative_path}: expected {expected_size}, got {image.size}")
        if relative_path in TRANSPARENT_ASSETS:
            corners = [
                image.getpixel((0, 0))[3],
                image.getpixel((image.width - 1, 0))[3],
                image.getpixel((0, image.height - 1))[3],
                image.getpixel((image.width - 1, image.height - 1))[3],
            ]
            if any(alpha != 0 for alpha in corners):
                raise AssertionError(f"{relative_path}: expected transparent corners, got {corners}")


def verify_tileset(failures: list) -> None:
    """§11.1: the terrain sheet's geometry is load-bearing — its size must
    match what tileset.json slices (3 columns x however many rows the base
    layout + variants occupy, 128x112 each). Manifest-driven because
    tools/build_tileset_from_textures.py grows the sheet with variants."""
    import json

    manifest_path = ROOT / "assets" / "tiles" / "tileset.json"
    sheet_path = ROOT / "assets" / "tiles" / "tileset.png"
    if not manifest_path.exists() or not sheet_path.exists():
        failures.append("missing assets/tiles/tileset.png or tileset.json")
        return
    manifest = json.loads(manifest_path.read_text())
    cells = []
    for tile in manifest["tiles"]:
        cells.append(tile["location"])
        cells.extend(tile.get("variants", []))
    cols = max(c for c, _ in cells) + 1
    rows = max(r for _, r in cells) + 1
    expected = (cols * manifest["tile_width"], rows * manifest["tile_height"])
    actual = Image.open(sheet_path).size
    if actual != expected:
        failures.append(
            f"tileset.png is {actual[0]}x{actual[1]} but tileset.json "
            f"slices {expected[0]}x{expected[1]}")


def main() -> int:
    referenced = referenced_asset_paths()
    failures = []
    verify_tileset(failures)

    for relative_path in sorted(referenced):
        if not exact_case_exists(relative_path):
            failures.append(f"missing or casing mismatch: {relative_path}")

    for relative_path, expected_size in EXPECTED_DIMS.items():
        if not exact_case_exists(relative_path):
            failures.append(f"missing generated asset: {relative_path}")
            continue
        try:
            assert_image(relative_path, expected_size)
        except Exception as exc:
            failures.append(str(exc))

    if failures:
        for failure in failures:
            print(f"FAIL {failure}")
        return 1

    print(f"verified {len(EXPECTED_DIMS)} generated assets and {len(referenced)} data references")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
