# Faction unit graphics — review 02

Two approved faction signature units: Horse Archer and Axeman (2026-09-08).
Axeman revision 02 uses a centered
two-handed grip, naturally bent elbows, fixed arm lengths and a forward swing.
The previous pose/model is preserved in `review-01-before-centered-grip.zip`.
The user approved the graphics before authorizing gameplay integration.
Both models are now approved and integrated. Steppe Clans recruit Horse Archers
from Stables; Highland Clans recruit Axemen from Barracks. Both unlock in Bronze
Age and receive ordinary Blacksmith upgrades. First-pass stats are in `install.py`
and `data/units.json`. No additional faction economic bonuses are applied.

Open `index.html` for an offline animated gallery with action, direction,
playback speed, pause, frame stepping and a scrubber. Both units use matching
world scale. Downloads are relative to the gallery and require this directory.

## Artwork

- `models/horse_archer.blend`: editable scene based on the approved Bronze
  mounted horse and Option B Archer. Preserves horse proportions, grounded trot,
  saddle and seated legs. The upper body has a leather cap, team cloth, quiver
  and animated bow. Shooting uses the standing horse cycle, not moving fire.
- `models/axeman.blend`: editable scene using the approved Option B Clubman's
  proportions and locomotion. New single-bit axe, two-handed articulated arms,
  exposed arms, fur shoulder pieces and longer beard. The axe's forward/downward
  cutting edge leads its chop. Both hands retain their grip through recovery.
- Three separate actions per unit, sixteen exported frames per action, eight
  directions: E, SE, S, SW, W, NW, N, NE. Playback is 20 fps (0.8s cycles).
  Blender action sections begin at 1, 18 and 35, each with a closing pose.
- `frames/` holds 768 transparent 192px renders; `sheets/` contains six
  3072x1536 sprite sheets. Approved copies are installed under
  `assets/sprites/Units/Factions/` through `install.py`.
- `details/` contains 640px close-up renders. `roster.png`, `eight-directions.png`
  and `idle.gif` / `run.gif` / `attack.gif` are review compositions. GIFs use half speed.
- Model JSON files record camera-derived ground anchors and compensating display
  scales. These will be needed if the user approves gameplay integration.

## Rebuild

Run from the repository root in PowerShell:

```powershell
& 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe' -b -t 4 --python art/factions/build_models.py
& 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe' -b -t 2 --python art/factions/verify_models.py
& 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe' -b -t 4 --python art/factions/render_review.py
& 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe' -b -t 4 --python art/factions/render_review.py -- --quick
& 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe' -b -t 4 --python art/factions/render_review.py -- --quick --attack-details
python art/factions/pack_review.py
```

The builder and renderer accept `--unit horse_archer|axeman` after `--`.
The renderer's `--resume` may only be used when the model is unchanged.
`gallery.html` is the gallery template; the packer embeds the current images into
`index.html`. No external libraries or network are required for playback.

## Verification scope

`verify_models.py` samples every quarter-frame across all three complete cycles:
195 poses per unit. Evaluated meshes include modifiers, surface intersections
and closed-mesh containment using the project's established geometry helpers.
The axeman's axe is checked against body/clothing/arms, excluding intentional
handle contact with gripping hands and wrist wraps. The horse archer's imported
upper body and bow are checked against horse and tack. Existing bow/arm mechanics
are inherited unchanged from the approved Archer. This is a sampled equipment
audit, not exhaustive continuous collision certification of the entire character.
Both units also undergo grip-position and action-loop checks.
The revised Axeman additionally checks centered hand positions, elbows remaining
on their own sides of the torso, and constant upper-arm/forearm lengths. Front,
side and three-quarter close-up poses supplement these numerical checks.

`pack_review.py` verifies all frame dimensions, alpha, margins, distinct facings
and active motion, and requires clean geometry results. `verification.json`
contains the final combined evidence.

## Gameplay validation

`smoke_integration.py` exercises real recruitment, queue payments, preserved
wounds/animations, faction save v8, v7 migration, post-load updates and drawing.
It writes private test saves under `_gen/faction-save-smoke`, not user save slots.
`smoke_ai.py` runs a seeded 200-game-second Bronze scenario with both factions,
requiring each AI to recruit its own unique unit. Reports and screenshots are
under `integration/`. Focused regressions are in `tests/test_factions.py`.
