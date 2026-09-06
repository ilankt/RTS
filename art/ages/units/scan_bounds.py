"""Report clipping early while a full render is still running."""
from pathlib import Path
from PIL import Image, UnidentifiedImageError

out=Path(__file__).resolve().parent
bad=[]
count=0
for path in (out/'frames').glob('*/*/*/*.png'):
    try:
        with Image.open(path) as frame:
            bounds=frame.getbbox()
            if not bounds or min(bounds[:2])<=1 or max(bounds[2:])>=191:
                bad.append((str(path.relative_to(out)),bounds))
            count+=1
    except (OSError,UnidentifiedImageError):
        pass  # A concurrent renderer can be midway through writing a PNG.
print('Rendered cells inspected:',count)
print('Clipped cells:',bad[:30], 'total',len(bad))
