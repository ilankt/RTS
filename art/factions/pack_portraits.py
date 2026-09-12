"""Frame faction portraits like the shared 128px age-unit portraits."""
from pathlib import Path
from PIL import Image

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]


def portrait(sprite):
    bounds = sprite.getbbox()
    if not bounds:
        raise ValueError('Empty unit portrait')
    subject = sprite.crop(bounds)
    scale = 112 / max(subject.size)
    subject = subject.resize((round(subject.width*scale), round(subject.height*scale)),
                             Image.Resampling.LANCZOS)
    icon = Image.new('RGBA', (128, 128))
    icon.paste(subject, ((128-subject.width)//2, (128-subject.height)//2))
    return icon


if __name__ == '__main__':
    for unit in ['axeman', 'horse_archer']:
        source = Image.open(OUT / 'frames' / unit / 'idle/SE/00.png').convert('RGBA')
        icon = portrait(source)
        icon.save(OUT / 'portraits' / f'{unit}.png')
        icon.save(ROOT / 'assets/ui/Units/Factions' / f'{unit}.png')
        print(unit, icon.size, icon.getbbox())
