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


class MusicPlayer:
    """The background-music playlist. pygame.mixer.music is process-global,
    so this is a module singleton (`music_player`) — the main menu starts a
    track and a launched match adopts it seamlessly instead of restarting.
    """

    def __init__(self):
        self.playlist = []
        self.index = 0
        self.volume = 0.4
        self.started = False
        self._scanned = False

    def _ensure_ready(self):
        """Scan the playlist once and make sure the mixer is up."""
        if not self._scanned:
            self._scanned = True
            try:
                self.playlist = sorted(glob.glob(os.path.join(MUSIC_DIR, "*.ogg")))
            except Exception:
                self.playlist = []
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
        except Exception:
            return False
        return bool(self.playlist)

    def set_volume(self, volume):
        self.volume = min(1.0, max(0.0, float(volume)))
        try:
            pygame.mixer.music.set_volume(self.volume)
        except Exception:
            pass

    def start(self):
        """Start (or keep) the playlist. Safe no-op without tracks/mixer."""
        if self.started:
            return
        if self._ensure_ready() and self._play_track(self.index):
            self.started = True

    def stop(self):
        if not self.started:
            return
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass
        self.started = False

    def update(self):
        """Advance to the next track when the current one ends (called every
        frame; get_busy is a cheap C call)."""
        if not self.started:
            return
        try:
            if pygame.mixer.music.get_busy():
                return
        except Exception:
            return
        self.index = (self.index + 1) % len(self.playlist)
        self._play_track(self.index)

    def _play_track(self, index):
        try:
            pygame.mixer.music.load(self.playlist[index])
            pygame.mixer.music.set_volume(self.volume)
            pygame.mixer.music.play(fade_ms=1500)
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
        return music_player.playlist

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
        if self.enabled:
            music_player.start()

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
