# Clubman style options

Three isolated art studies for user selection. The playable sprites in assets/sprites/Units/Clubman are unchanged.

1. **Outlined cartoon**: larger head, compact limbs, three-band cel shading and strong navy contours. Closest to the original worker/warrior visual language.
2. **Textured illustration**: taller proportions, finer brown contours, procedural cloth/wood grain, leather shoulder pad and diagonal strap. Emphasizes the building materials.
3. **Crisp pixel sprite**: broader torso and collar, compact proportions, cel shading rendered at 96 px and presented with nearest-neighbor scaling. Emphasizes pixel readability.

Every option carries the same wooden club and wooden buckler, with a blue tunic. These are editable Blender models, not generated concept paintings. Each has eight directional idle views and an eight-frame southeast walk preview. Full action/direction production sheets will follow the selected style.

- `three-options.png`: comparison board including original assets and actual game-rendered scene crops.
- `walk-comparison.gif`: synchronized walking comparison.
- `<option>/clubman.blend`: editable source for each option.
- `render_options.py`: regenerates all models and renders using Blender 5.2.
- `compare.py`: builds the board and GIF using the game's own renderer, pygame and Pillow. Does not modify game data or sprite assets.

Rebuild from the prototype root:

```powershell
& 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe' -b -t 4 --python art/clubman/options/render_options.py
python art/clubman/options/compare.py
```

Status: awaiting user choice and feedback. Existing buildings, units and terrain were inspected directly. All comparison scenes use the same camera, unit positions and seed (4321).
