# Remaining foot-unit review

Installed in gameplay on 2026-09-08 through `../install.py`, together with the
approved melee and Worker variants. Earlier review outputs remain as evidence.

Actual Blender scenes and renders for Slinger, Archer, Crossbowman, Spearman,
Bronze Spearman, Pikeman, Healer and Priest. The three Workers are in `../workers`.
Approved Clubman/Swordsmen, all source models and all gameplay assets are preserved.
Horses and ballistas are explicitly excluded.

Changes emphasize equipment and silhouette: a larger fork carried forward, taller
bow, wider crossbow, stronger spearheads, tall oval bucklers, wider robe hems and
larger staff finials. Quivers move back for clearance. Weapon handles retain their
grip points. Arms, wrists, bowstrings and sling bands are rebuilt where the larger
equipment requires it; the original action cadence remains.

`render_units.py` rebuilds and renders each unit from its original source. It accepts
`-- --group ranged|spears|healers`, `--unit NAME`, and `--models-only`. Run it with
Blender's `-b -t 4 --python` options. Each unit has eight directions and its original
idle, run and attack/shoot cycle. Camera expansion has compensating display scale
and ground anchors, so comparisons do not shrink the character to fit the weapon.

Run `check_units.py -- --strict` in Blender for evaluated mesh intersection and
containment checks at eighth-frame intervals. Expected hand/handle, wrist and
shield-arm contacts are enumerated in the JSON report; other equipment/body
contacts fail the check. Grip coincidence and bowstring/fork attachments are
checked separately. This is a sampled equipment audit, not a claim that every
possible body/body contact or arbitrary future animation is collision-free.

Run `render_details.py` in Blender, then `build_review.py` in Python with Pillow.
The latter validates every exported frame's alpha, margins, active motion and
eight directions, and creates group comparisons and before/after action GIFs.
Run `../build_remaining_roster.py` for the combined roster and matched crowd.

Final evidence is in `clearance.json` and `verification.json`. These are review
assets only; no production sprite packer or gameplay configuration is changed.
