"""Verify actual hoof trajectories in Blender, independently of frame order.

blender -b -t 2 --python art/mounted_units/verify_gait.py
Optional -- --render-check renders a corrected pose for each live variant.
"""
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from repair_gait import ROOT, OUT, SPECS, DIRS

results = []
for unit, model, count, _, _ in SPECS:
    bpy.ops.wm.open_mainfile(filepath=str(ROOT / model))
    scene = bpy.context.scene
    facing = bpy.data.objects['Facing']
    start = 9 if count == 8 else 18
    stance_checks = swing_checks = 0
    max_loop_error = 0
    for direction, angle in zip(DIRS, [90, 45, 0, 315, 270, 225, 180, 135]):
        facing.rotation_euler.z = math.radians(angle)
        forward = Vector((math.sin(math.radians(angle)), -math.cos(math.radians(angle)), 0))
        for name in ['Fore left', 'Fore right', 'Hind left', 'Hind right']:
            hip = bpy.data.objects[name]
            knee = next(o for o in hip.children if o.name.startswith('Knee flex'))
            points = []
            for i in range(count):
                scene.frame_set(start + i)
                points.append(knee.matrix_world @ Vector((0, 0, -.65)))
            ground = min(p.z for p in points)
            assert -.01 < ground < .10, (unit, name, ground)
            assert max(p.z for p in points) - ground > .15, (unit, name, 'no hoof clearance')
            for i, point in enumerate(points):
                travel = (points[(i+1) % count] - points[(i-1) % count]).dot(forward)
                if abs(travel) < .003:
                    continue  # The front/back turnaround is neither stroke.
                if point.z <= ground + .012:
                    assert travel < 0, (unit, direction, name, i, 'planted hoof travels forward')
                    stance_checks += 1
                elif point.z > ground + .08:
                    assert travel > 0, (unit, direction, name, i, 'lifted hoof travels backward')
                    swing_checks += 1
            if count == 16:
                scene.frame_set(start + count)
                error = ((knee.matrix_world @ Vector((0, 0, -.65))) - points[0]).length
                max_loop_error = max(max_loop_error, error)
    assert stance_checks >= 8*4 and swing_checks >= 8*4
    assert max_loop_error < .00001, (unit, 'open run loop', max_loop_error)
    results.append(dict(unit=unit, directions=8, stance_checks=stance_checks,
                        swing_checks=swing_checks, max_loop_error=max_loop_error))
    if '--render-check' in sys.argv and unit != 'original':
        facing.rotation_euler.z = math.radians(90)
        scene.frame_set(start + 3)
        scene.render.filepath = str(OUT / f'{unit}-render.png')
        bpy.ops.render.render(write_still=True)
    print('PASS', results[-1], flush=True)
OUT.mkdir(parents=True, exist_ok=True)
(OUT / 'verification.json').write_text(json.dumps(results, indent=2))
