"""Sound manager - SFX + background music (§8.5).

SFX: synthesized placeholders, each overridable by a real file — drop
`assets/sfx/<name>.ogg` (or .wav) matching a sound key and it replaces the
synth bleep automatically (AUDIO_GUIDE.md §2). Unit response barks use the
file convention `assets/sfx/bark_<unit>_<kind>_<n>.ogg` (kind: select/move/
attack); without files, per-unit-type pitch variants of the synth blips give
each type a distinct voice.

Music: mood-aware playlist streamed through pygame.mixer.music with its own
volume, independent of SFX. Track conventions (either dir, no code change):
- assets/music/  (AUDIO_GUIDE layout): menu.ogg, peace_01.ogg.., combat_01.ogg..,
  victory.ogg / defeat.ogg stingers
(The ambient.ogg bed was CUT 2026-07-25 — it overpowered the mix in play and
the user chose removal over re-levelling; don't re-add a bed without a
per-channel volume slider.)
- assets/sounds/Background Music/ (legacy): menu.ogg, game_0.ogg.. (peace pool)
Combat mood switches the pool when combat_* tracks exist; alerts duck the
music briefly; game-over plays the matching stinger when present.
"""
import glob
import os
import random
import time

import pygame
import struct
import math


MUSIC_DIR = os.path.join("assets", "sounds", "Background Music")
MUSIC_DIR_NEW = os.path.join("assets", "music")
SFX_DIR = os.path.join("assets", "sfx")


MENU_TRACK = "menu.ogg"


class MusicPlayer:
    """The background music. pygame.mixer.music is process-global, so this
    is a module singleton (`music_player`).

    Pools: menu (loops), peace (exploration), combat (battle), stingers
    (victory/defeat one-shots).
    The combat pool is optional — without combat_* files the peace pool
    plays regardless of mood.
    """

    DUCK_FACTOR = 0.35     # music volume multiplier while ducked
    DUCK_RECOVER_S = 0.8   # ramp back to full over this many seconds
    FADEOUT_MS = 900       # crossfade: old track fades out before the next fades in

    def __init__(self):
        self.menu_track = None
        self.peace_playlist = []
        self.combat_playlist = []
        self.stingers = {}       # 'victory' / 'defeat' -> path
        self.index = 0
        self.volume = 0.4
        self.mode = None  # None | 'menu' | 'game' | 'stinger'
        self.mood = 'peace'  # 'peace' | 'combat' (only meaningful in 'game')
        self._scanned = False
        # Own RNG: track picks must never consume the global random stream
        # the seeded map gen / AI rolls depend on
        self._rng = random.Random()
        self._last_game_index = None  # last game track played, ever
        # Shuffle bag: every track plays once before any repeats
        self._shuffle_bag = []
        self._bag_count = 0
        # Track queued behind a fadeout (crossfade second half)
        self._pending_track = None
        self._duck_until = 0.0
        self._applied_volume = None

    @property
    def started(self):
        return self.mode is not None

    # Back-compat alias: the settings/UI code and tests referred to the
    # in-match pool as `game_playlist` before moods existed.
    @property
    def game_playlist(self):
        return self.peace_playlist

    @staticmethod
    def _game_sort_key(path):
        """game_10 sorts after game_2; oddly named files sort last, lexically."""
        stem = os.path.splitext(os.path.basename(path))[0]
        try:
            return (0, int(stem.rsplit("_", 1)[-1]), stem)
        except ValueError:
            return (1, 0, stem)

    def _scan(self):
        self.menu_track = None
        self.peace_playlist = []
        self.combat_playlist = []
        self.stingers = {}
        try:
            for base in (MUSIC_DIR_NEW, MUSIC_DIR):
                menu_path = os.path.join(base, MENU_TRACK)
                if self.menu_track is None and os.path.exists(menu_path):
                    self.menu_track = menu_path
                self.peace_playlist += sorted(
                    glob.glob(os.path.join(base, "peace_*.ogg")), key=self._game_sort_key)
                self.peace_playlist += sorted(
                    glob.glob(os.path.join(base, "game_*.ogg")), key=self._game_sort_key)
                self.combat_playlist += sorted(
                    glob.glob(os.path.join(base, "combat_*.ogg")), key=self._game_sort_key)
                for kind in ("victory", "defeat"):
                    path = os.path.join(base, f"{kind}.ogg")
                    if kind not in self.stingers and os.path.exists(path):
                        self.stingers[kind] = path
        except Exception:
            pass

    def _ensure_ready(self):
        """Scan the tracks once and make sure the mixer is up."""
        if not self._scanned:
            self._scanned = True
            self._scan()
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
        except Exception:
            return False
        return bool(self.menu_track or self.peace_playlist or self.combat_playlist)

    def set_volume(self, volume):
        self.volume = min(1.0, max(0.0, float(volume)))
        self._apply_volume(force=True)

    def _duck_multiplier(self):
        """1.0 normally; DUCK_FACTOR while ducked, ramping back linearly."""
        now = time.monotonic()
        if now < self._duck_until:
            return self.DUCK_FACTOR
        since = now - self._duck_until
        if since < self.DUCK_RECOVER_S:
            t = since / self.DUCK_RECOVER_S
            return self.DUCK_FACTOR + (1.0 - self.DUCK_FACTOR) * t
        return 1.0

    # Music tracks are mastered LOUD — the current set peaks at 0 dBFS with
    # ~-15 dB RMS, while the SFX average ~-27 dB RMS. Raw, that is a 12 dB gap
    # in RMS, and music is continuous where SFX are transient, so it swallows
    # the mix even with the slider near its minimum (user-reported: "music at
    # 10% is louder than SFX at 30%"). This trim rescales the slider into a
    # useful range instead of re-encoding the audio, so nothing is re-
    # compressed and it can be undone with one number. Raise it toward 1.0 if
    # the tracks are ever remastered to ~-16 LUFS as AUDIO_GUIDE §1.4 asks.
    MUSIC_HEADROOM = 0.30

    def _apply_volume(self, force=False):
        value = self.volume * self._duck_multiplier() * self.MUSIC_HEADROOM
        if not force and self._applied_volume is not None and abs(value - self._applied_volume) < 0.005:
            return
        self._applied_volume = value
        try:
            pygame.mixer.music.set_volume(value)
        except Exception:
            pass

    def duck(self, seconds=2.5):
        """Dip the music under an alert/stinger moment (§8.5)."""
        self._duck_until = max(self._duck_until, time.monotonic() + seconds)
        self._apply_volume()

    def _active_game_playlist(self):
        """The in-match tracks for the current mood, with fallbacks: a mood
        pool that has no files falls back to the other pool, then the menu
        theme — silence only when nothing exists at all."""
        if self.mood == 'combat' and self.combat_playlist:
            return self.combat_playlist
        if self.peace_playlist:
            return self.peace_playlist
        if self.combat_playlist:
            return self.combat_playlist
        return [self.menu_track] if self.menu_track else []

    def set_mood(self, mood):
        """'combat' during active fighting, 'peace' otherwise. Switching
        crossfades to a track from the new pool — but ONLY when the mood
        change actually changes which pool is playing. Without dedicated
        combat tracks both moods resolve to the same pool, and the old
        check restarted a random peace track every time combat ENDED
        (user-reported: songs never finish, replaced mid-song)."""
        if mood not in ('peace', 'combat') or mood == self.mood:
            return
        pool_before = self._active_game_playlist()
        self.mood = mood
        if self.mode != 'game':
            return
        pool_after = self._active_game_playlist()
        if pool_after is pool_before or not pool_after:
            return  # same pool either way — let the current track finish
        self.index = self._pick_game_index(len(pool_after))
        self._crossfade_to(pool_after[self.index])

    def play_menu(self):
        """Loop the dedicated menu theme (safe no-op without tracks/mixer)."""
        if not self._ensure_ready():
            return
        if self.menu_track is None:
            self.play_game()  # no menu theme yet: reuse the game playlist
            return
        if self.mode == 'menu':
            return
        if self._play(self.menu_track, loops=-1):
            self.mode = 'menu'

    def _pick_game_index(self, count):
        """Shuffle-bag pick: random order, but every track plays once
        before any repeats, and never the same track twice in a row
        (repeats only when a single track exists)."""
        if count <= 1:
            return 0
        if self._bag_count != count or not self._shuffle_bag:
            indices = list(range(count))
            self._rng.shuffle(indices)
            # A fresh bag must not open with the track that just played
            if indices[0] == self._last_game_index:
                indices.append(indices.pop(0))
            self._shuffle_bag = indices
            self._bag_count = count
        return self._shuffle_bag.pop(0)

    def play_game(self):
        """Start (or keep) the in-match playlist, shuffled."""
        if self.mode == 'game':
            return
        if not self._ensure_ready():
            return
        self.mood = 'peace'
        playlist = self._active_game_playlist()
        if not playlist:
            return
        self.index = self._pick_game_index(len(playlist))
        if self._play(playlist[self.index]):
            self.mode = 'game'
            self._last_game_index = self.index

    def play_stinger(self, kind):
        """One-shot victory/defeat fanfare over everything else. Falls back
        to letting the current music keep playing when no stinger file
        exists. After the stinger ends the music stays stopped (the menu
        restarts it when the player navigates back)."""
        path = self.stingers.get(kind)
        if path is None or not self._ensure_ready():
            return False
        if self._play(path, loops=0, fade_ms=0):
            self.mode = 'stinger'
            return True
        return False

    def _crossfade_to(self, path):
        """Fade the current track out; update() starts `path` (fading in)
        once the fadeout completes. Starts immediately when nothing is
        actually playing (or the mixer is down)."""
        self._pending_track = path
        try:
            if pygame.mixer.music.get_busy():
                pygame.mixer.music.fadeout(self.FADEOUT_MS)
                return
        except Exception:
            pass
        self._start_pending()

    def _start_pending(self):
        path = self._pending_track
        self._pending_track = None
        if path is not None and self._play(path):
            self._last_game_index = self.index

    def stop(self):
        self._pending_track = None
        if self.mode is None:
            return
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass
        self.mode = None

    def update(self):
        """Advance the in-match playlist when a track ends (called every
        frame; get_busy is a cheap C call). The menu theme loops on its own.
        Also runs the duck-volume ramp."""
        self._apply_volume()
        if self.mode == 'stinger':
            try:
                if not pygame.mixer.music.get_busy():
                    self.mode = None
            except Exception:
                pass
            return
        if self.mode != 'game':
            return
        try:
            if pygame.mixer.music.get_busy():
                return
        except Exception:
            return
        if self._pending_track is not None:
            # Crossfade second half: the fadeout finished, fade the new one in
            self._start_pending()
            return
        playlist = self._active_game_playlist()
        if not playlist:
            return
        self.index = self._pick_game_index(len(playlist))
        if self._play(playlist[self.index]):
            self._last_game_index = self.index

    def _play(self, path, loops=0, fade_ms=1500):
        # Whatever plays now supersedes any queued crossfade target
        self._pending_track = None
        try:
            pygame.mixer.music.load(path)
            self._apply_volume(force=True)
            pygame.mixer.music.play(loops=loops, fade_ms=fade_ms)
            return True
        except Exception:
            return False


music_player = MusicPlayer()


class SoundManager:
    """Manages game audio: SFX (file overrides over synth placeholders),
    unit barks, and the shared mood-aware music playlist."""

    BARK_KINDS = ("select", "move", "attack")
    # Only real audio files are heard. The synthesized bleeps stay loaded as a
    # silent scaffold so every trigger, throttle and spatial gate keeps working
    # — drop assets/sfx/<key>.ogg in and that sound switches itself on. Flip to
    # False to hear the placeholders again.
    SILENCE_PLACEHOLDERS = True
    # File-only sound keys — no synth placeholder, they simply don't exist
    # until a file is supplied. Per-resource gather sounds fall back to the
    # generic `gather` when absent.
    EXTRA_SFX = ("gather_gold", "gather_wood", "gather_food", "building_destroyed")
    # Looping beds tied to game state, each an optional assets/sfx/<name>.ogg.
    # Unlike the one-shot keys these have no synth fallback: no file, no loop.
    LOOP_SFX = ("construction",)
    LOOP_VOLUME = 0.7          # relative to the SFX volume — beds sit back

    def __init__(self, game):
        self.game = game
        self.enabled = True
        self.volume = 0.3          # SFX volume
        self.barks = {}            # (unit_name, kind) -> [Sound, ...]
        self.loops = {}            # name -> Sound (looping bed)
        self._loop_channels = {}   # name -> Channel currently looping it
        self._world_last = {}      # key -> last play time, for world throttles
        # Own RNG for bark variant picks — never the seeded global stream.
        self._rng = random.Random()

        try:
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
            # 8 (the default) runs out fast once world sounds overlap — a
            # skirmish alone can want a dozen at once.
            pygame.mixer.set_num_channels(32)
            self._generate_sounds()
            self._load_sfx_overrides()
            self._load_barks()
            self._load_loops()
        except Exception:
            self.enabled = False

    def set_volume(self, volume):
        """SFX volume 0.0-1.0, applied to every loaded sound (§8.2)."""
        self.volume = min(1.0, max(0.0, float(volume)))
        for sound in getattr(self, "sounds", {}).values():
            sound.set_volume(self.volume)
        # Numbered variants live outside `sounds` (only the first is stored
        # there), so they need setting explicitly or they play at full volume.
        for variants in getattr(self, "sfx_variants", {}).values():
            for sound in variants:
                sound.set_volume(self.volume)
        for variants in self.barks.values():
            for sound in variants:
                sound.set_volume(self.volume)
        for channel in getattr(self, "_loop_channels", {}).values():
            if channel is not None:
                try:
                    channel.set_volume(self.volume * self.LOOP_VOLUME)
                except Exception:
                    pass

    # ---- Spatial world audio (§8.5) ---------------------------------- #
    # World events are heard from the camera's viewpoint: full volume at the
    # centre of the view, fading to nothing past its edge, panned left/right
    # by where they sit on screen. Without this the whole map is audible at
    # once — every worker's axe and every distant skirmish (user-reported).
    # Zoom falls out for free: the view covers less ground zoomed in, so only
    # what you are actually looking at can be heard.
    WORLD_EDGE_MARGIN = 0.30   # extra fraction of the view that still sounds
    WORLD_MIN_GAIN = 0.05      # quieter than this -> don't bother playing
    WORLD_PAN = 0.55           # 0 = no stereo spread, 1 = hard panning

    def world_gain(self, x, y):
        """(left, right) gain for a sound at a world position, or None when it
        is too far outside the view to be worth playing."""
        camera = getattr(self.game, "camera", None)
        if camera is None:
            return (1.0, 1.0)      # headless / tests: never silence anything
        # Read the view size off the module so a resolution change is picked up
        from core import config

        zoom = getattr(camera, "zoom", 1.0) or 1.0
        half_w = max(1.0, config.MAP_VIEW_WIDTH / 2.0)
        half_h = max(1.0, config.MAP_VIEW_HEIGHT / 2.0)
        # Offset from the centre of the view, normalised so 1.0 == the edge
        dx = ((x * zoom + camera.x) - half_w) / half_w
        dy = ((y * zoom + camera.y) - half_h) / half_h
        distance = math.hypot(dx, dy) / (1.0 + self.WORLD_EDGE_MARGIN)
        if distance >= 1.0:
            return None
        gain = (1.0 - distance) ** 1.5
        if gain < self.WORLD_MIN_GAIN:
            return None
        pan = max(-1.0, min(1.0, dx))
        left = gain * (1.0 - self.WORLD_PAN * max(0.0, pan))
        right = gain * (1.0 - self.WORLD_PAN * max(0.0, -pan))
        return (left, right)

    def play_world(self, key, x, y, obj=None, min_interval=0.0):
        """Play a sound that happens somewhere on the map.

        Attenuated and panned by `world_gain`, skipped entirely when off
        screen, silent when `obj` is hidden by fog, and optionally rate-limited
        so a big battle doesn't fire the same blip dozens of times a second.
        Returns True if it actually played.
        """
        if not self.enabled or not self.has_real_sound(key):
            return False
        return self._play_positioned(self._pick(key), key, x, y, obj, min_interval)

    def play_world_unit(self, kind, unit_name, fallback_key, x, y,
                        obj=None, min_interval=0.0):
        """A per-unit-type world sound: an archer's bow, a ram's boom. Uses the
        unit's bark variant (assets/sfx/bark_<unit>_<kind>_<n>.ogg) when one is
        installed, else the shared fallback key — positional either way."""
        if not self.enabled:
            return False
        variants = self.barks.get((unit_name, kind)) if unit_name else None
        if variants:
            sound = self._rng.choice(variants)
            throttle_key = f"{kind}::{unit_name}"
        elif self.has_real_sound(fallback_key):
            sound = self._pick(fallback_key)
            throttle_key = fallback_key
        else:
            return False
        return self._play_positioned(sound, throttle_key, x, y, obj, min_interval)

    def _play_positioned(self, sound, key, x, y, obj=None, min_interval=0.0):
        """Shared body of the world-sound path: fog gate, distance/pan gain,
        throttle, then play on its own channel at the computed stereo gain."""
        if sound is None:
            return False
        if obj is not None:
            fog = getattr(self.game, "fog_of_war", None)
            if fog is not None and not fog.is_object_visible(obj):
                return False
        gains = self.world_gain(x, y)
        if gains is None:
            return False
        now = time.monotonic()
        if min_interval and now - self._world_last.get(key, -9999.0) < min_interval:
            return False
        # Recorded on every play, not just throttled ones, so call sites that
        # ask for a throttle still see plays made by ones that didn't.
        self._world_last[key] = now
        channel = sound.play()
        if channel is not None:
            # The Sound already carries self.volume, so these are pure
            # positional scalars — multiplying by volume again would square it.
            try:
                channel.set_volume(*gains)
            except Exception:
                pass
        return True

    def _load_loops(self):
        """Load the optional looping beds (assets/sfx/<name>.ogg|.wav)."""
        for name in self.LOOP_SFX:
            for ext in (".ogg", ".wav"):
                path = os.path.join(SFX_DIR, name + ext)
                if os.path.exists(path):
                    try:
                        self.loops[name] = pygame.mixer.Sound(path)
                    except Exception:
                        pass
                    break

    def set_loop_active(self, name, active, gain=1.0):
        """Start/stop a looping bed. Safe to call every frame — it only acts on
        a change, and no-ops entirely when the sound file isn't installed.
        `gain` (0-1) attenuates it by distance so the bed fades as the camera
        pans away from what is making the noise."""
        sound = self.loops.get(name)
        if sound is None:
            return
        channel = self._loop_channels.get(name)
        if active and self.enabled:
            if channel is None or not channel.get_busy():
                try:
                    channel = sound.play(loops=-1, fade_ms=250)
                except Exception:
                    channel = None
                self._loop_channels[name] = channel
            if channel is not None:
                try:
                    channel.set_volume(self.volume * self.LOOP_VOLUME * gain)
                except Exception:
                    pass
        elif channel is not None:
            try:
                channel.fadeout(300)
            except Exception:
                pass
            self._loop_channels[name] = None

    # ---- Background music (§8.5): delegates to the shared player ------ #

    @property
    def music_playlist(self):
        music_player._ensure_ready()
        return music_player.game_playlist

    @property
    def music_started(self):
        return music_player.started

    @property
    def music_volume(self):
        return music_player.volume

    def set_music_volume(self, volume):
        """Music volume 0.0-1.0, independent of the SFX volume."""
        music_player.set_volume(volume)

    def start_music(self):
        """A match plays the game_* playlist (switching off the menu theme)."""
        if self.enabled:
            music_player.play_game()

    def stop_music(self):
        music_player.stop()

    def update_music(self, in_combat=None):
        if self.enabled:
            if in_combat is not None:
                music_player.set_mood('combat' if in_combat else 'peace')
            music_player.update()

    def play_game_over(self, victory):
        """Victory/defeat stinger if the file exists (AUDIO_GUIDE layout)."""
        if self.enabled:
            music_player.play_stinger('victory' if victory else 'defeat')

    def _generate_sounds(self):
        """Generate simple synthesized sounds as placeholders."""
        self.sounds = {}

        # Attack swing sound - quick metallic ping
        self.sounds["attack"] = self._make_sound(440, 0.05, "square")
        # Hit impact - lower thud
        self.sounds["hit"] = self._make_sound(220, 0.08, "sawtooth")
        # Death sound - descending tone
        self.sounds["death"] = self._make_descending_sound(300, 100, 0.15)
        # Construction complete - ascending tone
        self.sounds["build_complete"] = self._make_ascending_sound(200, 500, 0.2)
        # Research complete - brighter ascending tone
        self.sounds["research_complete"] = self._make_ascending_sound(300, 700, 0.22)
        # Unit selection - short click
        self.sounds["select"] = self._make_sound(600, 0.03, "sine")
        # Unit move order - confirmation tone
        self.sounds["move_order"] = self._make_sound(350, 0.04, "sine")
        # Resource gathered - small chime
        self.sounds["gather"] = self._make_sound(800, 0.04, "sine")
        # UI click
        self.sounds["ui_click"] = self._make_sound(500, 0.02, "square")
        # Alert / warning
        self.sounds["alert"] = self._make_sound(880, 0.1, "square")
        # Soft rising chime for "a worker fell idle" — gentle nudge, not an
        # alarm (launch feedback: silent idling read as "workers just stopped")
        self.sounds["idle_worker"] = self._make_ascending_sound(520, 690, 0.13)
        # Insufficient resources / invalid command
        self.sounds["error"] = self._make_descending_sound(220, 120, 0.12)

    def _load_sfx_overrides(self):
        """Real files replace synth placeholders: assets/sfx/<key>.ogg|.wav
        (AUDIO_GUIDE §2 — filenames map to sound keys).

        Numbered siblings rotate: `death.ogg` + `death_2.ogg` + `death_3.ogg`
        register as variants of `death` and one is picked at random each play,
        which stops the most-repeated sounds (hits, deaths, axe swings) from
        turning into a metronome. Keys in EXTRA_SFX have no synth placeholder
        and exist only when a file is supplied."""
        self.real_sfx = set()
        self.sfx_variants = {}
        for key in list(self.sounds.keys()) + list(self.EXTRA_SFX):
            variants = []
            for suffix in ("",) + tuple(f"_{i}" for i in range(2, 10)):
                for ext in (".ogg", ".wav"):
                    path = os.path.join(SFX_DIR, key + suffix + ext)
                    if os.path.exists(path):
                        try:
                            variants.append(pygame.mixer.Sound(path))
                        except Exception:
                            pass
                        break
            if variants:
                self.sounds[key] = variants[0]
                self.sfx_variants[key] = variants
                self.real_sfx.add(key)

    def has_real_sound(self, key):
        """Is this key backed by an actual audio file (not a synth bleep)?"""
        return not self.SILENCE_PLACEHOLDERS or key in getattr(self, "real_sfx", ())

    def _pick(self, key):
        """The Sound to play for a key — a random variant when several exist."""
        variants = getattr(self, "sfx_variants", {}).get(key)
        if variants:
            return variants[0] if len(variants) == 1 else self._rng.choice(variants)
        return self.sounds.get(key)

    def _load_barks(self):
        """Per-object response barks: assets/sfx/bark_<name>_<kind>[_<n>].ogg|.wav
        (kind: select/move/attack). `name` is a unit type OR a building type, so
        clicking a farm can cluck exactly like selecting a warrior grunts.
        Numbered variants rotate at random. No files -> per-type pitch variants
        of the synth blips keep unit types audibly distinct.

        The name is read from the MIDDLE of the stem, not a fixed position, so
        multi-word types survive: bark_siege_workshop_select_1 -> siege_workshop.
        """
        try:
            paths = glob.glob(os.path.join(SFX_DIR, "bark_*.ogg"))
            paths += glob.glob(os.path.join(SFX_DIR, "bark_*.wav"))
        except Exception:
            paths = []
        for path in sorted(paths):
            parts = os.path.splitext(os.path.basename(path))[0].split("_")
            if len(parts) < 3:
                continue
            if parts[-1] in self.BARK_KINDS:                     # ..._select
                kind, name = parts[-1], "_".join(parts[1:-1])
            elif len(parts) >= 4 and parts[-2] in self.BARK_KINDS:  # ..._select_2
                kind, name = parts[-2], "_".join(parts[1:-2])
            else:
                continue
            if not name:
                continue
            try:
                sound = pygame.mixer.Sound(path)
            except Exception:
                continue
            self.barks.setdefault((name, kind), []).append(sound)

    @staticmethod
    def _type_pitch_factor(unit_name):
        """Deterministic per-type pitch offset (±15%) so each unit type's
        synth acknowledgement sounds distinct. hash() is salted per process,
        so derive from character codes instead."""
        code = sum(ord(c) for c in unit_name)
        return 1.0 + ((code % 7) - 3) * 0.05

    def _type_variant(self, key, unit_name, base_freq, duration, wave_type="sine"):
        """Lazily synthesized per-unit-type variant of a base blip."""
        cache_key = f"{key}::{unit_name}"
        if cache_key not in self.sounds:
            freq = base_freq * self._type_pitch_factor(unit_name)
            try:
                self.sounds[cache_key] = self._make_sound(freq, duration, wave_type)
            except Exception:
                return key  # fall back to the base sound
        return cache_key

    def _play_bark_or(self, kind, unit_name, fallback_key):
        """A bark file variant when one exists, else the fallback key."""
        if unit_name:
            variants = self.barks.get((unit_name, kind))
            if variants:
                sound = self._rng.choice(variants)
                sound.set_volume(self.volume)
                sound.play()
                return
        self.play(fallback_key)

    def _make_sound(self, frequency, duration, wave_type="sine"):
        """Create a synthesized sound."""
        sample_rate = 44100
        num_samples = int(sample_rate * duration)
        samples = []

        for i in range(num_samples):
            t = i / sample_rate
            envelope = 1.0 - (i / num_samples)  # Fade out

            if wave_type == "sine":
                value = math.sin(2 * math.pi * frequency * t)
            elif wave_type == "square":
                value = 1.0 if math.sin(2 * math.pi * frequency * t) > 0 else -1.0
            elif wave_type == "sawtooth":
                value = 2.0 * (frequency * t - math.floor(frequency * t + 0.5))
            else:
                value = math.sin(2 * math.pi * frequency * t)

            sample = int(value * envelope * 16000)
            samples.append(sample)
            samples.append(sample)  # Duplicate for stereo

        raw_data = struct.pack('<' + 'h' * len(samples), *samples)
        return pygame.mixer.Sound(buffer=raw_data)

    def _make_descending_sound(self, start_freq, end_freq, duration):
        """Create a descending tone."""
        sample_rate = 44100
        num_samples = int(sample_rate * duration)
        samples = []

        for i in range(num_samples):
            t = i / sample_rate
            freq = start_freq + (end_freq - start_freq) * t / duration
            envelope = 1.0 - (i / num_samples) * 0.5
            value = math.sin(2 * math.pi * freq * t)
            sample = int(value * envelope * 12000)
            samples.append(sample)
            samples.append(sample)

        raw_data = struct.pack('<' + 'h' * len(samples), *samples)
        return pygame.mixer.Sound(buffer=raw_data)

    def _make_ascending_sound(self, start_freq, end_freq, duration):
        """Create an ascending tone."""
        sample_rate = 44100
        num_samples = int(sample_rate * duration)
        samples = []

        for i in range(num_samples):
            t = i / sample_rate
            freq = start_freq + (end_freq - start_freq) * t / duration
            envelope = 1.0 - (i / num_samples) * 0.5
            value = math.sin(2 * math.pi * freq * t)
            sample = int(value * envelope * 12000)
            samples.append(sample)
            samples.append(sample)

        raw_data = struct.pack('<' + 'h' * len(samples), *samples)
        return pygame.mixer.Sound(buffer=raw_data)

    def play(self, sound_name):
        """Play a sound by name. Returns True if it was actually audible —
        placeholder-only keys are silently skipped (SILENCE_PLACEHOLDERS)."""
        if not self.enabled or not self.has_real_sound(sound_name):
            return False
        sound = self._pick(sound_name)
        if not sound:
            return False
        sound.set_volume(self.volume)
        sound.play()
        return True

    def play_attack(self, unit_name=None):
        if not self.enabled:
            return
        self._play_bark_or("attack", unit_name, "attack")

    def play_hit(self):
        self.play("hit")

    def play_death(self):
        self.play("death")

    def play_build_complete(self):
        self.play("build_complete")

    def play_research_complete(self):
        self.play("research_complete")

    def play_select(self, unit_name=None):
        if not self.enabled:
            return
        # Per-type pitch variants only make sense while `select` is still a
        # synth placeholder. Once a real file is installed it must be heard as
        # recorded, not replaced by a pitch-shifted bleep.
        if (unit_name and (unit_name, "select") not in self.barks
                and not self.has_real_sound("select")):
            self.play(self._type_variant("select", unit_name, 600, 0.03))
            return
        self._play_bark_or("select", unit_name, "select")

    def play_move_order(self, unit_name=None):
        if not self.enabled:
            return
        if (unit_name and (unit_name, "move") not in self.barks
                and not self.has_real_sound("move_order")):
            self.play(self._type_variant("move_order", unit_name, 350, 0.04))
            return
        self._play_bark_or("move", unit_name, "move_order")

    def play_gather(self):
        self.play("gather")

    def play_ui_click(self):
        self.play("ui_click")

    def play_alert(self):
        self.play("alert")
        # §8.5: alerts duck the music so they cut through the mix
        music_player.duck(2.5)

    def play_idle_worker(self):
        """Subtle chime when a worker falls idle. Quieter than a combat alert
        and deliberately does NOT duck the music — it should nudge, not alarm."""
        if not self.enabled or not self.has_real_sound("idle_worker"):
            return
        sound = self.sounds.get("idle_worker")
        if sound:
            sound.set_volume(self.volume * 0.55)
            sound.play()

    def play_error(self):
        self.play("error")

    def toggle_sound(self):
        self.enabled = not self.enabled
        return self.enabled
