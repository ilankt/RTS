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

Latest style pass follows the user-supplied ChatGPT cartoon reference: larger head, fuller mane/tail, sturdy legs with cream fetlocks, cream muzzle/blaze, decorative saddle cloth and chest pendant with gold trim. These are cloth decorations, not armor. Spear remains wooden for tier one. decorated-review.png compares three player colors using the actual game tint function; preview_colors.py verifies recoloring and alpha preservation. Current animation GIFs still predate this review pass.

Decoration revision: continuous rounded saddle blanket wraps the back/flanks; curved breast collar follows the chest. Cheek straps run behind/below the eyes and segmented reins sag below the jaw. Latest decorated-review.png verifies these surfaces in three player colors.

Latest revision removes all reins, nose/cheek straps and bridle buttons. Dark leather, a fine gold seat rim and a deeper team-colored saddle blanket separate the rider from the saddle. Three-color preview regenerated and tint/alpha checks pass.

Animation review refreshed for the approved rope-free decorated design: idle, trot and mounted spear thrust, each with eight frames in eight directions. Spear grip follows the right hand. review.py verifies at least four distinct poses per direction/action and checks all 192 frames for clipping. idle-preview.gif, run-preview.gif and attack-preview.gif now show the current model.

Muzzle/thrust refinement: reduced flattened muzzle with soft corners and smaller nostrils. The mounted attack holds the spear level, draws back and pokes along one fixed axis before recovery; a two-segment arm follows the grip. verify_thrust.py checks the saved Blender timeline for constant direction, axial travel, grip attachment and return to the starting pose.
