# Clubman prototype

Isolated branch: `codex/clubman-8-directions`; base: `fb6dffb`. Main remains in `D:/Dev/RTS`.

Open `preview.html` for an offline, self-contained animated gallery. `clubman.blend` is the editable source; timeline frames 1–8 idle, 9–16 walk, 17–24 attack. The procedural articulated model is a first visual study, not final character art.

Rebuild from this worktree:

```powershell
& 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe' -b -t 4 --python art/clubman/render.py
python art/clubman/pack.py
python main.py
```

Packing requires Pillow. Blender needs no external assets. Game sheets have eight rows ordered E, SE, S, SW, W, NW, N, NE, and eight 192×192 frames per row. Add `animation_directions: 8` to unit JSON to use this layout. The existing warrior ID and combat statistics are retained for compatibility; its display name and art become Clubman in this fork. Factions, age progression, final sound/icon art, and balancing are future work.
