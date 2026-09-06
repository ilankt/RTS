"""Remove the user-requested magenta key and package static sprite review art.

Preserves every generated source. No resizing or painted changes are applied.
"""
from pathlib import Path
import base64
import json
import numpy as np
from PIL import Image

OUT = Path(__file__).resolve().parent
PARENT = OUT.parent


def remove_magenta(source, destination):
    image = Image.open(source).convert('RGBA')
    rgba = np.array(image)
    rgb = rgba[:, :, :3].astype(np.float32)
    border = np.concatenate((rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]))
    key = np.median(border, axis=0)
    # Magenta contributes equally to red and blue, with no green. Removing
    # that excess also unmattes the antialiased silhouette instead of leaving
    # a bright pink fringe. Natural browns, blue cloth and neutral stone stay.
    spill = np.maximum(0, np.minimum(rgb[:, :, 0], rgb[:, :, 2]) - rgb[:, :, 1])
    alpha = np.clip(1 - spill / max(1, min(key[0], key[2]) - key[1]), 0, 1)
    # Generated magenta varies slightly despite the exact RGB prompt. Reject
    # those near-key pixels, including low-opacity background speckles.
    border_alpha = np.concatenate((alpha[0], alpha[-1], alpha[:, 0], alpha[:, -1]))
    cutoff = max(.2, min(.35, float(border_alpha.max()) + .025))
    alpha[alpha < cutoff] = 0
    safe = np.maximum(alpha, .001)
    clean = rgb.copy()
    for channel in range(3):
        clean[:, :, channel] = (rgb[:, :, channel] - (1 - alpha) * key[channel]) / safe
    rgba[:, :, :3] = np.clip(clean, 0, 255).astype(np.uint8)
    rgba[:, :, 3] = np.minimum(rgba[:, :, 3], np.round(alpha * 255)).astype(np.uint8)
    rgba[rgba[:, :, 3] == 0, :3] = 0
    result = Image.fromarray(rgba)
    result.save(destination)
    bounds = result.getbbox()
    assert bounds and result.getchannel('A').getextrema() == (0, 255), source
    assert min(bounds[:2]) > 0 and bounds[2] < image.width and bounds[3] < image.height, (source, bounds)
    return dict(width=image.width, height=image.height, bounds=list(bounds),
                transparent_fraction=round(float((rgba[:, :, 3] == 0).mean()), 3))


def build():
    original = json.loads((PARENT / 'manifest.json').read_text())
    rows = []
    validation = {}
    for entry in original:
        key = entry['id']
        filename = '3_castle-v3' if key == '3_castle' else key
        source = OUT / 'raw' / (filename + '.png')
        if not source.exists():
            continue
        target = OUT / 'sprites' / (filename + '.png')
        info = remove_magenta(source, target)
        validation[key] = info
        rows.append(dict(id=key, family=entry['family'], age=entry['age'], name=entry['name'],
                         sprite='imagegen/sprites/' + filename + '.png',
                         raw='imagegen/raw/' + filename + '.png', width=info['width'], height=info['height'],
                         directions=1, frames=1, generation='built-in image_gen',
                         background_key=[255, 0, 255]))
    (OUT / 'manifest.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
    (OUT / 'validation.json').write_text(json.dumps(validation, indent=2), encoding='utf-8')
    page_rows = [dict(row, image='data:image/png;base64,' + base64.b64encode(
        (PARENT / row['sprite']).read_bytes()).decode()) for row in rows]
    template = (PARENT / 'gallery.html').read_text(encoding='utf-8')
    template = template.replace('Building workshop / 01', 'Building workshop / 02')
    template = template.replace('These are editable 3D models in the army’s outlined cartoon style.',
                                'Painted static sprites made with Image Generation. One isometric view per building.')
    template = template.replace('512 PX TRANSPARENT ART', 'SINGLE VIEW · STATIC PNG')
    template = template.replace('12 EDITABLE BUILDING FAMILIES', 'MAGENTA ORIGINALS PRESERVED')
    template = template.replace('<a href="${b.model}" download>Blender model ↓</a>',
                                '<a href="${b.raw}" download>${b.source_label || "Magenta source"} ↓</a>')
    template = template.replace('${materials[age-1]}', '${b.note || materials[age-1]}')
    template = template.replace('Building art review ·', 'Image Generation art review ·')
    (OUT / 'gallery.html').write_text(template, encoding='utf-8')
    (PARENT / 'index.html').write_text(template.replace('__BUILDINGS__', json.dumps(page_rows)), encoding='utf-8')
    print(f'Prepared {len(rows)} static, single-view building PNGs; original magenta images preserved.')


if __name__ == '__main__':
    build()
