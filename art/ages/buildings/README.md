# Buildings through three ages

**Integrated artwork: 30 approved Image Generation sprites.** The user rejected the Blender
approach: buildings need only one static direction. `index.html` now presents
the replacement painted sprites. See `imagegen/README.md`, `imagegen/raw/`
for preserved magenta sources, `imagegen/sprites/` for cleaned PNGs and
`imagegen/magenta-prompts.json` for the prompt set. Rebuild the current gallery
with `python art/ages/buildings/imagegen/prepare.py`.
Install game copies with `python art/ages/buildings/imagegen/install.py`.
Runtime artwork uses `data/age_buildings.json`; the Iron Castle is the approved v3.

The material below documents the superseded Blender attempt, preserved only
for reference. Its gallery is `blender-review.html`.

Open `index.html` for the self-contained review gallery. Filter by family and
click a model to enlarge it. Feedback can be sent in chat by building and age.
The model and PNG download links need this folder alongside the HTML.

Thirty editable Blender models cover twelve building families. Town Center,
Barracks, House, Farm, Lumbermill and Mine have all three ages. Stable,
Blacksmith, Temple, Siege Workshop, Market and Watchtower unlock in Bronze,
so they have Bronze and Iron variants. The civic lineage is Town Center →
Town Hall → Castle; every other building keeps its name.

Stone uses timber/earth/thatch, Bronze framing/plaster/clay, and Iron masonry,
metal fittings and slate. Models use the approved unit scenes' cel materials,
contours and orthographic lighting. Blue banners support eventual player tint.

- `models/*.blend`: editable named meshes and render scene.
- `sprites/*.png`: transparent 512×512 renders.
- `manifest.json`: names, ages, families, relative paths and ground anchors.
- `roster.png`: all 30 variants side by side.
- `validation.json`: render size, alpha and padding verification.

These superseded Blender assets are archived and are not used by gameplay.

Rebuild from the repository root in PowerShell:

```powershell
& 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe' -b -t 4 --python art/ages/buildings/render.py
python art/ages/buildings/pack.py
```
