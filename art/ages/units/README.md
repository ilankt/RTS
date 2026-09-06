# Bronze and Iron unit artwork

This production set extends the user-approved outlined cartoon Blender rigs.
It contains fourteen age variants, including economic worker variants. The
four existing Stone Age units remain unchanged. Bronze Healer keeps its robe
and staff design with added trim, a satchel and corrected staff clearance; the Bronze Mounted Spearman
preserves the approved horse proportions and gait with bronze rider equipment.

Open `index.html` for the animated review gallery. It embeds its sprite sheets
and works offline. Select an age, action and facing, or pause and step through
the sixteen frames. Half/quarter-speed playback and action-phase labels make the
contact, draw and reload poses easier to inspect. The combined work/attack
view shows Workers gathering rather than idling. Feedback can be sent directly
in chat using the unit name.
Model and portrait downloads use relative links and require the project files
alongside the HTML. The gallery itself needs no server or external dependency.

## Deliverables

- `models/<unit>.blend`: editable Blender 5.2 scene, named action timeline
  sections, original cel materials, navy contours, orthographic camera.
- `frames/<unit>/<action>/<direction>/<frame>.png`: rendered transparent cells.
- `manifest.json`: sprite paths, portraits, action lists, eight-direction order,
  normalized foot anchors, presentation scale and validation results.
- `../../../assets/sprites/Units/Ages/<unit>/`: 3072×1536 sprite sheets, sixteen
  frames horizontally and eight directions vertically, in 192×192 cells.
- `../../../assets/ui/Units/Ages/`: 128×128 portraits.
- `roster.png`, `action-roster.png`, `actions.gif`: overview and action reviews.

Units: Bronze Worker, Iron Worker, Bronze Swordsman, Iron Swordsman, Archer,
Crossbowman, Bronze Spearman, Pikeman, Mounted Spearman, Heavy Cavalry, Healer,
Priest, Ballista and Heavy Ballista. Workers have idle, run, gather and build.
Other units have idle, run and attack (ranged infantry calls the action shoot).
The Healer/Priest attack animation is the healing cast. Siege idle is still;
rolling wheels and the draw/release/recoil sequence animate in the other actions.

## Rebuild

From the repository root, in PowerShell:

```powershell
& 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe' -b -t 4 --python art/ages/units/render.py
python art/ages/units/pack.py
& 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe' -b -t 2 --python art/ages/units/verify_rigs.py
```

For model previews, add `-- --preview` to Blender and `--preview` to the packer.
For one unit, add `-- --unit crossbowman` to Blender. `--resume` skips already
rendered full frames; use it only when the model and renderer are unchanged.

The renderer starts from the approved sources in `art/outlined_units` and
`art/mounted_units`; it does not run their packers, which modify gameplay data.
Long spears use a wider camera and a compensating presentation scale so their
full thrust fits inside the cell without shrinking the unit in the game.

## Integration contract

The user-approved artwork is integrated into gameplay through `systems/ages.py`
and `data/age_units.json`. Workers change on age-up; military variants require
paid global line research, except the first Bronze mounted/healer/siege unlocks.
Production, live units, portraits and save/load resolve the same variant. Consumers
use each variant's `ground_anchor` and `render_scale` from the manifest,
not assume the same padding as another unit. Read `frames_per_direction=16`
and `fps=20`; each cycle still lasts 0.8 seconds. Editable model sections use
`timeline_stride=17` (16 exported frames plus a closing pose). Keep animation direction order
E, SE, S, SW, W, NW, N, NE. Guard may reuse idle. Unit portraits retain alpha.

The packer validates every source cell before exporting sheets: size and alpha,
nonempty content, edge padding, distinct directional views and visible motion
for active cycles. Editable models preserve the generated animation keys.

New geometry is modeled in Blender from the established source meshes; no
image-generation API or raster concept sheet substitutes for animation frames.

## Working-edge animation

The Bronze/Iron Workers and Swordsmen use articulated arms whose hands follow
the tool grip. Swordsmen coil beside the right shoulder, step forward and turn
the torso into a diagonal right-to-left cut, then follow through on the left.
The blade's sharp edge faces the sweep; hands stay attached while the torso
turns independently of the stance. Pickaxe horns lie across the swing plane so the lower
cutting tip meets the ore. The two hands hold separate positions on the handle.

Archer draws to the cheek, flexes both bow limbs, releases the string and reaches
for another arrow. Crossbowman has a separate cycle: aim, fire, lower the weapon,
reach and pull the string into its latch, take a bolt and seat it on the rail.
Spearman/Pikeman point inward and slightly upward from the side-held grip;
the tip converges on the opponent's center rather than a parallel offset lane.

The manifest's `action_events` uses zero-based frame indices. Melee/mining/build
contact is frame 8, Archer release is frame 10 and Crossbow release is frame 4.
These are animation timing hints for future gameplay integration.

`contact-review.gif` demonstrates the actual exported models against review-only
ore/target props in two directions; those props are not part of the sprites.
`revised-actions.gif` and `motion-strip-e.png` / `motion-strip-se.png` show the
complete sixteen-frame cycles (the still strips show every other frame).
To regenerate the affected eight variants:

```powershell
& 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe' -b -t 4 --python art/ages/units/render.py -- --affected
python art/ages/units/pack.py
python art/ages/units/review_motion.py
& 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe' -b -t 2 --python art/ages/units/render_contact_review.py
python art/ages/units/pack_contact_review.py
```

`--affected --motion-preview` renders complete active cycles in four directions
to a separate preview directory. `review_motion.py --preview` packages those
previews. Full production validation checks all eight directions.
`review_sword.py` creates `sword-slash-review.gif` and `sword-slash-strip.png`,
comparing the worker's vertical strike with the sword cut in SE and S views.
The pre-slash revision is preserved in
`../backups/2026-09-06_070407_before-detail-pass.zip`.

## Detail and clearance pass

Sword blades have tapered diamond sections, swept guards and wrapped hilts.
Workers have pocket stitching, fasteners and tool sockets; infantry have helmet
and armor fasteners, bound spear grips and quiver fittings. Cavalry receive
saddle pouches; healers receive robe trim and staff wraps; siege frames have
joinery pegs and bolt guides. The established proportions and palette remain.

The worker lifts outside the head, strikes with the pick's cutting horn and
recovers clear of the apron. Sword recovery stays in front of the shield and
tunic. Archer draws beside the cheek; Crossbowman reloads in front of the torso.
Healers keep the staff outside the hood. Intermediate poses use quaternion
rotation and resolved arm grips; each action closes back to its own first pose.
Ballista strings meet the rear of the bolt, the guide bed clears its head,
and the crank winds forward before holding for release.

`check_clearance.py` evaluates mesh intersections every quarter-frame across
all action sections, including the closing pose. `clearance-report.json`
records the checked heads/torsos and any intersections. Intentional equipment
joins and clothing/armor contact are excluded; this is a sampled geometric
check, not a continuous collision simulation. `verify_rigs.py` separately
checks grips, ore contact, forward cutting edges, spear aim and ranged phases.

The complete pre-pass snapshot is
`../backups/2026-09-06_062449_before-detail-pass.zip`; its adjacent JSON records
the archive hash and restoration instructions. The archive includes an internal
per-file SHA-256 manifest and was verified after creation. Restore it from the
repository root to recover the previous models, sprites, review files and sources.
