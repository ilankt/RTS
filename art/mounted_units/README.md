# Tier-one mounted spearman - review in progress

This is an isolated art study on `codex/clubman-8-directions`. The gameplay cavalry assets have not been replaced yet.

The first horse was rejected as too chunky and donkey-like. The current revision narrows the torso, lengthens the legs, shortens the ears and refines the head/neck. It uses an unarmored bay coat, a plain leather saddle, bridle/reins and a blue-clothed rider carrying a sharpened wooden spear.

The horse has its own four articulated leg chains, neck, tail and body suspension. The rider has seated legs and separate reins/spear poses. A diagonal-pair trot uses two-bone inverse kinematics to hold stance hooves at the ground. Idle and mounted thrust are separate actions, with eight frames in each of eight actual directions.

Run from the worktree root:

```powershell
& 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe' -b -t 4 --python art/mounted_units/render.py
python art/mounted_units/review.py
python art/mounted_units/preview.py
```

`mounted_spearman.blend` contains the editable model and animation timeline. `run-preview.gif` and `attack-preview.gif` are review artifacts; `manifest.json` records the projected ground anchor and intended presentation scale. `review.py` checks all 192 frame bounds. Add `-- --preview` to the Blender command for idle views only.

Next: user feedback on revised proportions and gait, then install the approved cavalry sprites, portrait, selection footprint and demo group. Armored horses and iron weapons belong to later ages.

Current review: the user supplied a horse photograph to guide proportions. The latest model has a longer, deeper continuous torso, a forward-sloping tapered neck, elongated face and stronger upper legs. `reference-review.png` is the latest true side profile; `first-model.png` contains the latest gameplay-angle stills. Existing animation GIFs show the previous revision and will be regenerated after proportion feedback.
