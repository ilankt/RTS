"""§8.12 batch 3: ram cap, squad interleave, radius-aware bounds, towers."""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")


def _ram_ctx(rams, army_size):
    military = [SimpleNamespace(name="ram")] * rams + \
               [SimpleNamespace(name="warrior")] * (army_size - rams)
    return SimpleNamespace(
        has_pop_space=lambda: True,
        can_afford=lambda name: True,
        find_idle_production_building=lambda name: object(),
        military=military,
        enemy_buildings=[SimpleNamespace(name="castle")],
    )


def test_ram_cap_scales_with_army():
    from systems.ai.utility.goals.military import TrainRamGoal

    goal = TrainRamGoal()
    assert goal.score(_ram_ctx(rams=2, army_size=8)) > 0     # under cap
    assert goal.score(_ram_ctx(rams=3, army_size=8)) == 0    # min-cap hit, no filler
    assert goal.score(_ram_ctx(rams=5, army_size=24)) > 0    # 25% of 24 = 6
    assert goal.score(_ram_ctx(rams=6, army_size=24)) == 0   # proportional cap


def test_squads_interleave_unit_types():
    from systems.ai.military_brain import MilitaryBrain

    brain = MilitaryBrain(game=SimpleNamespace())

    class P:  # hashable (used as a dict key for the squad cursor)
        name = "AI"

    player = P()
    # Production order: 5 rams then 5 warriors — old chunking made a pure-ram squad
    army = [SimpleNamespace(name="ram", id=i) for i in range(5)] + \
           [SimpleNamespace(name="warrior", id=i) for i in range(5)]
    squad = brain._next_squad(player, army)
    names = {u.name for u in squad}
    assert names == {"ram", "warrior"}, "squads must mix fighters with siege"


def test_ai_placement_bounds_are_radius_aware():
    import random
    random.seed(5150)
    from core.game import Game
    from systems.ai.utility.context import GoalContext

    game = Game(mode="ai_spectator", player_count=2)
    game.fog_of_war_enabled = False  # isolate the bounds check from fog
    try:
        placer = game.ai_system.building_placer
        ctx = GoalContext.build(game, game.players[0])
        radius = game.game_data["buildings"]["castle"].radius
        assert not placer._is_valid_position(radius - 10, 500, "castle", ctx), \
            "a castle center this close to the edge sticks out of the world"
    finally:
        game.fog_of_war_enabled = True


def test_second_tower_needs_no_pressure_third_does():
    from systems.ai.utility.goals.military import BuildWatchtowerGoal

    def ctx_with(towers):
        return SimpleNamespace(
            game=SimpleNamespace(is_building_disabled=lambda name: False),
            castle=SimpleNamespace(x=0, y=0),
            workers=[object()] * 4,
            can_afford=lambda name: True,
            has_construction_in_progress=lambda name: False,
            buildings={"watchtower": [SimpleNamespace(x=0, y=0)] * towers},
            threat_at=lambda x, y: 0.0,  # NO pressure anywhere
            player=SimpleNamespace(ai_personality="balanced"),
        )

    goal = BuildWatchtowerGoal()
    assert goal.score(ctx_with(0)) > 0
    assert goal.score(ctx_with(1)) > 0, "tower #2 guards the economy, no pressure needed"
    assert goal.score(ctx_with(2)) == 0, "tower #3 requires actual pressure"
