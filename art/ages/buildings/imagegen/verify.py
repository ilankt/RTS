"""Check delivery completeness without generating or modifying images."""
from pathlib import Path
import json
from PIL import Image

out=Path(__file__).resolve().parent
expected={row['id'] for row in json.loads((out/'magenta-prompts.json').read_text())}
rows=json.loads((out/'manifest.json').read_text())
assert len(rows)==30 and {row['id'] for row in rows}==expected
for row in rows:
    assert row['directions']==row['frames']==1
    for field in ('sprite','raw'):
        assert (out.parent/row[field]).is_file()
    image=Image.open(out.parent/row['sprite'])
    assert image.mode=='RGBA' and image.getchannel('A').getextrema()==(0,255)
    assert image.size==(row['width'],row['height'])
page=(out.parent/'index.html').read_text(encoding='utf-8')
assert '__BUILDINGS__' not in page and '${b.model}' not in page
assert page.count('data:image/png;base64,')==30
castle=next(row for row in rows if row['id']=='3_castle')
assert castle['sprite']=='imagegen/sprites/3_castle-v3.png'
assert castle['generation']=='built-in image_gen'
print('PASS: all 30 single-view sprites, magenta originals, transparency and gallery references.')
