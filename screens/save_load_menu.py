"""Multi-slot Save / Load screen (§8.2).

Reached from the pause menu (Save/Load tabs) and the main menu (load only).
One click on a slot performs the current action directly — no separate
confirm button (user-reported: "hover the slot, then hunt for the button"
was confusing). Each slot shows when it was written (date + time) and a
one-line match summary, elided to fit; the caller performs the actual load
with the returned slot number.
"""
import pygame

from core.config import SCREEN_WIDTH, SCREEN_HEIGHT
from managers.save_manager import SaveManager
from screens import theme


class SaveLoadScreen:
    """`game` present -> in-game (Save + Load tabs). `game` None -> load-only."""

    def __init__(self, screen, game=None):
        if not pygame.font.get_init():
            pygame.font.init()
        self.screen = screen
        self.game = game
        self.can_save = game is not None
        self.title = "Save / Load" if self.can_save else "Load Game"

        self.slots = list(range(SaveManager.SLOT_COUNT))
        self.selected = 0
        # Active tab: saving is the default from the pause menu — loading
        # throws away the current match, so it takes a deliberate tab switch.
        self.mode = "save" if self.can_save else "load"
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
    SLOT_HEIGHT = 58
    SLOT_PITCH = 68

    def _tabs_height(self):
        return 52 if self.can_save else 0

    def _panel_rect(self):
        h = 96 + self._tabs_height() + len(self.slots) * self.SLOT_PITCH + 84
        return pygame.Rect(SCREEN_WIDTH // 2 - 320, (SCREEN_HEIGHT - h) // 2, 640, h)

    def _tab_rects(self):
        if not self.can_save:
            return {}
        panel = self._panel_rect()
        w, gap = 150, 12
        x = panel.centerx - w - gap // 2
        y = panel.y + 88
        return {
            "save": pygame.Rect(x, y, w, 40),
            "load": pygame.Rect(x + w + gap, y, w, 40),
        }

    def _slot_rect(self, i):
        panel = self._panel_rect()
        top = panel.y + 96 + self._tabs_height()
        return pygame.Rect(panel.x + 40, top + i * self.SLOT_PITCH,
                           panel.width - 80, self.SLOT_HEIGHT)

    def _back_rect(self):
        panel = self._panel_rect()
        return pygame.Rect(panel.centerx - 75, panel.bottom - 64, 150, 46)

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

    def _set_mode(self, mode):
        if mode != self.mode:
            self.mode = mode
            self._play_click()

    def _handle(self, event):
        if event.type == pygame.QUIT:
            self.running = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.running = False
            elif event.key == pygame.K_UP:
                self.selected = (self.selected - 1) % len(self.slots)
            elif event.key == pygame.K_DOWN:
                self.selected = (self.selected + 1) % len(self.slots)
            elif event.key == pygame.K_TAB and self.can_save:
                self._set_mode("load" if self.mode == "save" else "save")
            elif event.key == pygame.K_s and self.can_save:
                self._set_mode("save")
            elif event.key == pygame.K_l and self.can_save:
                self._set_mode("load")
            elif event.key == pygame.K_RETURN:
                self._activate_slot(self.selected)
        elif event.type == pygame.MOUSEMOTION:
            for i in range(len(self.slots)):
                if self._slot_rect(i).collidepoint(event.pos):
                    self.selected = i
                    break
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            pos = event.pos
            for name, rect in self._tab_rects().items():
                if rect.collidepoint(pos):
                    self._set_mode(name)
                    return
            for i in range(len(self.slots)):
                if self._slot_rect(i).collidepoint(pos):
                    self.selected = i
                    self._activate_slot(i)  # one click does the deed
                    return
            if self._back_rect().collidepoint(pos):
                self.running = False

    def _play_click(self):
        sm = getattr(self.game, "sound_manager", None)
        if sm:
            sm.play_ui_click()

    # -- actions ------------------------------------------------------------ #
    def _activate_slot(self, index):
        self.selected = index
        if self.mode == "save":
            self._do_save()
        else:
            self._do_load()

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
    @staticmethod
    def _elide(text, font, max_width):
        """`text`, cut with an ellipsis to render within max_width."""
        if max_width <= 0 or font.size(text)[0] <= max_width:
            return text
        while text and font.size(text + "…")[0] > max_width:
            text = text[:-1]
        return text + "…"

    def draw(self):
        panel = self._panel_rect()
        theme.draw_menu_scene(self.screen, self.title, panel)
        mouse = pygame.mouse.get_pos()

        for name, rect in self._tab_rects().items():
            label = "Save" if name == "save" else "Load"
            active = self.mode == name
            theme.draw_action_row(self.screen, rect, label,
                                  active or rect.collidepoint(mouse),
                                  self.font_btn, primary=active)

        for i, slot in enumerate(self.slots):
            rect = self._slot_rect(i)
            selected = (i == self.selected)
            theme._draw_row_chrome(self.screen, rect, "selected" if selected else "normal")

            # Text stays inside the frame art's ornate end caps
            left = rect.x + 30
            right = rect.right - 30

            name = self.font_slot.render(f"Slot {slot + 1}", True,
                                         theme.VALUE_COLOR if selected else theme.LABEL_COLOR)
            self.screen.blit(name, (left, rect.y + 7))

            meta = self._meta.get(slot)
            if meta:
                # Right column: date on top, time below — always fits
                date = self.font_meta.render(meta.get("date", ""), True, theme.LABEL_COLOR)
                time_text = self.font_meta.render(meta.get("time", ""), True, theme.MUTED_COLOR)
                self.screen.blit(date, (right - date.get_width(), rect.y + 10))
                self.screen.blit(time_text, (right - time_text.get_width(), rect.y + 31))
                # Summary elides against the date column so it never overlaps
                date_col = max(date.get_width(), time_text.get_width())
                summary = self._elide(meta["summary"], self.font_meta,
                                      right - date_col - 16 - left)
                self.screen.blit(
                    self.font_meta.render(summary, True, theme.MUTED_COLOR),
                    (left, rect.y + 33))
            else:
                empty = self.font_meta.render("— Empty —", True, theme.MUTED_COLOR)
                self.screen.blit(empty, (right - empty.get_width(), rect.y + 19))

        theme.draw_action_row(self.screen, self._back_rect(), "Back",
                              self._back_rect().collidepoint(mouse), self.font_btn)

        hint_y = min(panel.bottom + 20, self.screen.get_height() - 16)
        if self._toast:
            text, expire = self._toast
            if pygame.time.get_ticks() < expire:
                theme.draw_hint(self.screen, text, y=hint_y)
            else:
                self._toast = None
        else:
            action = "save to" if self.mode == "save" else "load"
            hint = f"Click a slot to {action} it   ·   Enter confirms   ·   Esc back"
            if self.can_save:
                hint += "   ·   Tab switches Save/Load"
            theme.draw_hint(self.screen, hint, y=hint_y)
