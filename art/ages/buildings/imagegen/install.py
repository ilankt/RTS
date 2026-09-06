"""Install the approved static paintings at game resolution; preserve sources."""
import json
from pathlib import Path

from PIL import Image

SOURCE = Path(__file__).resolve().parent
ROOT = SOURCE.parents[3]


def install():
    entries = json.loads((SOURCE / 'manifest.json').read_text(encoding='utf-8'))
    assert len(entries) == 30
    output = ROOT / 'assets/sprites/Buildings/Ages'
    output.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for entry in entries:
        source = SOURCE.parent / entry['sprite']
        # Keep the approved canvas, proportions and margins. All renderer,
        # construction and UI paths use this same static image.
        image = Image.open(source).convert('RGBA')
        assert image.size == (1254, 1254)
        target = output / (entry['id'] + '.png')
        image.resize((512, 512), Image.Resampling.LANCZOS).save(target)
        manifest[entry['id']] = {
            'family': entry['family'], 'age': entry['age'],
            'sprite': target.relative_to(ROOT).as_posix(),
            'source': source.relative_to(ROOT).as_posix(),
            'size': [512, 512], 'frames': 1, 'directions': 1,
        }
    (ROOT / 'data/age_buildings.json').write_text(
        json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(f'Installed {len(manifest)} approved building sprites (512px RGBA).')


if __name__ == '__main__':
    install()
