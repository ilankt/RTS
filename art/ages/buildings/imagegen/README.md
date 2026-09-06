# Image-generated building sprites

The Iron Age Castle uses the newly generated `sprites/3_castle-v3.png`: the
original compact four-tower layout freshly painted with warm masonry, blue slate
roofs, iron-bound doors, lanterns and blue banners. No inner building or extra
gatehouse towers. Its magenta original is `raw/3_castle-v3.png`; its exact prompt
is `castle-v3-prompt.json`. Earlier attempts remain archived outside the gallery.
The other 29 generated building variants are retained as approved.

Replacement for the rejected Blender building set. Each building/age is one
static painted PNG in a single isometric direction, generated with the built-in
Image Generation tool. No building models, animations or directional sheets.

The user specified RGB(255, 0, 255) backgrounds, followed by background removal.
`raw/` preserves the generated magenta sources; `sprites/` contains the cleaned
RGBA exports at original resolution. The generator slightly varies the keyed
color, so `prepare.py` samples the background and removes its color contribution
at the antialiased edges. It does not repaint or resize the buildings.

`magenta-prompts.json` contains the exact final prompt set. The approved unit
portrait informed the first painted Town Center; that image provides the style
reference for the set. `manifest.json` records individual static sprite paths,
and `validation.json` checks alpha, bounds and dimensions.

Rebuild the gallery and cleaned PNGs from the preserved sources:

```powershell
python art/ages/buildings/imagegen/prepare.py
```

Review at `../index.html`; the superseded Blender gallery is preserved as
`../blender-review.html`.

All 30 approved paintings are now installed in gameplay. Run
`python art/ages/buildings/imagegen/install.py` to recreate the 512px RGBA
runtime copies in `assets/sprites/Buildings/Ages/` and `data/age_buildings.json`.
The installer preserves the approved canvas, proportions and margins; the game
keeps its existing building scale, center and collision footprints. The final
Castle v3 is installed as `3_castle.png`. Source paintings remain untouched.
Buildings, placement previews, construction overlays and portraits select art
by their owner's age; saturated blue cloth supports player colors.
