"""HUD alert feed (§7.4): toasts, pings, throttling, low-resource dips."""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest


@pytest.fixture(scope="module")
def game():
    random.seed(4321)
    from core.game import Game

    return Game(mode="human_1v1", player_count=2)


def test_alert_appends_and_pings(game):
    ui = game.ui_manager
    ui.alerts.clear()
    pings_before = len(game.minimap._pings)

    assert ui.add_alert("Test alert", world_pos=(500, 500))
    assert [text for text, _ in ui.alerts] == ["Test alert"]
    assert len(game.minimap._pings) == pings_before + 1


def test_alert_throttling(game):
    ui = game.ui_manager
    ui.alerts.clear()
    ui._alert_last.clear()

    assert ui.add_alert("Once", throttle_key="k", throttle_ms=60000)
    assert not ui.add_alert("Twice", throttle_key="k", throttle_ms=60000)
    assert len(ui.alerts) == 1


def test_low_resource_dip_alerts_once(game):
    ui = game.ui_manager
    ui.alerts.clear()
    ui._alert_last.clear()
    human = game.players[0]

    game._last_resource_snapshot = {"wood": 200}
    human.resources["wood"] = 10
    game._low_resource_timer = 0.0
    game._check_low_resources(1.5)
    assert any("Low on wood" in text for text, _ in ui.alerts)

    # Staying low does not re-alert (no dip, plus throttle)
    ui.alerts.clear()
    game._check_low_resources(1.5)
    assert ui.alerts == []


def test_draw_alerts_prunes_expired(game):
    ui = game.ui_manager
    surface = pygame.Surface((1280, 720))

    now = pygame.time.get_ticks()
    ui.alerts = [("fresh", now), ("stale", now - ui.ALERT_DURATION_MS - 1)]
    ui.draw_alerts(surface)
    assert [text for text, _ in ui.alerts] == ["fresh"]
