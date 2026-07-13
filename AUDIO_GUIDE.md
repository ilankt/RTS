# Audio Asset Guide

How to generate/source the background music and sound effects for this RTS, and
how to prep them for the game. Target vibe: **Warcraft 3 — orchestral fantasy.**

This is a *content* guide — you make the assets, then drop them into folders and
they get wired in. The intended layout (filenames matter — they map to sound keys):

```
assets/
  music/
    menu.ogg          # main menu / title
    peace_01.ogg      # exploration loop A
    peace_02.ogg      # exploration loop B
    peace_03.ogg      # exploration loop C   (optional)
    combat_01.ogg     # battle loop A
    combat_02.ogg     # battle loop B        (optional)
    victory.ogg       # one-shot stinger
    defeat.ogg        # one-shot stinger
  sfx/
    attack.ogg  hit.ogg  death.ogg  build_complete.ogg  research_complete.ogg
    select.ogg  move_order.ogg  gather.ogg  ui_click.ogg  alert.ogg  error.ogg
```

> The 11 SFX names above are exactly the ones `managers/sound_manager.py` already
> plays as synth placeholders. Match the filenames and each real file replaces its
> bleep automatically (with the synth kept as fallback if a file is missing).

---

## 1. Background Music

### 1.1 What tracks you actually need

RTS music is a small rotation of **long, loopable** beds, plus a couple of short
one-shots. You don't need many — 4–6 good loops carry a whole game.

| Track | Purpose | Count | Length | Loops? |
|-------|---------|-------|--------|--------|
| `menu` | Title screen, sets tone | 1 | 60–120 s | yes |
| `peace_0x` | Base-building / exploration | 2–3 | **90–150 s** | yes |
| `combat_0x` | Active battle / tension | 1–2 | 60–120 s | yes |
| `victory` | Win stinger | 1 | 6–12 s | **no** |
| `defeat` | Loss stinger | 1 | 6–12 s | **no** |

**Why these lengths:** you already got a clean 150 s track — that's the sweet spot
for a peace loop. Longer generations (toward the model's ~3 min max) tend to *drift*
and lose coherence, which makes them harder to loop. If in doubt, generate 90–150 s
of *good* material and tile it rather than 180 s that wanders. Stingers are short and
intentionally **don't** loop — generate them at ~10 s or trim a punchy bit out of a
longer take.

### 1.2 Prompt formula (Stable Audio 3 Medium Base)

The model responds well to a structured prompt. Order things like this:

```
[genre/setting] | [lead instruments] | [mood] | [tempo in BPM] | [production descriptors]
```

Always include **`instrumental, no lead vocals, no lyrics`** (choir *pads* like
"oohs/aahs" are fine and wanted — just no solo singer over the top), and
**`loopable, consistent, no long silence, no fade out`** to keep it tileable.

### 1.3 Ready-to-paste prompts

**Menu / title theme**
```
Epic orchestral main theme for a medieval fantasy strategy game, soaring strings
and heroic French horns, grand timpani, full choir swells, noble and adventurous,
90 BPM, cinematic and wide, instrumental, no lead vocals, no lyrics, loopable,
consistent, no fade out.
```

**Peace / exploration — heroic (human-faction feel)**
```
Warm orchestral exploration music, noble legato strings, gentle French horn melody,
soft harp and woodwinds, light timpani, majestic but calm, medieval fantasy kingdom,
85 BPM, spacious and warm, instrumental, no lead vocals, loopable, seamless,
no long silence.
```

**Peace / exploration — mystical (elven / forest feel)**
```
Calm mystical ambient orchestral, harp arpeggios, soft flute and clarinet, ethereal
choir pad, distant chimes, peaceful enchanted forest, 80 BPM, gentle and dreamy,
instrumental, no lyrics, loopable, seamless, no fade out.
```

**Peace / exploration — somber (undead / eerie feel)**
```
Dark ambient orchestral, low sustained cellos, muted brass, eerie choir drone,
sparse harp, cold and mysterious, haunted fantasy ruins, 75 BPM, tense and quiet,
instrumental, no lead vocals, loopable, seamless.
```

**Combat — heroic charge**
```
Intense orchestral battle music, driving staccato strings, powerful brass stabs,
war drums and taiko, crashing cymbals, epic choir shouts, heroic and urgent,
fantasy strategy game combat, 140 BPM, aggressive and cinematic, instrumental,
no lyrics, loopable, relentless, no fade out.
```

**Combat — dark war march**
```
Ominous tribal war march, pounding low taiko drums, snarling low brass, dissonant
strings, deep male choir chant, building dread, orc horde fantasy battle, 130 BPM,
heavy and menacing, instrumental, loopable, seamless, no silence.
```

**Victory stinger** (generate ~10 s, no loop)
```
Short triumphant orchestral fanfare, bright brass, rising strings, cymbal crash,
choir hit, heroic resolution, medieval fantasy victory, cinematic, instrumental.
```

**Defeat stinger** (generate ~10 s, no loop)
```
Short somber orchestral outro, descending strings, low brass, single tolling bell,
mournful choir, tragic defeat, medieval fantasy, cinematic, instrumental.
```

### 1.4 Music generation tips

- **Test `use_reprompt` OFF.** That toggle rewrites your prompt before generating.
  It can help, but it also drifts away from the exact orchestration you asked for.
  Run the *same seed* with reprompt on vs off and keep whichever sounds better.
- **Roll 3–4 seeds per prompt** and audition before committing. Music gen is a
  slot machine — the 3rd take is often much better than the 1st. **Log the
  seed + prompt** of keepers (paste them at the bottom of this file) so you can
  regenerate or make variants later.
- **BPM actually matters** — WC3 exploration sits ~75–110 BPM, combat ~125–150.
  Stating it keeps the model from wandering in tempo (which wrecks loops).
- **Render lossless, not MP3.** In ComfyUI, swap the `Save Audio (MP3)` node
  (it's tagged `[DEPR]` anyway) for a **WAV or FLAC** save node. Keep that as your
  master; only make OGG at the end (see §3). Transcoding MP3→OGG later is
  lossy-on-lossy and sounds worse.
- **Keep music quieter than SFX.** Aim music around **-16 LUFS** (or just peak
  around -3 dBFS and turn it down in-engine). Battle music can be a touch louder
  than peace so combat *feels* like it kicks in.
- **Faction variety without new systems:** the peace prompts above (heroic /
  mystical / somber) give three moods from one pipeline. Rotate them for variety
  even though the game has no faction-music logic yet.

### 1.5 Making a track loop seamlessly

Nothing generates a perfect loop out of the box, and pygame's music loop does a
hard restart with no crossfade — so the **file itself** has to loop cleanly. Recipe
in **Audacity** (free), ~10 min per track:

1. Import the WAV. Trim any silence/build-up at the very start and any fade at the end.
2. **Crossfade the seam:** select the last ~4 seconds, `Edit > Cut`. Move the cursor
   to the very start, `Edit > Paste` won't crossfade — instead use two tracks:
   put the body on track 1, the cut tail on track 2 shifted to overlap the start,
   then `Effect > Crossfade Tracks…`. Mix down (`Tracks > Mix > Mix and Render`).
   The tail now blends into the head, hiding the seam.
3. **Check the loop:** `Edit > Preferences > Playback`, or just `Shift+Space` to
   loop-play. Listen across the seam a few times — no click, no obvious "restart."
4. `Effect > Normalize` to ~-3 dB peak (or a Loudness Normalization to -16 LUFS).
5. Export as OGG (§3).

> Quick-and-dirty alternative for **ambient pads** (the mystical/somber peace
> tracks): a soft 2–3 s fade-in at the head and fade-out at the tail makes the hard
> restart much less noticeable, even without the crossfade-fold. Good enough for
> background beds; do the proper crossfade for anything with a clear rhythm.

---

## 2. Sound Effects

### 2.1 Recommendation: source these, don't generate them

You need 11 short, punchy, *consistent* one-shots. Generative audio is fiddly for
that — inconsistent transients, weird tails. Since this is a hobby project,
**CC0 (public-domain) libraries** are faster and sound better, with zero licensing
hassle. Only reach for generation on a bespoke sound you can't find.

**Best sources (all free, CC0-friendly):**
- **[Kenney.nl](https://kenney.nl/assets?q=audio)** — CC0 game SFX packs
  ("Interface Sounds", "Impact Sounds", "RPG Audio"). Covers most UI/economy sounds
  in one download. No attribution required.
- **[Sonniss GDC bundle](https://sonniss.com/gameaudiogdc)** — huge royalty-free
  pro library, free every year. Great for combat/impacts.
- **[Freesound.org](https://freesound.org)** — filter license to **CC0**. Search the
  terms in the table below. (CC-BY works too if you keep a credits file.)

### 2.2 What each sound should be — with search terms

| File | In-game trigger | What it should sound like | Search term (Kenney/Freesound) |
|------|-----------------|---------------------------|-------------------------------|
| `attack.ogg` | Unit swings/attacks | Quick sword *swish* / bow *twang* | "sword swing", "whoosh", "bow shot" |
| `hit.ogg` | Attack lands | Meaty impact / flesh or metal thud | "melee impact", "punch", "hit flesh" |
| `death.ogg` | Unit dies | Short grunt + body fall | "death grunt", "male die", "body fall" |
| `build_complete.ogg` | Building finished | Positive wooden/stone *ka-chunk* + chime | "construction complete", "build done" |
| `research_complete.ogg` | Tech done | Brighter magical shimmer / bell up | "upgrade", "magic sparkle", "success chime" |
| `select.ogg` | Select a unit | Short soft click / "yes?" blip | "UI select", "click soft", "blip" |
| `move_order.ogg` | Right-click move | Confirmation tick / "moving" blip | "confirm", "UI tick", "command" |
| `gather.ogg` | Resource collected | Small coin/wood tick / chop | "coin", "chop wood", "pickaxe", "pickup" |
| `ui_click.ogg` | Button press | Crisp UI click | "button click", "UI click" |
| `alert.ogg` | Under attack / warning | Attention horn / warning ping | "alert", "warning", "horn short" |
| `error.ogg` | Invalid / no resources | Low "denied" buzz / thunk | "error", "invalid", "denied buzz" |

**Consistency tip:** grab UI sounds (`select`, `move_order`, `ui_click`, `error`,
`build_complete`) from a **single Kenney pack** so they share a sonic family — mixing
sources here is the #1 thing that makes indie audio feel cobbled together.

**Optional per-unit expansion (later):** the game currently has one `attack`/`hit`
pair. If you want WC3-style variety, you could add `attack_sword`, `attack_bow`,
`attack_siege` (ram) etc. Not needed to start — get the 11 first.

### 2.3 If you *do* generate SFX in ComfyUI

Same node, different settings:

- Set **`duration` to 1–4 s** (trim silence after).
- Set **`reprompt_category` to `SFX` / `Sound Effects`** if the dropdown offers it;
  otherwise **turn `use_reprompt` OFF** and write a literal description.
- Prompt the *literal sound*, dry and isolated — no music, no reverb tails:

```
Single metallic sword slash, sharp swish, dry, isolated sound effect, no music, no reverb.
```
```
Heavy blunt melee impact on armor, short thud, dry, isolated foley, no music.
```
```
Wooden building construction finished, hammer tap and satisfying ka-chunk, short, dry.
```
```
Magical research upgrade complete, bright ascending sparkle shimmer, short, clean.
```
```
Short deep error buzz, negative denied UI sound, dry, no music.
```

- Generate several, pick the cleanest, **trim to the transient + short tail** in
  Audacity, normalize to ~-3 dBFS, export OGG.

### 2.4 SFX prep tips

- **Trim hard.** SFX should start *immediately* — cut leading silence or the sound
  feels laggy in-game.
- **Normalize peaks**, but keep relative loudness sane: `ui_click`/`select` should be
  noticeably quieter than `death`/`alert`. (You can also tune this per-sound in the
  engine later — it already supports per-sound volume.)
- **Keep them short** — most under 0.5 s; `death`/`alert` maybe up to ~1 s.
- **Mono is fine** for SFX and halves file size; keep music stereo.

---

## 3. Converting to OGG (and the MP3 question)

**Why OGG:** pygame streams `.ogg` reliably and loops it cleaner than MP3, and it's a
free/open format. Standardize the game on `.ogg` for both music and SFX.

**Important:** if you only have an MP3, converting MP3→OGG is **lossy → lossy** and
degrades quality. Prefer re-rendering a **WAV/FLAC** from ComfyUI and converting
*that*. Only transcode MP3→OGG if the MP3 is all you've got.

### Option A — ffmpeg (best, scriptable)

Install once on Windows (PowerShell):
```powershell
winget install ffmpeg
# or:  choco install ffmpeg
```

Convert one file (`-q:a` is quality 0–10; **6 ≈ ~192 kbps**, great for music):
```powershell
# WAV -> OGG  (preferred: lossless source)
ffmpeg -i track.wav -c:a libvorbis -q:a 6 track.ogg

# MP3 -> OGG  (only if WAV isn't available; already-lossy source)
ffmpeg -i track.mp3 -c:a libvorbis -q:a 6 track.ogg
```

Batch-convert a whole folder (run from inside it):
```powershell
# Every WAV in the current folder -> OGG
Get-ChildItem *.wav | ForEach-Object {
    ffmpeg -i $_.FullName -c:a libvorbis -q:a 6 ($_.BaseName + ".ogg")
}

# Same for MP3s
Get-ChildItem *.mp3 | ForEach-Object {
    ffmpeg -i $_.FullName -c:a libvorbis -q:a 6 ($_.BaseName + ".ogg")
}
```

Quality settings: music `-q:a 6` (or 7 for menu theme); SFX `-q:a 4` is plenty
(short sounds don't need the bitrate). Add `-ac 1` to force mono for SFX:
```powershell
ffmpeg -i attack.wav -c:a libvorbis -q:a 4 -ac 1 attack.ogg
```

### Option B — Audacity (no command line)

You're probably already in Audacity for loop editing, so:
`File > Export > Export as OGG` → set the **Quality slider (0–10, use 6)** → Export.
Do your trim/normalize/loop *first*, export OGG *last*.

### Option C — swap the ComfyUI save node

Cleanest of all: in the graph, replace `Save Audio (MP3)` with a **WAV or FLAC**
save node so your master is lossless from the start. Then loop-edit the WAV and
export OGG via A or B. Skip MP3 entirely.

---

## 4. Suggested workflow, end to end

1. **Music:** pick a prompt (§1.3) → generate 3–4 seeds in ComfyUI at WAV/FLAC →
   audition → loop-edit the keeper in Audacity (§1.5) → export OGG (§3) → drop in
   `assets/music/` with the right filename → log the seed below.
2. **SFX:** download a Kenney/Freesound CC0 pack → pick one clip per row in §2.2 →
   trim + normalize in Audacity → export OGG → drop in `assets/sfx/` with the exact
   key name.
3. Ping me to wire up the music streaming + real-SFX loader, and it all plays.

---

## 5. Seed log (fill this in as you find keepers)

Keep prompts + seeds for tracks you liked, so you can regenerate or make variants.

| File | Seed | reprompt | Notes |
|------|------|----------|-------|
| peace_01 | | off | |
| combat_01 | | | |
| menu | | | |
