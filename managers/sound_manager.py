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
  victory.ogg / defeat.ogg stingers, ambient.ogg bed
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
    (victory/defeat one-shots), ambient (low bed on its own channel).
    The combat pool is optional — without combat_* files the peace pool
    plays regardless of mood.
    """

    DUCK_FACTOR = 0.35     # music volume multiplier while ducked
    DUCK_RECOVER_S = 0.8   # ramp back to full over this many seconds

    def __init__(self):
        self.menu_track = None
        self.peace_playlist = []
        self.combat_playlist = []
        self.stingers = {}       # 'victory' / 'defeat' -> path
        self.ambient_track = None
        self.index = 0
        self.volume = 0.4
        self.mode = None  # None | 'menu' | 'game' | 'stinger'
        self.mood = 'peace'  # 'peace' | 'combat' (only meaningful in 'game')
        self._scanned = False
        # Own RNG: track picks must never consume the global random stream
        # the seeded map gen / AI rolls depend on
        self._rng = random.Random()
        self._last_game_index = None  # last game track played, ever
        self._duck_until = 0.0
        self._applied_volume = None
        self._ambient_channel = None
        self._ambient_sound = None

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
        self.ambient_track = None
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
                ambient = os.path.join(base, "ambient.ogg")
                if self.ambient_track is None and os.path.exists(ambient):
                    self.ambient_track = ambient
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

    def _apply_volume(self, force=False):
        value = self.volume * self._duck_multiplier()
        if not force and self._applied_volume is not None and abs(value - self._applied_volume) < 0.005:
            return
        self._applied_volume = value
        try:
            pygame.mixer.music.set_volume(value)
        except Exception:
            pass
        if self._ambient_channel is not None:
            try:
                self._ambient_channel.set_volume(value * 0.5)
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
        crossfades to a track from the new pool — but only when the new
        mood actually has its own tracks (no pointless track hops)."""
        if mood not in ('peace', 'combat') or mood == self.mood:
            return
        self.mood = mood
        if self.mode != 'game':
            return
        target_pool = self.combat_playlist if mood == 'combat' else self.peace_playlist
        if not target_pool:
            return  # nothing dedicated to switch to; keep playing
        playlist = self._active_game_playlist()
        self.index = self._pick_game_index(len(playlist))
        if self._play(playlist[self.index]):
            self._last_game_index = self.index

    def play_menu(self):
        """Loop the dedicated menu theme (safe no-op without tracks/mixer)."""
        if not self._ensure_ready():
            return
        self._stop_ambient()
        if self.menu_track is None:
            self.play_game()  # no menu theme yet: reuse the game playlist
            return
        if self.mode == 'menu':
            return
        if self._play(self.menu_track, loops=-1):
            self.mode = 'menu'

    def _pick_game_index(self, count):
        """A random track index, never the one that played last (repeats
        only when a single track exists)."""
        if count <= 1:
            return 0
        choices = [i for i in range(count) if i != self._last_game_index]
        return self._rng.choice(choices)

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
            self._start_ambient()

    def play_stinger(self, kind):
        """One-shot victory/defeat fanfare over everything else. Falls back
        to letting the current music keep playing when no stinger file
        exists. After the stinger ends the music stays stopped (the menu
        restarts it when the player navigates back)."""
        path = self.stingers.get(kind)
        if path is None or not self._ensure_ready():
            return False
        self._stop_ambient()
        if self._play(path, loops=0, fade_ms=0):
            self.mode = 'stinger'
            return True
        return False

    def _start_ambient(self):
        """Low looping bed on its own channel, if ambient.ogg exists."""
        if self.ambient_track is None:
            return
        try:
            if self._ambient_sound is None:
                self._ambient_sound = pygame.mixer.Sound(self.ambient_track)
            self._ambient_channel = self._ambient_sound.play(loops=-1, fade_ms=2000)
            self._apply_volume(force=True)
        except Exception:
            self._ambient_channel = None

    def _stop_ambient(self):
        if self._ambient_channel is not None:
            try:
                self._ambient_channel.fadeout(800)
            except Exception:
                pass
            self._ambient_channel = None

    def stop(self):
        self._stop_ambient()
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
        playlist = self._active_game_playlist()
        if not playlist:
            return
        self.index = self._pick_game_index(len(playlist))
        if self._play(playlist[self.index]):
            self._last_game_index = self.index

    def _play(self, path, loops=0, fade_ms=1500):
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

    def __init__(self, game):
        self.game = game
        self.enabled = True
        self.volume = 0.3          # SFX volume
        self.barks = {}            # (unit_name, kind) -> [Sound, ...]
        # Own RNG for bark variant picks — never the seeded global stream.
        self._rng = random.Random()

        try:
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
            self._generate_sounds()
            self._load_sfx_overrides()
            self._load_barks()
        except Exception:
            self.enabled = False

    def set_volume(self, volume):
        """SFX volume 0.0-1.0, applied to every loaded sound (§8.2)."""
        self.volume = min(1.0, max(0.0, float(volume)))
        for sound in getattr(self, "sounds", {}).values():
            sound.set_volume(self.volume)
        for variants in self.barks.values():
            for sound in variants:
                sound.set_volume(self.volume)

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
        # Insufficient resources / invalid command
        self.sounds["error"] = self._make_descending_sound(220, 120, 0.12)

    def _load_sfx_overrides(self):
        """Real files replace synth placeholders: assets/sfx/<key>.ogg|.wav
        (AUDIO_GUIDE §2 — filenames map to sound keys; synth stays as the
        fallback when a file is missing or unloadable)."""
        for key in list(self.sounds.keys()):
            for ext in (".ogg", ".wav"):
                path = os.path.join(SFX_DIR, key + ext)
                if os.path.exists(path):
                    try:
                        self.sounds[key] = pygame.mixer.Sound(path)
                    except Exception:
                        pass
                    break

    def _load_barks(self):
        """Unit response barks: assets/sfx/bark_<unit>_<kind>_<n>.ogg|.wav
        (kind: select/move/attack). Multiple numbered variants per unit+kind
        rotate randomly. No files -> per-type pitch variants of the synth
        blips keep unit types audibly distinct."""
        try:
            paths = glob.glob(os.path.join(SFX_DIR, "bark_*.ogg"))
            paths += glob.glob(os.path.join(SFX_DIR, "bark_*.wav"))
        except Exception:
            paths = []
        for path in sorted(paths):
            stem = os.path.splitext(os.path.basename(path))[0]
            parts = stem.split("_")  # bark, unit, kind, n
            if len(parts) < 3 or parts[2] not in self.BARK_KINDS:
                continue
            try:
                sound = pygame.mixer.Sound(path)
            except Exception:
                continue
            self.barks.setdefault((parts[1], parts[2]), []).append(sound)

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
        """Play a sound by name."""
        if not self.enabled:
            return
        sound = self.sounds.get(sound_name)
        if sound:
            sound.set_volume(self.volume)
            sound.play()

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
        if unit_name and (unit_name, "select") not in self.barks:
            self.play(self._type_variant("select", unit_name, 600, 0.03))
            return
        self._play_bark_or("select", unit_name, "select")

    def play_move_order(self, unit_name=None):
        if not self.enabled:
            return
        if unit_name and (unit_name, "move") not in self.barks:
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

    def play_error(self):
        self.play("error")

    def toggle_sound(self):
        self.enabled = not self.enabled
        return self.enabled
