# Approved outlined cartoon units

Implemented in the isolated `codex/clubman-8-directions` branch. The original `D:/Dev/RTS` checkout is unchanged.

- Clubman: the selected option 1 geometry, navy outlines, and cel shading; idle, walk, attack. Guard reuses idle.
- Worker: matching proportions and outlines, with a cap, apron, pouch and pickaxe; idle, walk, gather, and a separate hammer/build cycle.
- Every action: eight actual directions, eight frames per direction, 192×192 transparent cells. 1,024 rendered frames total across the five units.
- Slingshot Man: forked wooden slingshot, stone pouch, idle/walk/draw-and-release; replaces the archer artwork and portrait, with stone projectiles.
- Spearman: sharpened all-wood spear and buckler, idle/walk/thrust; guard reuses idle.
- Healer: cream robe, blue stole, hood and staff, idle/walk/cast; faces the ally receiving healing.
- Matching portraits and player-coloured cloth. Worker facing follows resource/construction targets while working.

## Rebuild

From this worktree:

```powershell
& 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe' -b -t 4 --python art/outlined_units/render.py
python art/outlined_units/pack.py
python art/clubman/pack.py
```

Blender source starts from the user-selected `art/clubman/options/1_cartoon/clubman.blend`. The renderer produces editable `clubman.blend` and `worker.blend` here, with named animation timeline sections. Add `-- --unit worker` to render only the worker during iteration. Packing uses Pillow and validates all 1,024 source frames before changing the game assets.

Open `actions.gif` for motion samples. Launch `Play Clubman Prototype.cmd` for a playable match: group 1 selects six clubmen; group 2 selects three workers; groups 3, 4 and 5 select slingshot units, wooden spearmen and healers. Right-click terrain to move, resources to gather, or a construction site to build. Normal `python main.py` matches use the new art too.

## Validation

Run `python -m pytest art/outlined_units/test_integration.py tests/test_directional_animation.py tests/test_worker_task_system.py tests/test_production_queue.py tests/test_save_load.py -q` and `python art/clubman/smoke.py`.

The style options remain as historical review artifacts. Factions, ages and balance are unchanged.

The renderer exports a normalized ground anchor from the Blender camera into unit metadata. Selection markers, hover markers and shadows use that shared foot point, independent of animation pose. Gameplay coordinates and unit scale remain as before. The anchor/selection/shadow checks pass at four zoom levels; see foot-alignment.png.

Selection and hover ellipses draw above ground shadows and beneath object sprites, so feet occlude their rear arcs. Rally flags remain above objects. See ring-occlusion.png.

The three new infantry share the approved foot anchor, team tint and direction hysteresis. Their internal unit IDs, combat stats, costs and production prerequisites stay compatible with existing saves. Age progression (slingshot to archer to crossbow; wood to iron spear) and mounted units are deferred. `infantry-directions.gif` shows all eight directions and actions; `verify_infantry.py` checks actual production, healing, stone projectiles, rendering and save/load.
