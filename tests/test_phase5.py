import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class MockGameMap:
    def __init__(self):
        self.width = 50
        self.height = 50
        self.grid = [["grass"] * 50 for _ in range(50)]
    
    def world_to_grid(self, wx, wy):
        col = int(wx / 40)
        row = int(wy / 40)
        if 0 <= col < self.width and 0 <= row < self.height:
            return (col, row)
        return None
    
    def grid_to_world(self, c, r):
        return (c * 40, r * 40)


class MockPlayer:
    def __init__(self, human=True):
        self.human = human
        self.name = "Test"
        self.color = (255, 255, 255)
        self.resources = {}
        self.ai_personality = "balanced"


class MockGame:
    def __init__(self):
        self.units = []
        self.buildings = []
        self.resources = []
        self.construction_sites = []
        self.players = [MockPlayer(human=True), MockPlayer(human=False)]
        self.game_map = MockGameMap()


# ---------------------------------------------------------------------------
# Fog of War Tests
# ---------------------------------------------------------------------------
class TestFogOfWar:
    def test_fog_initializes_grids(self):
        from systems.fog_of_war import FogOfWar
        game = MockGame()
        fog = FogOfWar(game)
        assert len(fog.visibility_grid) == 2
    
    def test_unexplored_by_default(self):
        from systems.fog_of_war import FogOfWar
        game = MockGame()
        fog = FogOfWar(game)
        human = game.players[0]
        assert fog.get_tile_state(human, 0, 0) == fog.UNEXPLORED
    
    def test_object_visibility_own_always_visible(self):
        from systems.fog_of_war import FogOfWar
        from entities.unit import Unit
        game = MockGame()
        fog = FogOfWar(game)
        unit = Unit("worker", [1,1], 100, 40, 0, {}, radius=10, player=game.players[0])
        assert fog.is_object_visible(unit) is True
    
    def test_visibility_marks_nearby_tiles(self):
        from systems.fog_of_war import FogOfWar
        from entities.unit import Unit
        game = MockGame()
        fog = FogOfWar(game)
        human = game.players[0]
        
        # Place a unit at center
        unit = Unit("worker", [1,1], 100, 40, 0, {}, radius=10, player=game.players[0])
        unit.x = 500
        unit.y = 500
        game.units.append(unit)
        
        fog.update()
        
        # Tiles near the unit should be explored
        tile_state = fog.get_tile_state(human, 12, 12)  # ~500/40 = 12.5
        assert tile_state == fog.VISIBLE
    
    def test_exploration_stays_after_visibility_fades(self):
        from systems.fog_of_war import FogOfWar
        from entities.unit import Unit
        game = MockGame()
        fog = FogOfWar(game)
        human = game.players[0]
        
        unit = Unit("worker", [1,1], 100, 40, 0, {}, radius=10, player=game.players[0])
        unit.x = 100
        unit.y = 100
        game.units.append(unit)
        
        fog.update()
        first_state = fog.get_tile_state(human, 2, 2)
        assert first_state == fog.VISIBLE
        
        # Remove unit and update
        game.units.remove(unit)
        fog.update()
        second_state = fog.get_tile_state(human, 2, 2)
        assert second_state == fog.EXPLORED  # Should remain explored

    def test_disabled_fog_makes_everything_visible(self):
        from systems.fog_of_war import FogOfWar
        from entities.unit import Unit
        game = MockGame()
        game.fog_of_war_enabled = False
        fog = FogOfWar(game)
        human = game.players[0]
        enemy_unit = Unit("worker", [1, 1], 100, 40, 0, {}, radius=10, player=game.players[1])
        enemy_unit.x = 1600
        enemy_unit.y = 1600

        assert fog.get_tile_state(human, 0, 0) == fog.VISIBLE
        assert fog.is_visible(human, enemy_unit.x, enemy_unit.y) is True
        assert fog.is_object_visible(enemy_unit) is True
        assert fog.get_exploration_percent(human) == 100.0

    def test_selection_ignores_hidden_resource_targets(self):
        from managers.selection_manager import SelectionManager
        from entities.resource import Resource

        game = MockGame()
        hidden_resource = Resource("wood", None, x=100, y=100, radius=16)
        game.resources.append(hidden_resource)

        class HiddenFog:
            enabled = True

            def is_object_visible(self, obj):
                return False

        game.fog_of_war = HiddenFog()

        selection = SelectionManager(game)

        assert selection._get_object_at_position((100, 100)) is None

    def test_selection_allows_visible_resource_targets(self):
        from managers.selection_manager import SelectionManager
        from entities.resource import Resource

        game = MockGame()
        visible_resource = Resource("wood", None, x=100, y=100, radius=16)
        game.resources.append(visible_resource)

        class VisibleFog:
            enabled = True

            def is_object_visible(self, obj):
                return True

        game.fog_of_war = VisibleFog()

        selection = SelectionManager(game)

        assert selection._get_object_at_position((100, 100)) is visible_resource

    def test_main_menu_initializes_font_if_needed(self):
        import pygame
        from screens.main_menu import MainMenu

        pygame.font.quit()
        MainMenu(screen=None)

        assert pygame.font.get_init() is True


# ---------------------------------------------------------------------------
# Particle System Tests
# ---------------------------------------------------------------------------
class TestParticleSystem:
    def test_particle_initialization(self):
        from systems.particle_system import ParticleSystem
        game = MockGame()
        ps = ParticleSystem(game)
        assert len(ps.particles) == 0
    
    def test_spawn_attack_particles(self):
        from systems.particle_system import ParticleSystem
        game = MockGame()
        ps = ParticleSystem(game)
        ps.spawn_attack_particles(100, 100, count=5)
        assert len(ps.particles) == 5
        assert all(p.alive for p in ps.particles)
    
    def test_spawn_death_particles(self):
        from systems.particle_system import ParticleSystem
        game = MockGame()
        ps = ParticleSystem(game)
        ps.spawn_death_particles(100, 100, count=8)
        assert len(ps.particles) == 8
    
    def test_particle_ages_and_dies(self):
        from systems.particle_system import ParticleSystem
        game = MockGame()
        ps = ParticleSystem(game)
        ps.spawn_attack_particles(100, 100, count=3)
        
        # Age them past their lifetime
        ps.update(1.0)
        assert len(ps.particles) == 0
    
    def test_particle_spawn_types(self):
        from systems.particle_system import ParticleSystem
        game = MockGame()
        ps = ParticleSystem(game)
        ps.spawn_build_particles(100, 100)
        assert len(ps.particles) == 5
        ps.spawn_gather_particles(100, 100)
        assert len(ps.particles) == 7  # 5 + 2


# ---------------------------------------------------------------------------
# Sound Manager Tests
# ---------------------------------------------------------------------------
class TestSoundManager:
    def test_sound_manager_has_sounds(self):
        # We can't easily test pygame mixer without display, but check file structure
        assert os.path.exists("managers/sound_manager.py")
    
    def test_sound_manager_methods_exist(self):
        with open("managers/sound_manager.py") as f:
            source = f.read()
        assert "play_attack" in source
        assert "play_death" in source
        assert "play_select" in source
        assert "play_build_complete" in source


# ---------------------------------------------------------------------------
# Utility AI Wiring Tests
# ---------------------------------------------------------------------------
class TestUtilityAIWiring:
    def test_ai_package_exports_only_live_orchestrator(self):
        import systems.ai as ai_package
        from systems.ai import UtilityAISystem

        assert UtilityAISystem.__name__ == "UtilityAISystem"
        assert ai_package.__all__ == ["UtilityAISystem"]
        assert not hasattr(ai_package, "SimpleAISystem")


# ---------------------------------------------------------------------------
# Fog of War Rendering Tests
# ---------------------------------------------------------------------------
class TestFogRendering:
    def test_rendering_has_fog_method(self):
        with open("systems/rendering_system.py") as f:
            source = f.read()
        assert "_draw_fog_overlay" in source
        assert "fog_of_war" in source


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
