"""Multi-slot Save / Load screen (§8.2).

Reached from the pause menu (save + load) and the main menu (load only).
Shows every slot with its timestamp and a one-line summary; the caller
performs the actual load with the returned slot number.
"""
import pygame

from core.config import SCREEN_WIDTH, SCREEN_HEIGHT
from managers.save_manager import SaveManager
from screens import theme


class SaveLoadScreen:
    """`game` present -> in-game (Save allowed). `game` None -> load-only."""

    def __init__(self, screen, game=None):
        if not pygame.font.get_init():
            pygame.font.init()
        self.screen = screen
        self.game = game
        self.can_save = game is not None
        self.title = "Save / Load" if self.can_save else "Load Game"

        self.slots = list(range(SaveManager.SLOT_COUNT))
        self.selected = 0
        self.result = None          # slot int to load, or None
        self.running = True

        self.font_slot = pygame.font.Font(None, 34)
        self.font_meta = pygame.font.Font(None, 24)
        self.font_btn = pygame.font.Font(None, 32)
        self._meta = {}
        self._toast = None          # (text, expire_ms)
        self._refresh_meta()

    def _refresh_meta(self):
        self._meta = {s: SaveManager.slot_meta(s) for s in self.slots}

    # -- geometry ----------------------------------------------------------- #
    def _panel_rect(self):
        h = 120 + len(self.slots) * 66 + 90
        return pygame.Rect(SCREEN_WIDTH // 2 - 320, (SCREEN_HEIGHT - h) // 2, 640, h)

    def _slot_rect(self, i):
        panel = self._panel_rect()
        return pygame.Rect(panel.x + 40, panel.y + 96 + i * 66, panel.width - 80, 56)

    def _button_rects(self):
        panel = self._panel_rect()
        y = panel.bottom - 66
        labels = (["Save", "Load", "Back"] if self.can_save else ["Load", "Back"])
        gap, bw = 16, 150
        total = len(labels) * bw + (len(labels) - 1) * gap
        x = panel.centerx - total // 2
        rects = {}
        for label in labels:
            rects[label] = pygame.Rect(x, y, bw, 46)
            x += bw + gap
        return rects

    # -- loop --------------------------------------------------------------- #
    def run(self):
        clock = pygame.time.Clock()
        while self.running:
            for event in pygame.event.get():
                self._handle(event)
            self.draw()
            pygame.display.flip()
            clock.tick(60)
        return self.result

    def _handle(self, event):
        if event.type == pygame.QUIT:
            self.running = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.running = False
            elif event.key in (pygame.K_UP, pygame.K_w):
                self.selected = (self.selected - 1) % len(self.slots)
            elif event.key == pygame.K_DOWN:  # not W/S — S is the save shortcut
                self.selected = (self.selected + 1) % len(self.slots)
            elif event.key == pygame.K_s and self.can_save:
                self._do_save()
            elif event.key in (pygame.K_RETURN, pygame.K_l):
                self._do_load()
        elif event.type == pygame.MOUSEMOTION:
            for i in range(len(self.slots)):
                if self._slot_rect(i).collidepoint(event.pos):
                    self.selected = i
                    break
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            pos = event.pos
            for i in range(len(self.slots)):
                if self._slot_rect(i).collidepoint(pos):
                    self.selected = i
                    return
            buttons = self._button_rects()
            if "Save" in buttons and buttons["Save"].collidepoint(pos):
                self._do_save()
            elif buttons["Load"].collidepoint(pos):
                self._do_load()
            elif buttons["Back"].collidepoint(pos):
                self.running = False

    def _play_click(self):
        sm = getattr(self.game, "sound_manager", None)
        if sm:
            sm.play_ui_click()

    def _do_save(self):
        if not self.can_save:
            return
        slot = self.slots[self.selected]
        try:
            SaveManager.save_game(self.game, slot=slot)
            self._toast = (f"Saved to Slot {slot + 1}", pygame.time.get_ticks() + 1800)
            self._refresh_meta()
            self._play_click()
        except Exception:
            self._toast = ("Save failed", pygame.time.get_ticks() + 1800)

    def _do_load(self):
        slot = self.slots[self.selected]
        if self._meta.get(slot) is None:
            self._toast = ("That slot is empty", pygame.time.get_ticks() + 1500)
            return
        self._play_click()
        self.result = slot
        self.running = False

    # -- draw --------------------------------------------------------------- #
    def draw(self):
        panel = self._panel_rect()
        theme.draw_menu_scene(self.screen, self.title, panel)

        for i, slot in enumerate(self.slots):
            rect = self._slot_rect(i)
            selected = (i == self.selected)
            theme._draw_row_chrome(self.screen, rect, "selected" if selected else "normal")

            name = self.font_slot.render(f"Slot {slot + 1}", True,
                                         theme.VALUE_COLOR if selected else theme.LABEL_COLOR)
            self.screen.blit(name, (rect.x + 24, rect.y + 6))

            meta = self._meta.get(slot)
            if meta:
                summ = self.font_meta.render(meta["summary"], True, theme.MUTED_COLOR)
                self.screen.blit(summ, (rect.x + 24, rect.y + 32))
                when = self.font_meta.render(meta["when"], True, theme.MUTED_COLOR)
                self.screen.blit(when, (rect.right - 24 - when.get_width(), rect.y + 18))
            else:
                empty = self.font_meta.render("— Empty —", True, theme.MUTED_COLOR)
                self.screen.blit(empty, (rect.right - 24 - empty.get_width(), rect.y + 18))

        mouse = pygame.mouse.get_pos()
        for label, rect in self._button_rects().items():
            primary = label == ("Save" if self.can_save else "Load")
            theme.draw_action_row(self.screen, rect, label,
                                  rect.collidepoint(mouse), self.font_btn, primary=primary)

        if self._toast:
            text, expire = self._toast
            if pygame.time.get_ticks() < expire:
                theme.draw_hint(self.screen, text, y=panel.bottom - 14)
            else:
                self._toast = None
        else:
            hint = ("Up/Down select   ·   S save   ·   Enter load   ·   Esc back"
                    if self.can_save
                    else "Up/Down select   ·   Enter load   ·   Esc back")
            theme.draw_hint(self.screen, hint, y=panel.bottom - 14)
