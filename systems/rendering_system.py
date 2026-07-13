import pygame
from core.config import TILE_WIDTH, TOP_BAR_HEIGHT, SCREEN_WIDTH, SCREEN_HEIGHT, MINIMAP_WIDTH, MINIMAP_HEIGHT
from entities import Building, Unit, Resource, ConstructionSite
from utils.perf_stats import perf_stats


class RenderingSystem:
    """Handles drawing and visual rendering of game objects"""
    
    def __init__(self, game):
        self.game = game
        self.sprite_manager = game.sprite_manager
        self.selection_manager = game.selection_manager
        self.floating_ui = game.floating_ui
        self.building_system = game.building_system
        
        # Colors
        self.DARK_GRAY = (40, 40, 40)
        self.MAP_GRAY = (60, 60, 60)

        # Cached fog tile surfaces keyed by (width, height, alpha)
        self._fog_tile_cache = {}
        # Cached scaled object sprites keyed by (id(sprite), width, height)
        self._scaled_sprite_cache = {}
        # Per-unit visual scale from units.json (render_scale): normalizes
        # perceived size across art styles (thin realistic sheets vs chunky
        # cartoons) without touching collision or gameplay size
        self._render_scales = {}
        try:
            import json
            with open('data/units.json') as f:
                for unit in json.load(f):
                    scale = unit.get('render_scale')
                    if scale:
                        self._render_scales[unit['name']] = float(scale)
        except (OSError, ValueError):
            pass

        # Ornate frame art (the four-sided banner) reused border-only to frame
        # the map + minimap, matching the top-bar/sidebar look. Falls back to a
        # drawn bevel if the art is missing.
        from ui.hud_background import NineSliceFrame
        self.hud_frame = NineSliceFrame("assets/ui/hud_top_bar.png",
                                        src_inset=(105, 100, 105, 100),
                                        dst_inset=(24, 24, 24, 24))

        # §8.5 death fades: brief alpha-fading ghosts of freshly dead units/
        # buildings (no death sprite sheets exist). Capped so headless sims —
        # which never draw and therefore never age the list — can't grow it.
        self._death_fades = []
        self._DEATH_FADE_MAX = 32
        self._DEATH_FADE_S = 1.1
    
    def draw_frame(self, screen, map_surface, camera, delta_time=1/60.0):
        """Draw a complete frame"""
        # Update camera shake
        shake_offset = camera.update_shake(delta_time)
        
        # Temporarily apply shake to camera
        camera.x += shake_offset[0]
        camera.y += shake_offset[1]
        
        # Clear backgrounds
        screen.fill(self.DARK_GRAY)
        map_surface.fill(self.MAP_GRAY)
        
        # Draw map
        self.game.game_map.draw(map_surface, camera)

        # §8.5: fading corpses lie under the living
        self._draw_death_fades(map_surface, camera, delta_time)

        # Draw all game objects
        self._draw_all_objects(map_surface, camera)
        
        # Draw UI overlays
        self._draw_ui_overlays(map_surface, camera)
        
        # Draw building preview
        if self.building_system.building_placement_mode:
            self.building_system.draw_building_preview(map_surface, camera)
        
        # Draw fog of war overlay
        self._draw_fog_overlay(map_surface, camera)

        # HP/construction bars + floats go ABOVE the fog overlay so they are
        # never dimmed by a fog-tile edge (user-reported dark bars at max zoom)
        self.floating_ui.draw_all_floating_ui(map_surface, camera, delta_time)

        # Instant command feedback rings (§7.4)
        self._draw_order_flashes(map_surface, camera)

        # Restore camera position after shake
        camera.x -= shake_offset[0]
        camera.y -= shake_offset[1]
        
        # Blit map to screen
        screen.blit(map_surface, (0, TOP_BAR_HEIGHT))
        
        # Draw UI panels
        self.game.minimap.draw(screen)
        self.game.ui_manager.draw_ui_panel(screen)
        self.game.ui_manager.draw_top_bar(screen)
        self._draw_map_border(screen)
        self.game.ui_manager.draw_alerts(screen)
        self.game.ui_manager.draw_event_log(screen)
        self.game.ai_debug_panel.draw(screen)

    @staticmethod
    def _draw_beveled_frame(screen, rect):
        """A beveled wood-and-iron border drawn inside `rect`: outer dark lip,
        wood body, warm highlight, inner shadow line. Matches the panel art so
        the map and minimap read as framed viewports, not bare black edges."""
        pygame.draw.rect(screen, (20, 17, 13), rect, 9)
        pygame.draw.rect(screen, (92, 66, 40), rect.inflate(-4, -4), 5)
        pygame.draw.rect(screen, (140, 104, 62), rect.inflate(-4, -4), 1)
        pygame.draw.rect(screen, (32, 24, 16), rect.inflate(-16, -16), 2)

    def _draw_map_border(self, screen):
        """Frame the play area and the minimap with the ornate frame art
        (border only, transparent centre), falling back to a drawn bevel."""
        map_rect = pygame.Rect(0, TOP_BAR_HEIGHT,
                               SCREEN_WIDTH - MINIMAP_WIDTH,
                               SCREEN_HEIGHT - TOP_BAR_HEIGHT)
        mini_rect = pygame.Rect(SCREEN_WIDTH - MINIMAP_WIDTH, 0,
                                MINIMAP_WIDTH, MINIMAP_HEIGHT)
        map_border = self.hud_frame.render_border(map_rect.width, map_rect.height)
        # Thinner frame on the small minimap so it doesn't swallow the map.
        mini_border = self.hud_frame.render_border(mini_rect.width, mini_rect.height,
                                                   dst_inset=(16, 16, 16, 16))
        if map_border is not None:
            screen.blit(map_border, map_rect.topleft)
            screen.blit(mini_border, mini_rect.topleft)
        else:
            self._draw_beveled_frame(screen, map_rect)
            self._draw_beveled_frame(screen, mini_rect)

    ORDER_FLASH_MS = 450
    ORDER_FLASH_COLORS = {
        "move": (90, 255, 120),
        "attack": (255, 90, 90),
        "gather": (255, 210, 80),
        "rally": (130, 190, 255),
    }

    def _draw_order_flashes(self, map_surface, camera):
        """Shrinking ring at each recent order target (§7.4)."""
        flashes = getattr(self.game, "order_flashes", None)
        if not flashes:
            return
        now = pygame.time.get_ticks()
        alive = []
        for x, y, kind, started in flashes:
            age = now - started
            if age > self.ORDER_FLASH_MS:
                continue
            alive.append((x, y, kind, started))
            progress = age / self.ORDER_FLASH_MS
            radius = max(3, int((26 - 20 * progress) * camera.zoom))
            color = self.ORDER_FLASH_COLORS.get(kind, (255, 255, 255))
            pygame.draw.circle(
                map_surface, color,
                (int(x * camera.zoom + camera.x), int(y * camera.zoom + camera.y)),
                radius, 2,
            )
        self.game.order_flashes = alive

    def add_death_fade(self, obj, sprite):
        """§8.5: register a just-died object's sprite to fade out in place."""
        if sprite is None:
            return
        if len(self._death_fades) >= self._DEATH_FADE_MAX:
            self._death_fades.pop(0)
        self._death_fades.append({
            "sprite": sprite,
            "x": obj.x, "y": obj.y,
            "size": tuple(getattr(obj, "size", (1, 1))),
            "name": getattr(obj, "name", None),
            "facing_left": getattr(obj, "facing_left", False),
            "age": 0.0,
        })

    def _draw_death_fades(self, map_surface, camera, delta_time):
        if not self._death_fades:
            return
        alive = []
        for fade in self._death_fades:
            fade["age"] += delta_time
            if fade["age"] >= self._DEATH_FADE_S:
                continue
            alive.append(fade)
            sprite = fade["sprite"]
            sprite_w, sprite_h = sprite.get_size()
            scale = (fade["size"][0] * TILE_WIDTH) / sprite_w
            scale *= self._render_scales.get(fade["name"], 1.0)
            width = max(1, int(sprite_w * scale * camera.zoom))
            height = max(1, int(sprite_h * scale * camera.zoom))
            key = (sprite, width, height, fade["facing_left"])
            scaled = self._scaled_sprite_cache.get(key)
            if scaled is None:
                scaled = pygame.transform.scale(sprite, (width, height))
                if fade["facing_left"]:
                    scaled = pygame.transform.flip(scaled, True, False)
                self._scaled_sprite_cache[key] = scaled
            # Per-frame copy so alpha never sticks to the cached surface
            ghost = scaled.copy()
            ghost.set_alpha(int(255 * (1.0 - fade["age"] / self._DEATH_FADE_S)))
            draw_x = (fade["x"] * camera.zoom) + camera.x - width / 2
            draw_y = (fade["y"] * camera.zoom) + camera.y - height / 2
            map_surface.blit(ghost, (draw_x, draw_y))
        self._death_fades = alive

    def _draw_all_objects(self, map_surface, camera):
        """Draw visible game objects (frustum-culled, fog-filtered, y-sorted)"""
        zoom = camera.zoom
        left = -camera.x / zoom
        right = (-camera.x + map_surface.get_width()) / zoom
        top = -camera.y / zoom
        bottom = (-camera.y + map_surface.get_height()) / zoom

        fog = getattr(self.game, 'fog_of_war', None)

        visible = []
        for group in (
            self.game.resources,
            self.game.buildings,
            self.game.units,
            self.game.construction_sites,
        ):
            for obj in group:
                # Sprites are centered on (x, y) with world extents from size
                # (in tiles); pad generously so we never cull a drawn sprite.
                margin = max(obj.radius, obj.size[0] * 32, obj.size[1] * 28) + 8
                if (
                    obj.x + margin < left
                    or obj.x - margin > right
                    or obj.y + margin < top
                    or obj.y - margin > bottom
                ):
                    continue
                if fog and not fog.is_object_visible(obj):
                    continue
                visible.append(obj)

        visible.sort(key=lambda obj: obj.y)
        for obj in visible:
            self._draw_object(obj, map_surface, camera)

        # §8.5 movement dust: fast movers kick up puffs at their feet.
        # Draw-time hook on purpose — visible units only, zero sim cost in
        # headless runs; throttled + jittered per unit.
        particles = getattr(self.game, 'particles', None)
        if particles:
            frame = self.game.frame_counter
            for obj in visible:
                if (getattr(obj, 'status', None) == 'run'
                        and getattr(obj, 'movement_speed', 0) >= 55
                        and frame >= getattr(obj, '_next_dust_frame', 0)):
                    obj._next_dust_frame = frame + 14 + (id(obj) % 8)
                    particles.spawn_move_dust(obj.x, obj.y + obj.radius * 0.5)
    
    def _draw_object(self, obj, map_surface, camera):
        """Draw a single game object"""
        draw_x = (obj.x * camera.zoom) + camera.x
        draw_y = (obj.y * camera.zoom) + camera.y

        sprite_to_draw = self._get_object_sprite(obj)

        if sprite_to_draw:
            self._render_sprite(sprite_to_draw, obj, draw_x, draw_y, camera, map_surface)

        # §8.5 staged construction: the finished building rises out of the
        # site as progress advances (bottom slice grows with progress).
        if isinstance(obj, ConstructionSite):
            self._draw_construction_stage(obj, draw_x, draw_y, camera, map_surface)

    def _draw_construction_stage(self, site, draw_x, draw_y, camera, map_surface):
        duration = getattr(site, 'construction_duration', 0) or 1
        progress = min(1.0, getattr(site, 'construction_progress', 0) / duration)
        if progress < 0.12:
            return  # bare foundation until work meaningfully starts
        try:
            player_index = self.game.players.index(site.player)
        except (ValueError, AttributeError):
            return
        sprite = self.sprite_manager.get_building_sprite(site.building_name, player_index)
        if sprite is None:
            return
        sprite_w, sprite_h = sprite.get_size()
        scale = (site.size[0] * TILE_WIDTH) / sprite_w
        width = max(1, int(sprite_w * scale * camera.zoom))
        height = max(1, int(sprite_h * scale * camera.zoom))
        key = (sprite, width, height, False)
        scaled = self._scaled_sprite_cache.get(key)
        if scaled is None:
            if len(self._scaled_sprite_cache) > 2048:
                self._scaled_sprite_cache.clear()
            scaled = pygame.transform.scale(sprite, (width, height))
            self._scaled_sprite_cache[key] = scaled
        # Bottom slice, proportional to progress, anchored at the sprite's base
        slice_h = max(1, int(height * progress))
        src = pygame.Rect(0, height - slice_h, width, slice_h)
        blit_x = draw_x - width / 2
        blit_y = draw_y - height / 2 + (height - slice_h)
        map_surface.blit(scaled, (blit_x, blit_y), area=src)
    
    def _get_object_sprite(self, obj):
        """Get the appropriate sprite for an object"""
        sprite_to_draw = None
        
        if isinstance(obj, Building):
            player_index = self.game.players.index(obj.player)
            sprite_to_draw = self.sprite_manager.get_building_sprite(obj.name, player_index)
        elif isinstance(obj, Resource):
            sprite_to_draw = self.sprite_manager.get_resource_sprite(obj.name)
        elif isinstance(obj, Unit):
            sprite_to_draw = obj.get_current_sprite()
        elif isinstance(obj, ConstructionSite):
            # Use construction sprite with player tinting
            player_index = self.game.players.index(obj.player)
            sprite_to_draw = self.sprite_manager.get_building_sprite("construction", player_index)
        
        return sprite_to_draw
    
    def _render_sprite(self, sprite, obj, draw_x, draw_y, camera, map_surface):
        """Render a sprite at the specified position (scaled copies cached).
        Units walking/facing left draw mirrored — the sheets face right."""
        sprite_w, sprite_h = sprite.get_size()
        scale = (obj.size[0] * TILE_WIDTH) / sprite_w
        scale *= self._render_scales.get(getattr(obj, 'name', None), 1.0)
        scaled_width = int(sprite_w * scale * camera.zoom)
        scaled_height = int(sprite_h * scale * camera.zoom)
        mirrored = getattr(obj, 'facing_left', False)

        # Only transform if necessary; cache per (sprite, size, mirrored)
        if (scaled_width, scaled_height) != (sprite_w, sprite_h) or mirrored:
            key = (sprite, scaled_width, scaled_height, mirrored)
            scaled_sprite = self._scaled_sprite_cache.get(key)
            if scaled_sprite is None:
                if len(self._scaled_sprite_cache) > 2048:
                    self._scaled_sprite_cache.clear()
                scaled_sprite = sprite
                if (scaled_width, scaled_height) != (sprite_w, sprite_h):
                    scaled_sprite = pygame.transform.scale(scaled_sprite, (scaled_width, scaled_height))
                if mirrored:
                    scaled_sprite = pygame.transform.flip(scaled_sprite, True, False)
                self._scaled_sprite_cache[key] = scaled_sprite
        else:
            scaled_sprite = sprite

        blit_x = draw_x - (scaled_width / 2)
        blit_y = draw_y - (scaled_height / 2)

        map_surface.blit(scaled_sprite, (blit_x, blit_y))
    
    def _draw_ui_overlays(self, map_surface, camera):
        """Draw UI overlays on the map surface"""
        # Draw selection circles
        self.selection_manager.draw_selection_circles(map_surface, camera)
        
        # Draw attack target indicators
        self.selection_manager.draw_attack_targets(map_surface, camera)
        
        # Draw LOS debug visualization
        self.selection_manager.draw_los_debug(map_surface, camera)
        
        # Draw unit paths (debug mode only)
        self.selection_manager.draw_unit_paths(map_surface, camera)
        
        # Draw selection box if active
        self.selection_manager.draw_selection_box(map_surface)
        
        # Draw projectiles
        if hasattr(self.game, 'projectile_system') and self.game.projectile_system:
            self.game.projectile_system.draw(map_surface, camera)
        
        # Draw particles
        if hasattr(self.game, 'particles') and self.game.particles:
            self.game.particles.draw(map_surface, camera)
    
    def draw_debug_info(self, screen, font=None):
        """Draw debug information on screen"""
        if not self.game.debug_overlay:
            return
            
        if font is None:
            font = pygame.font.Font(None, 24)
        
        debug_info = []
        debug_info.append(f"FPS: {self.game.clock.get_fps():.1f}")
        debug_info.append(f"Units: {len(self.game.units)}")
        debug_info.append(f"Buildings: {len(self.game.buildings)}")
        debug_info.append(f"Resources: {len(self.game.resources)}")
        debug_info.append(f"Construction Sites: {len(self.game.construction_sites)}")
        debug_info.append(f"Camera Zoom: {self.game.camera.zoom:.2f}")
        debug_info.append(f"Camera Pos: ({self.game.camera.x:.1f}, {self.game.camera.y:.1f})")
        debug_info.append(f"Game Speed: {getattr(self.game, 'game_speed', 1.0):.1f}x")
        fog_state = "ON" if getattr(self.game, "fog_of_war_enabled", True) else "OFF"
        debug_info.append(f"Fog of War: {fog_state} (F6)")
        if perf_stats.enabled:
            summary = perf_stats.summary()
            debug_info.append(
                f"Update ms avg/p95/max: {summary['frame_avg_ms']:.1f}/"
                f"{summary['frame_p95_ms']:.1f}/{summary['frame_max_ms']:.1f}"
            )
            debug_info.append(
                f"Path req/A*/hit: {summary['path_requests']}/"
                f"{summary['astar_calls']}/{summary['path_cache_hits']}"
            )
            debug_info.append(
                f"A* cells/caps: {summary['astar_expanded_cells']}/"
                f"{summary['astar_capped']}"
            )
            debug_info.append(f"Collision checks: {summary['collision_checks']}")
        
        # Draw debug text
        y_offset = 10
        for line in debug_info:
            text_surface = font.render(line, True, (255, 255, 0))
            screen.blit(text_surface, (10, y_offset))
            y_offset += 25
    
    def draw_grid_overlay(self, map_surface, camera):
        """Draw grid overlay for debugging"""
        if not self.game.debug_overlay:
            return
            
        # Draw pathfinding grid
        from core.config import GRID_SIZE
        grid_color = (100, 100, 100, 128)
        
        # Calculate visible grid range
        start_x = int(-camera.x / camera.zoom / GRID_SIZE) - 1
        end_x = int((-camera.x + map_surface.get_width()) / camera.zoom / GRID_SIZE) + 1
        start_y = int(-camera.y / camera.zoom / GRID_SIZE) - 1
        end_y = int((-camera.y + map_surface.get_height()) / camera.zoom / GRID_SIZE) + 1
        
        # Draw vertical lines
        for x in range(start_x, end_x):
            screen_x = x * GRID_SIZE * camera.zoom + camera.x
            if 0 <= screen_x <= map_surface.get_width():
                pygame.draw.line(map_surface, grid_color, 
                               (screen_x, 0), (screen_x, map_surface.get_height()))
        
        # Draw horizontal lines
        for y in range(start_y, end_y):
            screen_y = y * GRID_SIZE * camera.zoom + camera.y
            if 0 <= screen_y <= map_surface.get_height():
                pygame.draw.line(map_surface, grid_color,
                               (0, screen_y), (map_surface.get_width(), screen_y))
    
    def draw_object_bounds(self, map_surface, camera):
        """Draw bounding circles for all objects"""
        if not self.game.debug_overlay:
            return
            
        all_objects = (self.game.units + self.game.buildings + 
                      self.game.resources + self.game.construction_sites)
        
        for obj in all_objects:
            # Calculate screen position
            screen_x = int(obj.x * camera.zoom + camera.x)
            screen_y = int(obj.y * camera.zoom + camera.y)
            radius = int(obj.radius * camera.zoom)
            
            # Choose color based on object type
            if isinstance(obj, Unit):
                color = (0, 255, 0)  # Green for units
            elif isinstance(obj, Building):
                color = (0, 0, 255)  # Blue for buildings
            elif isinstance(obj, Resource):
                color = (255, 255, 0)  # Yellow for resources
            else:
                color = (255, 0, 255)  # Magenta for construction sites
            
            # Draw circle (only if visible)
            if (screen_x + radius >= 0 and screen_x - radius <= map_surface.get_width() and
                screen_y + radius >= 0 and screen_y - radius <= map_surface.get_height()):
                pygame.draw.circle(map_surface, color, (screen_x, screen_y), radius, 1)
    
    def _draw_fog_overlay(self, map_surface, camera):
        """Draw fog of war overlay for the human player."""
        fog = getattr(self.game, 'fog_of_war', None)
        if not fog or not fog.enabled:
            return
        
        human = self.game.players[0] if self.game.players else None
        if not human:
            return
        
        tile_width = int(TILE_WIDTH * camera.zoom)
        tile_height = int(TILE_WIDTH * camera.zoom * 0.875)
        
        # Determine visible tile range
        start_col = max(0, int(-camera.x / (tile_width * 0.75)) - 1)
        end_col = min(self.game.game_map.width, int((-camera.x + map_surface.get_width()) / (tile_width * 0.75)) + 1)
        start_row = max(0, int(-camera.y / tile_height) - 1)
        end_row = min(self.game.game_map.height, int((-camera.y + map_surface.get_height()) / tile_height) + 1)
        
        for row in range(start_row, end_row):
            for col in range(start_col, end_col):
                state = fog.get_tile_state(human, row, col)
                
                if state == fog.UNEXPLORED:
                    # Completely black
                    alpha = 255
                elif state == fog.EXPLORED:
                    # Semi-transparent black
                    alpha = 150
                else:
                    continue  # VISIBLE - no overlay
                
                x = col * tile_width * 0.75
                y = row * tile_height
                if col % 2 != 0:
                    y += tile_height / 2
                
                screen_x = x + camera.x
                screen_y = y + camera.y

                # Slightly larger rect to cover tile seams; surface cached per
                # (size, alpha) instead of allocated per tile per frame. The
                # map's last column/row get wider rects: their hex images
                # overhang where no neighbor's fog covers them (hidden under
                # the 720p sidebar, visible at higher resolutions).
                fog_w = int(tile_width * 0.75) + 2
                fog_h = int(tile_height) + 2
                if col == self.game.game_map.width - 1:
                    fog_w = int(tile_width) + 2
                if row == self.game.game_map.height - 1:
                    fog_h = int(tile_height * 1.5) + 2
                key = (fog_w, fog_h, alpha)
                fog_surface = self._fog_tile_cache.get(key)
                if fog_surface is None:
                    fog_surface = pygame.Surface((key[0], key[1]), pygame.SRCALPHA)
                    fog_surface.fill((0, 0, 0, alpha))
                    self._fog_tile_cache[key] = fog_surface
                map_surface.blit(fog_surface, (int(screen_x) - 1, int(screen_y) - 1))
    
    def get_visible_objects(self, camera, map_surface):
        """Get all objects that are currently visible on screen"""
        visible_objects = []
        
        # Calculate visible bounds
        left = -camera.x / camera.zoom
        right = (-camera.x + map_surface.get_width()) / camera.zoom
        top = -camera.y / camera.zoom
        bottom = (-camera.y + map_surface.get_height()) / camera.zoom
        
        all_objects = (self.game.units + self.game.buildings + 
                      self.game.resources + self.game.construction_sites)
        
        for obj in all_objects:
            # Check if object is within visible bounds (with some margin for object size)
            margin = obj.radius
            if (obj.x + margin >= left and obj.x - margin <= right and
                obj.y + margin >= top and obj.y - margin <= bottom):
                visible_objects.append(obj)
        
        return visible_objects
    
    def is_position_visible(self, position, camera, map_surface):
        """Check if a position is visible on screen"""
        screen_x = position[0] * camera.zoom + camera.x
        screen_y = position[1] * camera.zoom + camera.y
        
        return (0 <= screen_x <= map_surface.get_width() and
                0 <= screen_y <= map_surface.get_height())
