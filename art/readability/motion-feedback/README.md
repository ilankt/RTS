# Mechanical animation correction review

These corrections are installed in the game as of 2026-09-08 via `../install.py`.

Approval update (2026-09-08): Archer, Slinger and the Spearman line are approved.
The user authorized Worker approval after removing the return-loop arm twitch.
Stale quarter-frame keys after the corrected final pose have now been replaced.
`worker-loop.json` checks the return interval for both work actions in all three
Worker ages; mechanical/grip and clearance checks also pass. The refreshed Worker
GIF has identical first/last images. Worker is approved under that authorization.

User feedback identified four defects missed by the first clearance-only review:
one-handed Stone Worker strokes and sideways tool heads, an incorrectly braced
bow/string, a slingshot without a backward draw and release, and upgraded spear
animations that did not match the approved Stone Spearman.

`worker.gif`, `ranged.gif` and `spears.gif` show the corrected actual Blender
renders in isometric and side views, at half speed. The pose sheets isolate key
phases. `before-motion-feedback/` retains the preceding model versions and GIFs.

`../motion_corrections.py` is called by the Worker and remaining-unit builders:

- Stone Worker receives the Bronze Worker's two-handed tool rig and stroke,
  resampled to the Stone cycle. Both grips are resolved during gathering and
  building. Tool heads use the working point/face in the direction of the stroke.
- Archer receives a continuous curved stave, straight braced string and an actual
  backward draw. A geometric solve holds both string length and limb polyline
  length constant as the limbs flex. The arrow nock follows the string. On release,
  the string returns independently while the hand follows through and reloads.
- Slinger carries an elastic pouch between the bands. The pouch moves backward
  at constant height, pauses at full draw, then snaps forward independently of the
  released hand. The fork stays steady during the shot.
- Bronze Spearman and Pikeman inherit the approved Stone Spearman's body, shoulder,
  leg and weapon motion, resampled to sixteen frames at the same cycle duration.
  Age-specific armor and longer spear geometry are retained.

`../check_motion_mechanics.py` validates the actual saved scenes: two-hand tool
attachments and working-face/velocity alignment, constant bowstring and limb
length, straight braced string, backward draw, independent release, and copied
Stone Spearman poses. Its evidence is `mechanics.json`. Full equipment/body audits
remain in the Worker and remaining-unit `clearance.json` reports, including the
evaluated curved bow geometry. Export checks remain in their `verification.json`.

To regenerate this review, run `../render_motion_feedback.py` in Blender, then
`../build_motion_feedback.py` in Python/Pillow. The renderer accepts `--unit NAME`,
or `--set worker|ranged|spears`, and `--full` to refresh production-sized review
frames. This changes review assets only; gameplay installation is still pending.
