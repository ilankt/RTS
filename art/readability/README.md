# Approved Option B unit art

Installed in the game on 2026-09-08 after user approval: fourteen foot-unit
variants, 45 sheets, 4,928 frames and fourteen portraits. `install.py` validates
the rendered sources and installs the sheets, portraits, ground anchors and
compensating display scales. `installed.json` records the source model hashes,
frame counts and unchanged mounted/siege asset hashes. Balance and unit IDs are
unchanged. Earlier review descriptions below document the modeling process.

To rebuild from the committed final models, run Blender in background mode with
`--python art/readability/render_installed.py` (optionally `-- --unit NAME`).
It writes the correct frame directories, action timelines and eight directions. Then run
`python art/readability/install.py`. Stone cycles use eight frames at 10 fps;
age cycles use sixteen at 20 fps. The editable models include corrected loop
keys even where only integer frames are exported for gameplay.

## Review files

- `comparison.png`: original/Option B front and rear close-ups, plus sprites at
  zoom 1.0 and 0.65. Close-ups are actual 768 px Blender renders. Small rows
  use 192 px sprites scaled using the game's 64 px cell and model render scale.
  Open at 100% image size for the small rows; app fit-to-window changes their size.
- `eight-directions.png`: Option B idle from all eight facings.
- `run.gif`, `attack.gif`: original left, Option B right; SE and NW, eight
  samples per 0.8-second cycle. Swordsman previews sample every other frame.
- `mixed-crowd.png`: 42 units per panel on the game's desert source texture,
  identical layout before/after, without emblems. Other roles are unchanged.
  This is a sprite composition, not a running-game screenshot.
- `models/*_option_b.blend`: editable models retaining the original action timelines
  with corrected shoulder attachments, grips and follow-through poses.
- `attack-all-directions.gif`: corrected attacks in all eight directions.
- `swing-comparison.gif`: approved Clubman beside Bronze/Iron Swordsmen using
  that same swing, from SE and NW, synchronized over the 0.8-second cycle.
- `sword-edge-checks.json`: copied key-pose checks and measured alignment of
  the blade's sharp-edge axis with the powered stroke's direction of travel.
- `full-frames/`: every gameplay animation frame, all three actions and eight
  facings (8 frames per Clubman cycle, 16 per Swordsman cycle).
- `validation.json`: sprite RGBA, size, margins, distinct facings and active motion.
- `clearance-before.json`: the initial audit documenting real intersections.
- `clearance.json`: evaluated mesh audit at eighth-frame intervals. Checks
  equipment against the head, torso, clothes, armor, legs, and arms, plus weapon
  versus shield. Surface-triangle intersection and closed-mesh containment are
  tested. Intentional gripping hand/wrist and shield-bearing forearm contacts
  are explicitly listed. The complete rig rotates rigidly with facing, so its
  3D intersection result is direction-invariant. This is a finite sampled audit,
  not a mathematical continuous-time guarantee.
- `verification-summary.json`: 960 sprite frames, 643,068 mesh-pair checks,
  945 coincident-grip checks, and zero unintended sampled intersections.

## Geometry changes

Torso and arm hierarchy widened 18% with a static parent, leaving the head and
helmet unchanged. Each hip gains a 0.025-unit outward parent offset. The shield
is 30% larger in its plane and moves 0.035 units forward. The club is 30% wider,
20% deeper and 36% longer, keeping its grip origin. Sword blade width increases
55% and thickness 15%. The sword has a compact straight guard, with extra space
between the gripping hand and blade heel so the guard clears the forearm.
Swordsman pauldrons widen 8% in addition to the torso breadth. Existing Iron
shield size differences remain. Original keyframes remain intact beneath the
static width/stance parents; arms and weapons share those transforms.

## Animation clearance correction

The first review had real shield/body, club/head and sword-hilt/arm intersections.
The shield arm now sits forward and slightly outward; its upper arm is retargeted
back to the actual shoulder so the offset does not leave a disconnected joint.
The Clubman's right arm carries the club farther out and angles it forward;
the distal forearm is shortened beneath its wrist binding to clear the haft.
The hand stays attached to the club grip.

The user approved the corrected Clubman and requested its animation for both
Swordsmen instead of the previous diagonal slash. `swordsman_club_swing.py`
starts from that unchanged approved model, retains its body/arm/leg poses and
adds Bronze/Iron equipment. It resamples the eight-frame cycles to sixteen
frames, retaining the same 0.8-second timing and explicit closing poses. A hash
check verifies the approved Clubman file remains unchanged. The previous
Swordsman scenes are retained in `previous-sword-slash/`.

The sword is angled forward for guard/forearm clearance and rolled 90 degrees
around its length so a sharp edge, rather than a broad face, leads the downward
stroke. Edge/velocity alignment is at least 0.972 during the powered stroke;
80 key-pose checks confirm the Clubman body/arm/leg rotations were copied.
The hand and sword grip remain coincident. Gameplay damage/range/collision are
untouched. Bronze/Iron use wider cameras with compensating display scale and
ground anchors, preserving the same body size and foot position. Original
comparison renders retain their original camera metadata for a fair comparison.

## Reproduction

For the current Swordsmen, run `swordsman_club_swing.py` with Blender 5.2
(`-b -t 4 --python`), then `render_details.py`, then run `build_review.py`
with Python/Pillow. Run `check_clearance.py` with Blender and `-- --strict`
for the mesh audit, and `check_sword_edge.py` for cutting-edge/key-pose checks.
The earlier `render_option_b.py` contains the previous Swordsman slash; do not
use it to rebuild the current Swordsmen. The approved Clubman is unchanged.
All outputs stay in this directory. Do not run production packers for this review.

The user approved the Clubman and corrected Swordsmen, then authorized the
remaining foot roster. Workers, ranged infantry, spearmen and healers now have
separate review scenes in `workers/` and `remaining/`. Mounted units and ballistas
are excluded. The user requested rendered results together, not a live Blender
window. The complete approved set is now installed by `install.py`.

Start with `remaining-roster.png` and the matching 44-unit terrain comparison
`remaining-crowd.png`. The group comparison PNGs and action GIFs retain original
models on the left and revised models on the right at matching world scale.

After user feedback on tool use, bow/sling mechanics and spear motion, start with
`motion-feedback/worker.gif`, `motion-feedback/ranged.gif` and
`motion-feedback/spears.gif` for the corrected animations and their side views.
The corrective builder and mechanical checks are documented in that directory.
