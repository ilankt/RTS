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
    clubmen = [u for u in game.units if u.name == 'warrior' and u.player.human]
    for unit in clubmen:
        unit.selected = True
    game.selection_manager.selected_objects = clubmen
    game.selection_manager.control_groups[1] = list(clubmen)
    game.camera.zoom = 1.5
    game.camera.x = MAP_VIEW_WIDTH / 2 - castle.x * game.camera.zoom
    game.camera.y = MAP_VIEW_HEIGHT / 2 - castle.y * game.camera.zoom
    pygame.display.set_caption('RTS - Clubman Prototype (separate fork)')
    game.rendering_system.draw_frame(game.screen, game.map_surface, game.camera, 1 / 60)
    pygame.display.flip()
    pygame.image.save(game.screen, str(ROOT / 'art/clubman/gameplay.png'))
    print('READY: Clubman prototype gameplay; six selected clubmen; right-click to move; group 1 recalls them.', flush=True)
    try:
        game.run()
    finally:
        pygame.quit()


if __name__ == '__main__':
    main()

