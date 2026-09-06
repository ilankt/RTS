"""Archive the current art pack and verify every archived byte before edits."""
from pathlib import Path
from datetime import datetime
import hashlib
import json
import zipfile

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'art/ages/backups'
OUT.mkdir(exist_ok=True)
stamp=datetime.now().strftime('%Y-%m-%d_%H%M%S')
target=OUT/f'{stamp}_before-detail-pass.zip'
folders=['art/ages/units','art/ages/proposal','assets/sprites/Units/Ages','assets/ui/Units/Ages']
files={p for folder in folders for p in (ROOT/folder).rglob('*') if p.is_file() and p.suffix!='.log' and '__pycache__' not in p.parts}
files.add(ROOT/'art/ages/advancement-tree.html')
files.update((ROOT/'art/outlined_units').glob('*.blend'))
files.add(ROOT/'art/mounted_units/mounted_spearman.blend')
hashes={}
with zipfile.ZipFile(target,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=2) as archive:
    for path in sorted(files):
        data=path.read_bytes();name=path.relative_to(ROOT).as_posix()
        hashes[name]=hashlib.sha256(data).hexdigest();archive.writestr(name,data)
    archive.writestr('RESTORE-MANIFEST.json',json.dumps(hashes,indent=2))
with zipfile.ZipFile(target) as archive:
    for name,digest in hashes.items():
        assert hashlib.sha256(archive.read(name)).hexdigest()==digest,name
target.with_suffix('.json').write_text(json.dumps({'archive':target.name,'file_count':len(hashes),'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'restore':'Extract the archive into the repository root, replacing only its listed art files. Preserve a snapshot of the newer version first.'},indent=2))
print(f'VERIFIED BACKUP: {target} ({len(hashes)} files; {target.stat().st_size:,} bytes)')
