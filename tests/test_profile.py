"""Persistent profile + achievements (§8.7)."""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

from core.profile import Profile, ACHIEVEMENTS


@pytest.fixture()
def game():
    random.seed(4321)
    from core.game import Game

    return Game(mode="human_1v1", player_count=2)


def seed_match_stats(game, gathered=500, trained=12, built=6):
    human = game.players[0]
    game.stats_resources_gathered[human.name] = gathered
    game.stats_units_trained[(human.name, "worker")] = trained
    game.stats_buildings_built[(human.name, "house")] = built
    return human


def test_record_match_accumulates_and_persists(game, tmp_path):
    path = str(tmp_path / "profile.json")
    human = seed_match_stats(game)

    profile = Profile(path=path)
    unlocked = profile.record_match(game, human, won=True)
    assert ("first_win", "First Victory") in unlocked

    fresh = Profile(path=path)  # "restart"
    assert fresh.stats["matches_played"] == 1
    assert fresh.stats["matches_won"] == 1
    assert fresh.stats["units_trained"] == 12
    assert fresh.stats["buildings_built"] == 6
    assert fresh.stats["resources_gathered"] == 500
    assert "first_win" in fresh.achievements

    # Second win: first_win must NOT unlock again
    unlocked = fresh.record_match(game, human, won=True)
    assert all(ach_id != "first_win" for ach_id, _ in unlocked)
    assert fresh.stats["matches_played"] == 2


def test_lifetime_achievements_unlock_at_thresholds(game, tmp_path):
    human = seed_match_stats(game, gathered=9600, trained=95, built=48)
    profile = Profile(path=str(tmp_path / "p.json"))
    profile.record_match(game, human, won=False)  # below every threshold
    assert "economist" not in profile.achievements

    seed_match_stats(game, gathered=500, trained=10, built=5)
    unlocked = dict(profile.record_match(game, human, won=False))
    assert "economist" in unlocked  # 10,100 lifetime
    assert "warlord" in unlocked    # 105 lifetime
    assert "master_builder" in unlocked  # 53 lifetime
    assert "first_win" not in profile.achievements  # never won


def test_blitz_requires_fast_win(game, tmp_path):
    human = seed_match_stats(game)
    profile = Profile(path=str(tmp_path / "p.json"))

    game.sim_time_elapsed = 900.0  # 15 minutes: too slow
    profile.record_match(game, human, won=True)
    assert "blitz" not in profile.achievements

    game.sim_time_elapsed = 300.0  # 5 minutes
    unlocked = dict(profile.record_match(game, human, won=True))
    assert "blitz" in unlocked


def test_game_over_records_once(game, tmp_path, monkeypatch):
    import core.profile as profile_module

    monkeypatch.setattr(profile_module, "PROFILE_FILE", str(tmp_path / "profile.json"))
    human = seed_match_stats(game)

    game.game_over_state = "victory"
    game._record_match_result()
    game._record_match_result()  # second call must be a no-op

    profile = Profile(path=str(tmp_path / "profile.json"))
    assert profile.stats["matches_played"] == 1
    # The unlock toast reached the alert feed
    assert any("Achievement unlocked" in text for text, _ in game.ui_manager.alerts)


def test_corrupt_profile_ignored(tmp_path):
    path = tmp_path / "profile.json"
    path.write_text('{"stats": {"matches_played": "many"}, "achievements": {"fake": 1}, oops')
    profile = Profile(path=str(path))
    assert profile.stats["matches_played"] == 0
    assert profile.achievements == {}
    assert set(ACHIEVEMENTS) >= set(profile.achievements)
