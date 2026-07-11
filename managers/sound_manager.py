"""Sound manager - SFX (synthesized placeholders) + background music.

Music (§8.5): every .ogg in assets/sounds/Background Music forms a looping
playlist streamed through pygame.mixer.music, with its own volume control
independent of the SFX volume.
"""
import glob
import os

import pygame
import struct
import math


MUSIC_DIR = os.path.join("assets", "sounds", "Background Music")


MENU_TRACK = "menu.ogg"


class MusicPlayer:
    """The background music. pygame.mixer.music is process-global, so this
    is a module singleton (`music_player`).

    Track convention inside MUSIC_DIR — drop in new files, no code change:
    - `menu.ogg`               the main-menu theme, loops forever
    - `game_0.ogg, game_1.ogg` the in-match playlist, numerically sorted
    """

    def __init__(self):
        self.menu_track = None
        self.game_playlist = []
        self.index = 0
        self.volume = 0.4
        self.mode = None  # None | 'menu' | 'game'
        self._scanned = False

    @property
    def started(self):
        return self.mode is not None

    @staticmethod
    def _game_sort_key(path):
        """game_10 sorts after game_2; oddly named files sort last, lexically."""
        stem = os.path.splitext(os.path.basename(path))[0]
        try:
            return (0, int(stem.rsplit("_", 1)[-1]), stem)
        except ValueError:
            return (1, 0, stem)

    def _ensure_ready(self):
        """Scan the tracks once and make sure the mixer is up."""
        if not self._scanned:
            self._scanned = True
            try:
                menu_path = os.path.join(MUSIC_DIR, MENU_TRACK)
                self.menu_track = menu_path if os.path.exists(menu_path) else None
                self.game_playlist = sorted(
                    glob.glob(os.path.join(MUSIC_DIR, "game_*.ogg")),
                    key=self._game_sort_key,
                )
            except Exception:
                self.menu_track = None
                self.game_playlist = []
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
        except Exception:
            return False
        return bool(self.menu_track or self.game_playlist)

    def set_volume(self, volume):
        self.volume = min(1.0, max(0.0, float(volume)))
        try:
            pygame.mixer.music.set_volume(self.volume)
        except Exception:
            pass

    def _active_game_playlist(self):
        """The in-match tracks — falls back to the menu theme when no
        game_*.ogg exists yet."""
        if self.game_playlist:
            return self.game_playlist
        return [self.menu_track] if self.menu_track else []

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

    def play_game(self):
        """Start (or keep) the in-match playlist."""
        if self.mode == 'game':
            return
        if not self._ensure_ready():
            return
        playlist = self._active_game_playlist()
        if not playlist:
            return
        self.index %= len(playlist)
        if self._play(playlist[self.index]):
            self.mode = 'game'

    def stop(self):
        if self.mode is None:
            return
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass
        self.mode = None

    def update(self):
        """Advance the in-match playlist when a track ends (called every
        frame; get_busy is a cheap C call). The menu theme loops on its own."""
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
        self.index = (self.index + 1) % len(playlist)
        self._play(playlist[self.index])

    def _play(self, path, loops=0):
        try:
            pygame.mixer.music.load(path)
            pygame.mixer.music.set_volume(self.volume)
            pygame.mixer.music.play(loops=loops, fade_ms=1500)
            return True
        except Exception:
            return False


music_player = MusicPlayer()


class SoundManager:
    """Manages game audio: synthesized SFX and the shared music playlist."""

    def __init__(self, game):
        self.game = game
        self.enabled = True
        self.volume = 0.3          # SFX volume

        try:
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
            self._generate_sounds()
        except Exception:
            self.enabled = False

    def set_volume(self, volume):
        """SFX volume 0.0-1.0, applied to every loaded sound (§8.2)."""
        self.volume = min(1.0, max(0.0, float(volume)))
        for sound in getattr(self, "sounds", {}).values():
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

    def update_music(self):
        if self.enabled:
            music_player.update()
    
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
    
    def play_attack(self):
        self.play("attack")
    
    def play_hit(self):
        self.play("hit")
    
    def play_death(self):
        self.play("death")
    
    def play_build_complete(self):
        self.play("build_complete")

    def play_research_complete(self):
        self.play("research_complete")
    
    def play_select(self):
        self.play("select")
    
    def play_move_order(self):
        self.play("move_order")
    
    def play_gather(self):
        self.play("gather")
    
    def play_ui_click(self):
        self.play("ui_click")
    
    def play_alert(self):
        self.play("alert")

    def play_error(self):
        self.play("error")
    
    def toggle_sound(self):
        self.enabled = not self.enabled
        return self.enabled
