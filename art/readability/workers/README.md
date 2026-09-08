# Worker readability review

Installed in gameplay on 2026-09-08 through `../install.py`. The descriptions
below document the preceding review workflow; original source scenes remain.

Three actual Blender variants: Stone, Bronze and Iron Workers. Larger pick and
hammer heads, apron and tool pouch distinguish their working equipment. Existing
caps are retained. Tool grips and arm geometry are adjusted for clearance through
idle, run, gathering and building cycles. The pick rotates to lead with its working
point; age-worker contact markers follow the enlarged working surfaces.

`render_workers.py` builds each model from the original source and renders all
eight directions. Run with Blender `-b -t 4 --python`, optionally followed by
`-- --unit NAME --models-only`. `check_workers.py` audits equipment/body meshes
at eighth-frame intervals and checks coincident grips. `render_details.py` renders
close-ups. Run `build_review.py` with Python/Pillow to validate all 1,280 exported
frames and create before/after comparisons and gather/build/run animations.

Following user feedback, the Stone Worker uses the Bronze Worker's two-handed rig
and stroke with correctly aligned heads; both tool grips are resolved throughout
gathering/building. Build the Bronze Worker first (the default builder order does
this). Mechanical pose and working-face checks are in `../motion-feedback`.

The sampled audit passes 293,223 mesh-pair checks and 1,260 grip checks. Deliberate
hand/handle and wrist contacts are listed in the report. Originals and gameplay
assets are unchanged. The discontinued live viewer is not needed to reproduce
these review outputs.
