"""Validate and install approved foot-unit renders without touching mounted/siege art.

Run with Python/Pillow after rebuilding the review frames. Game balance, entity
IDs and animation cycle duration remain unchanged. Git preserves prior assets.
"""
import hashlib
import json
from pathlib import Path
from PIL import Image

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
DIRECTIONS=['E','SE','S','SW','W','NW','N','NE']
STONE={'clubman':'warrior','worker':'worker','slinger':'archer','spearman':'spearman'}
AGE=['bronze_worker','iron_worker','bronze_swordsman','iron_swordsman','archer','crossbowman','bronze_spearman','pikeman','healer','priest']

def source(unit):
    if unit in ['clubman','bronze_swordsman','iron_swordsman']:return OUT,OUT/'full-frames'
    folder=OUT/('workers' if 'worker' in unit else 'remaining')
    return folder,folder/'frames'

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def install():
    units=json.loads((ROOT/'data/units.json').read_text())
    ages=json.loads((ROOT/'data/age_units.json').read_text())
    untouched={name:json.dumps(meta,sort_keys=True) for name,meta in ages.items() if name not in AGE}
    protected={p:digest(p) for name in untouched for p in [ROOT/ages[name]['icon'],*[ROOT/v for v in ages[name]['animations'].values()]]}
    prepared=[];manifest={}
    for unit in [*STONE,*AGE]:
        folder,frames=source(unit);meta=json.loads((folder/'models'/f'{unit}.json').read_text())
        # Blender's float32 camera values include noise around exact scales.
        # Keep a nominal 1.0 scale from truncating a 64px sprite to 63px.
        meta['render_scale']=round(meta['render_scale'],6)
        meta['ground_anchor']=[round(v,6) for v in meta['ground_anchor']]
        target=next(u for u in units if u['name']==STONE[unit]) if unit in STONE else ages[unit]
        count=8 if unit in STONE else 16
        actions=[a for a in target['animations'] if a!='guard']
        stats={};model=folder/'models'/f'{unit}_option_b.blend'
        for action in actions:
            sheet=Image.new('RGBA',(192*count,192*8));facings=[];bounds_all=[]
            for row,d in enumerate(DIRECTIONS):
                poses=[]
                for n in range(count):
                    path=frames/unit/action/d/f'{n:02}.png'
                    with Image.open(path) as im:
                        assert im.mode=='RGBA' and im.size==(192,192),path
                        bounds=im.getbbox();assert bounds and min(bounds[0],bounds[1],192-bounds[2],192-bounds[3])>=2,(path,bounds)
                        poses.append(hashlib.sha256(im.tobytes()).hexdigest());bounds_all.append(bounds)
                        sheet.paste(im,(n*192,row*192))
                assert action=='idle' or len(set(poses))>=4,(unit,action,d)
                facings.append(poses[0])
            assert len(set(facings))==8,(unit,action)
            prepared.append((ROOT/target['animations'][action],sheet))
            stats[action]={'frames':count*8,'minimum_margin':min(min(b[0],b[1],192-b[2],192-b[3]) for b in bounds_all)}
        with Image.open(frames/unit/'idle/SE/00.png') as im:portrait=im.crop(im.getbbox())
        portrait.thumbnail((112,112),Image.Resampling.LANCZOS)
        icon=Image.new('RGBA',(128,128));icon.paste(portrait,((128-portrait.width)//2,(128-portrait.height)//2))
        prepared.append((ROOT/target['icon'],icon))
        target.update(ground_anchor=meta['ground_anchor'],render_scale=meta['render_scale'])
        if unit in AGE:
            target['model']=model.relative_to(ROOT).as_posix()
            if unit=='archer':target['action_events']['shoot']['release_frame']=9
        manifest[unit]=dict(model=model.relative_to(ROOT).as_posix(),model_sha256=digest(model),frame_source=frames.relative_to(ROOT).as_posix(),frames_per_direction=count,fps=count/.8,ground_anchor=meta['ground_anchor'],render_scale=meta['render_scale'],actions=stats)
    # All frame validation completes before changing any runtime asset.
    for path,im in prepared:
        path.parent.mkdir(parents=True,exist_ok=True);im.save(path)
    (ROOT/'data/units.json').write_text(json.dumps(units,indent=2)+'\n')
    (ROOT/'data/age_units.json').write_text(json.dumps(ages,indent=2)+'\n')
    assert all(json.dumps(ages[n],sort_keys=True)==v for n,v in untouched.items())
    assert all(digest(p)==h for p,h in protected.items()),'Mounted/siege assets changed'
    (OUT/'installed.json').write_text(json.dumps(dict(units=manifest,total_frames=sum(a['frames'] for m in manifest.values() for a in m['actions'].values()),sheets=sum(len(m['actions']) for m in manifest.values()),protected_assets={str(p.relative_to(ROOT)).replace('\\','/'):h for p,h in protected.items()}),indent=2)+'\n')
    print('Installed',len(manifest),'approved variants;',sum(len(m['actions']) for m in manifest.values()),'sheets. Mounted/siege hashes unchanged.')

if __name__=='__main__':install()
