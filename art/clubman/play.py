"""Open a playable match with six selected clubmen already at your base."""
import json
import os
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
import pygame
from core.game import Game
from core.config import MAP_VIEW_WIDTH, MAP_VIEW_HEIGHT


def main():
    random.seed(4321)
    game = Game(mode='human_1v1', player_count=2)
    castle = next(b for b in game.buildings if b.name == 'castle' and b.player.human)
    data = next(u for u in json.loads((ROOT / 'data/units.json').read_text()) if u['name'] == 'warrior')
    for _ in range(6):
        castle.current_production = {'unit_type': 'warrior', 'unit_data': data}
        game.production_manager._complete_production(castle)
        # The demo creates multiple units in one frame; refresh spawn occupancy.
        game.collision_system._rebuild_unit_index()
    worker_data = next(u for u in json.loads((ROOT / 'data/units.json').read_text()) if u['name'] == 'worker')
    for _ in range(2):
        castle.current_production = {'unit_type': 'worker', 'unit_data': worker_data}
        game.production_manager._complete_production(castle)
        # The demo creates multiple units in one frame; refresh spawn occupancy.
        game.collision_system._rebuild_unit_index()
    clubmen = [u for u in game.units if u.name == 'warrior' and u.player.human]
    for unit in clubmen:
        unit.selected = True
    game.selection_manager.selected_objects = clubmen
    game.selection_manager.control_groups[1] = list(clubmen)
    game.selection_manager.control_groups[2] = [u for u in game.units if u.name == 'worker' and u.player.human]
    for group, name in [(3, 'archer'), (4, 'spearman'), (5, 'healer')]:
        unit_data = next(u for u in json.loads((ROOT / 'data/units.json').read_text()) if u['name'] == name)
        for _ in range(2):
            castle.current_production = {'unit_type': name, 'unit_data': unit_data}
            game.production_manager._complete_production(castle)
            game.collision_system._rebuild_unit_index()
        game.selection_manager.control_groups[group] = [u for u in game.units if u.name == name and u.player.human]
    # Let the normal collision system separate freshly spawned units before display.
    for _ in range(20):
        game.update(delta_time_override=1 / 60)
    game.camera.zoom = 1.5
    game.game_map.scale_tiles(game.camera.zoom)
    game.camera.x = MAP_VIEW_WIDTH / 2 - castle.x * game.camera.zoom
    game.camera.y = MAP_VIEW_HEIGHT / 2 - castle.y * game.camera.zoom
    pygame.display.set_caption('RTS - Outlined Infantry Prototype')
    game.rendering_system.draw_frame(game.screen, game.map_surface, game.camera, 1 / 60)
    pygame.display.flip()
    pygame.image.save(game.screen, str(ROOT / 'art/clubman/gameplay.png'))
    print('READY: Outlined units; group 1 = six clubmen; group 2 = workers; 3 = slingshots; 4 = wooden spears; 5 = healers; right-click to move/work.', flush=True)
    try:
        game.run()
    finally:
        pygame.quit()


if __name__ == '__main__':
    main()
