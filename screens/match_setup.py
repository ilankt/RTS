"""Match setup screen (MASTER_PLAN §7.5).

Lets the player configure a skirmish before starting: play or spectate,
opponent count, AI personality, map seed, and game speed. Returns a config
dict, or None if the player backs out.
"""
import random

import pygame

from core.config import SCREEN_WIDTH, SCREEN_HEIGHT, MIN_GAME_SPEED, MAX_GAME_SPEED

PERSONALITY_CHOICES = ["random", "balanced", "rusher", "boomer", "turtle"]


class MatchSetupScreen:
    def __init__(self, screen):
        if not pygame.font.get_init():
            pygame.font.init()
        self.screen = screen
        self.font_large = pygame.font.Font(None, 56)
        self.font_medium = pygame.font.Font(None, 36)
        self.font_small = pygame.font.Font(None, 24)

        self.config = {
            "mode": "play",           # play | spectate
            "opponents": 1,           # AI count (vs human) or total-1 in spectate
            "personality": "random",  # applied to every AI, or random per AI
            "seed": random.randint(1, 99999),
            "speed": 1,
        }
        self.rows = [
            ("Mode", "mode"),
            ("Opponents", "opponents"),
            ("AI personality", "personality"),
            ("Map seed", "seed"),
            ("Game speed", "speed"),
            ("Start match", None),
            ("Back", None),
        ]
        self.selected_index = 0

        self.bg_color = (20, 20, 30)
        self.title_color = (200, 180, 100)
        self.option_color = (200, 200, 200)
        self.selected_color = (255, 255, 100)
        self.hint_color = (100, 100, 100)

    # --- Value cycling -----------------------------------------------------
    def _adjust(self, key, direction):
        if key == "mode":
            self.config["mode"] = "spectate" if self.config["mode"] == "play" else "play"
        elif key == "opponents":
            self.config["opponents"] = max(1, min(7, self.config["opponents"] + direction))
        elif key == "personality":
            index = PERSONALITY_CHOICES.index(self.config["personality"])
            self.config["personality"] = PERSONALITY_CHOICES[(index + direction) % len(PERSONALITY_CHOICES)]
        elif key == "seed":
            self.config["seed"] = max(0, self.config["seed"] + direction)
        elif key == "speed":
            self.config["speed"] = int(max(MIN_GAME_SPEED, min(MAX_GAME_SPEED, self.config["speed"] + direction)))

    def _value_text(self, key):
        if key == "mode":
            return "Play (you vs AI)" if self.config["mode"] == "play" else "Spectate (AI vs AI)"
        if key == "opponents":
            return str(self.config["opponents"])
        if key == "personality":
            return self.config["personality"].title()
        if key == "seed":
            return str(self.config["seed"])
        if key == "speed":
            return f"{self.config['speed']}x"
        return ""

    # --- Loop ---------------------------------------------------------------
    def run(self):
        clock = pygame.time.Clock()
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return None
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        return None
                    if event.key in (pygame.K_UP, pygame.K_w):
                        self.selected_index = (self.selected_index - 1) % len(self.rows)
                    elif event.key in (pygame.K_DOWN, pygame.K_s):
                        self.selected_index = (self.selected_index + 1) % len(self.rows)
                    elif event.key in (pygame.K_LEFT, pygame.K_a):
                        self._row_adjust(-1)
                    elif event.key in (pygame.K_RIGHT, pygame.K_d):
                        self._row_adjust(1)
                    elif event.key == pygame.K_r:
                        self.config["seed"] = random.randint(1, 99999)
                    elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        label, key = self.rows[self.selected_index]
                        if label == "Start match":
                            return dict(self.config)
                        if label == "Back":
                            return None
                        self._row_adjust(1)
                if event.type == pygame.MOUSEBUTTONDOWN:
                    for i, (label, key) in enumerate(self.rows):
                        if self._row_rect(i).collidepoint(pygame.mouse.get_pos()):
                            self.selected_index = i
                            if label == "Start match":
                                return dict(self.config)
                            if label == "Back":
                                return None
                            self._row_adjust(1)
            self.draw()
            pygame.display.flip()
            clock.tick(60)

    def _row_adjust(self, direction):
        _label, key = self.rows[self.selected_index]
        if key is not None:
            self._adjust(key, direction)

    # --- Drawing ------------------------------------------------------------
    def _row_rect(self, index):
        y = SCREEN_HEIGHT // 3 + index * 52
        return pygame.Rect(SCREEN_WIDTH // 2 - 260, y - 18, 520, 42)

    def draw(self):
        self.screen.fill(self.bg_color)
        title = self.font_large.render("Match Setup", True, self.title_color)
        self.screen.blit(title, title.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 5)))

        mouse_pos = pygame.mouse.get_pos()
        for i, (label, key) in enumerate(self.rows):
            rect = self._row_rect(i)
            selected = i == self.selected_index or rect.collidepoint(mouse_pos)
            color = self.selected_color if selected else self.option_color
            if selected:
                pygame.draw.rect(self.screen, (60, 60, 80), rect, border_radius=5)
                pygame.draw.rect(self.screen, self.selected_color, rect, 2, border_radius=5)

            if key is None:
                text = self.font_medium.render(label, True, color)
                self.screen.blit(text, text.get_rect(center=rect.center))
            else:
                label_surface = self.font_medium.render(label, True, color)
                self.screen.blit(label_surface, (rect.x + 14, rect.y + 6))
                value = f"< {self._value_text(key)} >"
                value_surface = self.font_medium.render(value, True, color)
                self.screen.blit(value_surface, (rect.right - value_surface.get_width() - 14, rect.y + 6))

        hint = self.font_small.render(
            "Arrows to navigate/change - R rerolls the seed - Enter to confirm - Esc to go back",
            True, self.hint_color,
        )
        self.screen.blit(hint, hint.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 50)))
