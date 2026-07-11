"""Match setup screen (MASTER_PLAN §7.5).

Lets the player configure a skirmish before starting: play or spectate,
opponent count, AI personality, map seed, and game speed. Returns a config
dict, or None if the player backs out.
"""
import random

import pygame

from core.config import SCREEN_WIDTH, SCREEN_HEIGHT, MAP_SIZES
from screens import theme

PERSONALITY_CHOICES = ["random", "balanced", "rusher", "boomer", "turtle"]
MUTATOR_CHOICES = ["none", "double_resources", "no_towers", "revealed_map",
                   "random_events", "comeback"]
MAP_SIZE_CHOICES = list(MAP_SIZES)  # tiny .. huge, in declared order


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
            "map_size": "medium",     # tiny..huge; caps the player count
            "personality": "random",  # applied to every AI, or random per AI
            "difficulty": "normal",   # easy | normal | hard (§7.2 honest tiers)
            "victory": "annihilation",  # annihilation | economic | timed (§7.5)
            "mutator": "none",          # §7.5 match modifiers
            "seed": random.randint(1, 99999),
        }
        self.rows = [
            ("Mode", "mode"),
            ("Map size", "map_size"),
            ("Opponents", "opponents"),
            ("AI personality", "personality"),
            ("AI difficulty", "difficulty"),
            ("Victory", "victory"),
            ("Mutator", "mutator"),
            ("Map seed", "seed"),
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
    def _max_opponents(self):
        """Small maps cap the head count — no 8-player brawls on Tiny."""
        _tiles, max_players = MAP_SIZES[self.config["map_size"]]
        return max_players - 1

    def _adjust(self, key, direction):
        if key == "mode":
            self.config["mode"] = "spectate" if self.config["mode"] == "play" else "play"
        elif key == "map_size":
            index = MAP_SIZE_CHOICES.index(self.config["map_size"])
            self.config["map_size"] = MAP_SIZE_CHOICES[(index + direction) % len(MAP_SIZE_CHOICES)]
            # Shrinking the map clamps the opponent count to what fits
            self.config["opponents"] = min(self.config["opponents"], self._max_opponents())
        elif key == "opponents":
            self.config["opponents"] = max(1, min(self._max_opponents(),
                                                  self.config["opponents"] + direction))
        elif key == "personality":
            index = PERSONALITY_CHOICES.index(self.config["personality"])
            self.config["personality"] = PERSONALITY_CHOICES[(index + direction) % len(PERSONALITY_CHOICES)]
        elif key == "difficulty":
            choices = ["easy", "normal", "hard"]
            index = choices.index(self.config["difficulty"])
            self.config["difficulty"] = choices[(index + direction) % len(choices)]
        elif key == "victory":
            choices = ["annihilation", "economic", "timed"]
            index = choices.index(self.config["victory"])
            self.config["victory"] = choices[(index + direction) % len(choices)]
        elif key == "mutator":
            index = MUTATOR_CHOICES.index(self.config["mutator"])
            self.config["mutator"] = MUTATOR_CHOICES[(index + direction) % len(MUTATOR_CHOICES)]
        elif key == "seed":
            self.config["seed"] = max(0, self.config["seed"] + direction)

    def _value_text(self, key):
        if key == "mode":
            return "Play (you vs AI)" if self.config["mode"] == "play" else "Spectate (AI vs AI)"
        if key == "map_size":
            _tiles, max_players = MAP_SIZES[self.config["map_size"]]
            return f"{self.config['map_size'].title()} (up to {max_players} players)"
        if key == "opponents":
            return str(self.config["opponents"])
        if key == "personality":
            return self.config["personality"].title()
        if key == "difficulty":
            return self.config["difficulty"].title()
        if key == "victory":
            return self.config["victory"].title()
        if key == "mutator":
            return self.config["mutator"].replace("_", " ").title()
        if key == "seed":
            return str(self.config["seed"])
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
                if event.type == pygame.MOUSEMOTION:
                    # Hover moves the ONE selection (no keyboard/mouse
                    # double highlight)
                    for i in range(len(self.rows)):
                        if self._row_rect(i).collidepoint(event.pos):
                            self.selected_index = i
                            break
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
    ROWS_TOP_OFFSET = 88   # first row's offset inside the panel
    ROW_PITCH = 48
    ROW_W = 530

    def _panel_rect(self):
        height = self.ROWS_TOP_OFFSET + len(self.rows) * self.ROW_PITCH + 36
        top = max(12, (SCREEN_HEIGHT - height) // 2)
        return pygame.Rect(SCREEN_WIDTH // 2 - 320, top, 640, height)

    def _row_rect(self, index):
        panel = self._panel_rect()
        y = panel.y + self.ROWS_TOP_OFFSET + index * self.ROW_PITCH
        if index >= len(self.rows) - 2:
            y += 10  # breathe before the Start/Back actions
        return pygame.Rect(SCREEN_WIDTH // 2 - self.ROW_W // 2, y,
                           self.ROW_W, self.ROW_PITCH - 6)

    def draw(self):
        theme.draw_menu_scene(self.screen, "Match Setup", self._panel_rect())

        for i, (label, key) in enumerate(self.rows):
            rect = self._row_rect(i)
            selected = i == self.selected_index
            if key is None:
                theme.draw_action_row(self.screen, rect, label, selected,
                                      self.font_medium,
                                      primary=(label == "Start match"))
            else:
                theme.draw_setting_row(self.screen, rect, label,
                                       self._value_text(key), selected,
                                       self.font_medium)

        theme.draw_hint(
            self.screen,
            "Arrows navigate/change · R rerolls the seed · Enter confirms · Esc backs out",
        )
