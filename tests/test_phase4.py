import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# Damage Notification Tests
# ---------------------------------------------------------------------------
class TestDamageNotifications:
    def test_floating_ui_has_damage_method(self):
        # We can't easily instantiate FloatingUI without pygame, but we can check the method exists
        import ast
        with open("ui/floating_ui.py") as f:
            tree = ast.parse(f.read())
        
        methods = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
        assert "add_damage_notification" in methods
    
    def test_combat_system_triggers_damage_notifications(self):
        import ast
        with open("systems/combat_system.py") as f:
            tree = ast.parse(f.read())
        
        source = ast.dump(tree)
        assert "damage_events" in source
        assert "add_damage_notification" in source


# ---------------------------------------------------------------------------
# Screen Shake Tests
# ---------------------------------------------------------------------------
class TestScreenShake:
    def test_camera_has_shake_attributes(self):
        from world.camera import Camera
        cam = Camera(800, 600)
        assert hasattr(cam, "shake_amount")
        assert hasattr(cam, "shake_decay")
        assert cam.shake_amount == 0.0
    
    def test_camera_add_shake(self):
        from world.camera import Camera
        cam = Camera(800, 600)
        cam.add_shake(10.0)
        assert cam.shake_amount == 10.0
        cam.add_shake(5.0)
        assert cam.shake_amount == 10.0  # Max behavior
    
    def test_camera_shake_decays(self):
        from world.camera import Camera
        cam = Camera(800, 600)
        cam.add_shake(10.0)
        offset = cam.update_shake(0.5)  # Half second
        assert cam.shake_amount < 10.0
        assert cam.shake_amount > 0
    
    def test_camera_shake_returns_zero_when_inactive(self):
        from world.camera import Camera
        cam = Camera(800, 600)
        offset = cam.update_shake(1.0)
        assert offset == (0, 0)


# ---------------------------------------------------------------------------
# Main Menu Tests
# ---------------------------------------------------------------------------
class TestMainMenu:
    def test_main_menu_file_exists(self):
        assert os.path.exists("screens/main_menu.py")
    
    def test_main_menu_has_run_method(self):
        import ast
        with open("screens/main_menu.py") as f:
            tree = ast.parse(f.read())
        methods = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
        assert "run" in methods
    
    def test_main_menu_has_correct_options(self):
        import ast
        with open("screens/main_menu.py") as f:
            source = f.read()
        assert "Start Game" in source
        assert "Load Game" in source
        assert "Exit" in source


# ---------------------------------------------------------------------------
# Main Entry Point Tests
# ---------------------------------------------------------------------------
class TestMainEntry:
    def test_main_py_imports_menu(self):
        import ast
        with open("main.py") as f:
            source = f.read()
        assert "MainMenu" in source
        assert "SaveManager" in source


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
