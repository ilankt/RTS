"""Onboarding tips (§8.7): timed hints for new players only."""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest


def make_game(tmp_path, monkeypatch, matches_played):
    import core.profile as profile_module
    from core.profile import Profile

    path = str(tmp_path / "profile.json")
    monkeypatch.setattr(profile_module, "PROFILE_FILE", path)
    profile = Profile(path=path)
    profile.stats["matches_played"] = matches_played
    profile.save()

    random.seed(4321)
    from core.game import Game

    return Game(mode="human_1v1", player_count=2)


def test_new_player_gets_timed_tips(tmp_path, monkeypatch):
    game = make_game(tmp_path, monkeypatch, matches_played=0)
    assert game._onboarding_queue  # tips queued for a fresh profile

    game.ui_manager.alerts.clear()
    game.sim_time_elapsed = game.ONBOARDING_HINTS[0][0] + 1
    game._update_onboarding()
    assert any(text.startswith("Tip:") for text, _ in game.ui_manager.alerts)

    # One tip per due time, not the whole queue at once
    remaining = len(game._onboarding_queue)
    assert remaining == len(game.ONBOARDING_HINTS) - 1


def test_experienced_player_gets_no_tips(tmp_path, monkeypatch):
    game = make_game(tmp_path, monkeypatch, matches_played=10)
    assert game._onboarding_queue == []

    game.ui_manager.alerts.clear()
    game.sim_time_elapsed = 9999
    game._update_onboarding()
    assert game.ui_manager.alerts == []


def test_spectator_matches_get_no_tips(tmp_path, monkeypatch):
    import core.profile as profile_module

    monkeypatch.setattr(profile_module, "PROFILE_FILE", str(tmp_path / "p.json"))
    random.seed(4321)
    from core.game import Game

    game = Game(mode="ai_spectator", player_count=2)
    assert game._onboarding_queue == []
