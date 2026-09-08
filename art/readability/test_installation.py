"""Exercise installed sheets through the game's real directional decoder."""
import os,json,hashlib,sys
from pathlib import Path
os.environ.setdefault('SDL_VIDEODRIVER','dummy')
os.environ.setdefault('SDL_AUDIODRIVER','dummy')
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
import pygame
from systems.animation import Animation

def test_approved_models_and_installed_animation_contract():
    manifest=json.loads((ROOT/'art/readability/installed.json').read_text())
    stone={u['name']:u for u in json.loads((ROOT/'data/units.json').read_text())}
    ages=json.loads((ROOT/'data/age_units.json').read_text())
    mapping={'clubman':'warrior','worker':'worker','slinger':'archer','spearman':'spearman'}
    assert len(manifest['units'])==14 and manifest['total_frames']==4928
    for unit,meta in manifest['units'].items():
        assert hashlib.sha256((ROOT/meta['model']).read_bytes()).hexdigest()==meta['model_sha256']
        data=stone[mapping[unit]] if unit in mapping else ages[unit]
        assert data['ground_anchor']==meta['ground_anchor'] and data['render_scale']==meta['render_scale']
        for action in meta['actions']:
            sheet=pygame.image.load(str(ROOT/data['animations'][action]))
            anim=Animation(sheet,192,192,1000/meta['fps'],directions=8)
            assert len(anim.frames)==meta['frames_per_direction'] and anim.direction_count==8
            assert abs(len(anim.frames)*anim.animation_speed-800)<1e-6
            assert len({pygame.image.tobytes(anim.get_current_frame(d),'RGBA') for d in range(8)})==8
            for n in range(len(anim.frames)):
                anim.current_frame_index=n
                for d in range(8):
                    rect=anim.get_current_frame(d).get_bounding_rect()
                    assert rect.width>0 and rect.height>0 and min(rect.x,rect.y,192-rect.right,192-rect.bottom)>=2

def test_mounted_and_siege_assets_remain_unchanged():
    manifest=json.loads((ROOT/'art/readability/installed.json').read_text())
    for path,expected in manifest['protected_assets'].items():
        assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==expected
