"""Sound manager - generates placeholder sounds using pygame mixer synthesis.

In a production game, these would be replaced with actual .wav/.ogg files.
"""
import pygame
import struct
import math


class SoundManager:
    """Manages game audio including synthesized placeholder effects."""
    
    def __init__(self, game):
        self.game = game
        self.enabled = True
        self.volume = 0.3
        
        try:
            pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)
            self._generate_sounds()
        except Exception:
            self.enabled = False
    
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
        sample_rate = 22050
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
        sample_rate = 22050
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
        sample_rate = 22050
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
