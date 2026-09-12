"""Correct existing authored trot cycles without changing any rendered pose.

Run once with Blender --python ... -- --models, then Python ... --assets.
The source generator now authors this order directly. Backups and verification
live in _gen/forward_gait; rerunning checks markers/hashes instead of reversing
already corrected assets. Only run sections/sheets are changed.
"""
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / '_gen/forward_gait'
DIRS = ['E', 'SE', 'S', 'SW', 'W', 'NW', 'N', 'NE']
SPECS = [
    ('original', 'art/mounted_units/mounted_spearman.blend', 8,
     'art/mounted_units/frames/run', 'assets/sprites/Units/MountedSpearmanOutlined/run.png'),
    ('mounted_spearman', 'art/ages/units/models/mounted_spearman.blend', 16,
     'art/ages/units/frames/mounted_spearman/run', 'assets/sprites/Units/Ages/mounted_spearman/run.png'),
    ('heavy_cavalry', 'art/ages/units/models/heavy_cavalry.blend', 16,
     'art/ages/units/frames/heavy_cavalry/run', 'assets/sprites/Units/Ages/heavy_cavalry/run.png'),
    ('horse_archer', 'art/factions/models/horse_archer.blend', 16,
     'art/factions/frames/horse_archer/run', 'assets/sprites/Units/Factions/horse_archer/run.png'),
]


def backup(path):
    target = OUT / 'before' / path.relative_to(ROOT)
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    return target


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def repair_models():
    import bpy
    from mathutils import Vector
    results = []
    for name, model, count, _, _ in SPECS:
        path = ROOT / model
        bpy.ops.wm.open_mainfile(filepath=str(path))
        scene = bpy.context.scene
        if scene.get('mounted_forward_trot') == 1:
            print('Already corrected:', name, flush=True)
            continue
        backup(path)
        start = 9 if count == 8 else 18
        stride = count if count == 8 else count + 1
        objects = [o for o in scene.objects if o.animation_data and o.name != 'Facing']
        properties = ['location', 'rotation_euler', 'scale']

        def snapshot(frame):
            scene.frame_set(frame)
            return {o: {p: tuple(getattr(o, p)) for p in properties} for o in objects}

        def signature(frame):
            scene.frame_set(frame)
            return {o.name: tuple(v for row in o.matrix_world for v in row)
                    for o in scene.objects if o.type == 'MESH'}

        def contacts():
            # In Facing-local coordinates the horse points toward -Y.
            tracks = {}
            for name in ['Fore left', 'Fore right', 'Hind left', 'Hind right']:
                hip = bpy.data.objects[name]
                knee = next(o for o in hip.children if o.name.startswith('Knee flex'))
                points = []
                for i in range(count):
                    scene.frame_set(start + i)
                    point = (bpy.data.objects['Facing'].matrix_world.inverted()
                             @ knee.matrix_world @ Vector((0, 0, -.65)))
                    points.append([point.y, point.z])
                tracks[name] = points
            return tracks

        before_contacts = contacts()
        untouched = {f: signature(f) for a in [0, 2]
                     for f in range(a * stride + 1, a * stride + count + 1)}
        poses = [snapshot(start + i) for i in range(count)]
        run_signatures = [signature(start + i) for i in range(count)]
        # Retain phase zero and the closing pose. Every direction shares this
        # same cycle: 0, N-1, N-2, ... 1 (never reverse direction rows).
        for i in range(stride):
            for obj, state in poses[(-i) % count].items():
                for prop, value in state.items():
                    setattr(obj, prop, value)
                    obj.keyframe_insert(prop, frame=start + i)
        errors = []
        for i in range(stride):
            actual = signature(start + i)
            expected = run_signatures[(-i) % count]
            errors += [abs(a-b) for name in expected
                       for a, b in zip(actual[name], expected[name])]
        for frame, expected in untouched.items():
            actual = signature(frame)
            errors += [abs(a-b) for name in expected
                       for a, b in zip(actual[name], expected[name])]
        assert max(errors) < .00001, (name, max(errors))
        after_contacts = contacts()
        scene['mounted_forward_trot'] = 1
        scene.frame_set(1)
        bpy.context.preferences.filepaths.save_version = 0
        bpy.ops.wm.save_as_mainfile(filepath=str(path))
        results.append(dict(unit=name, max_pose_error=max(errors),
                            before=before_contacts, after=after_contacts))
        print('Corrected model:', name, 'max pose error:', max(errors), flush=True)
    if results:
        (OUT / 'models.json').write_text(json.dumps(results, indent=2))


def repair_assets():
    from PIL import Image
    report_path = OUT / 'assets.json'
    if report_path.exists():
        report = json.loads(report_path.read_text())
        for path, expected in report['hashes'].items():
            assert digest(ROOT / path) == expected, ('Changed since correction:', path)
        print('All corrected assets already installed and verified.')
        return
    hashes = {}
    results = []
    for name, _, count, folder, sheet_path in SPECS:
        folder = ROOT / folder
        source = Image.open(backup(ROOT / sheet_path)).convert('RGBA')
        assert source.size == (192 * count, 192 * 8)
        sheet = Image.new('RGBA', source.size)
        margin = 192
        for row, direction in enumerate(DIRS):
            paths = [folder / direction / f'{i:02}.png' for i in range(count)]
            # Read the complete cycle before overwriting any frame.
            old_frames = [backup(path).read_bytes() for path in paths]
            for i, path in enumerate(paths):
                path.write_bytes(old_frames[(-i) % count])
                frame = Image.open(path).convert('RGBA')
                old = source.crop(((-i) % count * 192, row * 192,
                                   ((-i) % count + 1) * 192, (row + 1) * 192))
                assert frame.tobytes() == old.tobytes(), (name, direction, i)
                bounds = frame.getbbox()
                assert bounds and frame.size == (192, 192)
                margin = min(margin, *bounds[:2], 192-bounds[2], 192-bounds[3])
                assert frame.getchannel('A').getextrema() == (0, 255)
                sheet.paste(frame, (i * 192, row * 192))
                hashes[path.relative_to(ROOT).as_posix()] = digest(path)
        assert margin >= 3, (name, margin)
        path = ROOT / sheet_path
        backup(path)
        sheet.save(path)
        hashes[sheet_path] = digest(path)
        if name == 'horse_archer':
            review = ROOT / 'art/factions/sheets/horse_archer/run.png'
            backup(review)
            shutil.copy2(path, review)
            hashes[review.relative_to(ROOT).as_posix()] = digest(review)
        results.append(dict(unit=name, frames=count*8, min_edge_margin=margin))
    report_path.write_text(json.dumps(dict(units=results, hashes=hashes), indent=2))
    print('Installed and verified', sum(r['frames'] for r in results),
          'lossless frames in eight directions; only the run order changed.')


if __name__ == '__main__':
    OUT.mkdir(parents=True, exist_ok=True)
    if '--models' in sys.argv:
        repair_models()
    elif '--assets' in sys.argv:
        repair_assets()
    else:
        raise SystemExit('Use Blender -- --models, then Python --assets.')
