# Mounted Spearman

Implemented in the isolated `codex/clubman-8-directions` prototype. Uses the existing cavalry production slot and stable prerequisite, preserving costs, combat statistics and save compatibility. Display name: Mounted Spearman. The playable demo spawns two in control group **6**.

The approved tier-one design uses a bay horse, smaller flattened cream muzzle, rounded team-colored saddle blanket and chest collar, dark contrasting saddle leather, and a wooden spear. There are no reins, bridle straps or horse armor. Armored horses and iron weapons remain future-age work.

## Rebuild

Run from this worktree:

```powershell
& 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe' -b -t 4 --python art/mounted_units/render.py
python art/mounted_units/review.py
python art/mounted_units/pack.py
```

`mounted_spearman.blend` contains the editable horse and rider rig. Three actions (idle, trot, spear thrust), eight frames per action in each of eight directions: 192 validated transparent frames. The horse has independent leg chains, grounded hoof positioning, neck/tail movement and body suspension. The rider's articulated arm keeps its grip attached during a straight axial thrust.

`manifest.json` records the camera-derived foot anchor and presentation scale. Packing validates frame bounds before exporting sprites, portrait and cavalry metadata. `idle-preview.gif`, `run-preview.gif` and `attack-preview.gif` show the approved animation. `gameplay.png` shows the actual renderer beside infantry.

## Verification

```powershell
python art/mounted_units/verify_gameplay.py
& 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe' -b -t 2 --python art/mounted_units/verify_thrust.py
```

The gameplay check exercises production, directional animation, rendering, save/load and rendering after loading. The Blender check verifies constant spear direction, axial travel, attached grip and recovery. Shared outlined-unit tests cover player tint, foot anchors at four zoom levels and direction hysteresis. `preview_colors.py` checks recoloring and transparency in three player colors.

Mounted collision radius is explicitly 14 world pixels (infantry default is 8). Templates, production and save restoration use that same radius; selection/hover ellipses and shadows scale from it. The ellipse is a stylized ground marker, not an exact collider outline.

## Forward trot

The rig faces local -Y. A planted hoof travels +Y relative to the body;
the lifted return stroke travels toward -Y. The source generator uses a
negative run phase to satisfy this. Idle and attack retain their original
timing. All mounted variants inherit this source motion.

`repair_gait.py` updates existing source/age/faction models and reorders the
corresponding run frames losslessly, keeping phase zero and all eight facing
rows. New builds get the correct order directly from `render.py`.

```powershell
& 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe' -b -t 2 --python art/mounted_units/verify_gait.py -- --render-check
python tools/verify_forward_gait.py
```

The Blender check verifies physical stance/swing travel for all four legs
and eight directions, plus the production loop seam. The preview tool compares
the corrected model renders with installed sprites and uses the actual game
animation player. Its before/after comparison requires the local backups
created by `repair_gait.py`; output is in `_gen/forward_gait/`.
