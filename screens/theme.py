"""Shared menu styling (§8.2 menu polish): one visual language for every
screen — splash-art backdrop, dark scrim panels, gold titles with drop
shadows, and label/value rows with adjuster arrows.
"""
import pygame

from core.config import SCREEN_WIDTH, SCREEN_HEIGHT

SPLASH_PATH = "assets/ui/splash_background.png"
_splash_cache = {}  # (w, h) -> cover-scaled surface

TITLE_COLOR = (222, 195, 110)
TITLE_SHADOW = (12, 12, 12)
LABEL_COLOR = (218, 218, 218)
VALUE_COLOR = (235, 210, 140)
MUTED_COLOR = (150, 150, 150)
SELECTED_FILL = (62, 56, 36)
SELECTED_BORDER = (228, 202, 118)
ROW_FILL = (255, 255, 255, 12)
PANEL_FILL = (13, 13, 23, 215)
PANEL_BORDER = (105, 92, 55)
PRIMARY_FILL = (38, 74, 44)
PRIMARY_BORDER = (120, 200, 130)


def splash_background(size=None):
    """The splash art cover-scaled + center-cropped to `size` (defaults to
    the screen). Returns None if the art is missing."""
    size = size or (SCREEN_WIDTH, SCREEN_HEIGHT)
    cached = _splash_cache.get(size)
    if cached is not None:
        return cached
    try:
        art = pygame.image.load(SPLASH_PATH).convert()
    except Exception:
        return None
    width, height = size
    scale = max(width / art.get_width(), height / art.get_height())
    scaled = pygame.transform.smoothscale(
        art, (int(art.get_width() * scale) + 1, int(art.get_height() * scale) + 1))
    surface = pygame.Surface(size)
    surface.blit(scaled, ((width - scaled.get_width()) // 2,
                          (height - scaled.get_height()) // 2))
    _splash_cache[size] = surface
    return surface


def draw_splash(screen, caption=None):
    """Full-screen splash with an optional caption — used as the loading
    screen while a match is being generated."""
    background = splash_background(screen.get_size())
    if background is not None:
        screen.blit(background, (0, 0))
        overlay = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
        overlay.fill((10, 10, 20, 90))
        screen.blit(overlay, (0, 0))
    else:
        screen.fill((20, 20, 30))
    if caption:
        font = pygame.font.Font(None, 40)
        text = font.render(caption, True, (240, 225, 170))
        rect = text.get_rect(center=(screen.get_width() // 2,
                                     screen.get_height() - 80))
        draw_text_backdrop(screen, rect)
        screen.blit(text, rect)
    pygame.display.flip()


def draw_text_backdrop(screen, rect, alpha=150):
    backdrop = rect.inflate(30, 14)
    panel = pygame.Surface(backdrop.size, pygame.SRCALPHA)
    panel.fill((0, 0, 0, alpha))
    screen.blit(panel, backdrop.topleft)


def draw_panel(screen, rect):
    """Rounded scrim panel with a subtle gold border."""
    panel = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(panel, PANEL_FILL, panel.get_rect(), border_radius=16)
    pygame.draw.rect(panel, (*PANEL_BORDER, 200), panel.get_rect(), 2,
                     border_radius=16)
    screen.blit(panel, rect.topleft)


def draw_menu_scene(screen, title, panel_rect):
    """Splash backdrop + scrim panel + shadowed gold title inside its top."""
    background = splash_background(screen.get_size())
    if background is not None:
        screen.blit(background, (0, 0))
    else:
        screen.fill((20, 20, 30))
    draw_panel(screen, panel_rect)

    font = pygame.font.Font(None, 56)
    shadow = font.render(title, True, TITLE_SHADOW)
    text = font.render(title, True, TITLE_COLOR)
    rect = text.get_rect(center=(panel_rect.centerx, panel_rect.y + 44))
    screen.blit(shadow, rect.move(2, 2))
    screen.blit(text, rect)


def _arrow(screen, x, y, direction, color):
    """Small left/right adjuster triangle."""
    half = 6
    if direction < 0:
        points = [(x + half, y - half), (x + half, y + half), (x - half, y)]
    else:
        points = [(x - half, y - half), (x - half, y + half), (x + half, y)]
    pygame.draw.polygon(screen, color, points)


def draw_setting_row(screen, rect, label, value, selected, font):
    """Label left, value right; selected rows get adjuster arrows."""
    row = pygame.Surface(rect.size, pygame.SRCALPHA)
    if selected:
        pygame.draw.rect(row, (*SELECTED_FILL, 235), row.get_rect(), border_radius=8)
        pygame.draw.rect(row, SELECTED_BORDER, row.get_rect(), 2, border_radius=8)
    else:
        pygame.draw.rect(row, ROW_FILL, row.get_rect(), border_radius=8)
    screen.blit(row, rect.topleft)

    label_surface = font.render(label, True,
                                LABEL_COLOR if selected else MUTED_COLOR)
    screen.blit(label_surface, (rect.x + 18,
                                rect.centery - label_surface.get_height() // 2))

    value_surface = font.render(value, True,
                                VALUE_COLOR if selected else LABEL_COLOR)
    value_x = rect.right - 40 - value_surface.get_width()
    screen.blit(value_surface, (value_x,
                                rect.centery - value_surface.get_height() // 2))
    if selected:
        _arrow(screen, value_x - 16, rect.centery, -1, SELECTED_BORDER)
        _arrow(screen, rect.right - 24, rect.centery, 1, SELECTED_BORDER)


def draw_action_row(screen, rect, label, selected, font, primary=False):
    """Centered action button (Start / Back / Resume...)."""
    row = pygame.Surface(rect.size, pygame.SRCALPHA)
    if primary:
        fill = (*PRIMARY_FILL, 245) if selected else (*PRIMARY_FILL, 170)
        border = PRIMARY_BORDER if selected else (90, 140, 95)
    else:
        fill = (*SELECTED_FILL, 235) if selected else ROW_FILL
        border = SELECTED_BORDER if selected else (90, 90, 95)
    pygame.draw.rect(row, fill, row.get_rect(), border_radius=8)
    pygame.draw.rect(row, border, row.get_rect(), 2 if selected else 1,
                     border_radius=8)
    screen.blit(row, rect.topleft)

    color = (240, 240, 220) if selected or primary else LABEL_COLOR
    text = font.render(label, True, color)
    screen.blit(text, text.get_rect(center=rect.center))


def draw_hint(screen, text, y=None):
    font = pygame.font.Font(None, 24)
    surface = font.render(text, True, (185, 185, 185))
    rect = surface.get_rect(center=(screen.get_width() // 2,
                                    y if y is not None else screen.get_height() - 34))
    draw_text_backdrop(screen, rect, alpha=140)
    screen.blit(surface, rect)
