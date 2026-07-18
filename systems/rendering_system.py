import math
import pygame
from core.config import TILE_WIDTH, TILE_HEIGHT, TOP_BAR_HEIGHT, SCREEN_WIDTH, SCREEN_HEIGHT, MINIMAP_WIDTH, MINIMAP_HEIGHT
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
        self._fog_overlay = None  # §8.14: shared per-frame hex fog canvas
        # Cached scaled object sprites keyed by (id(sprite), width, height)
        self._scaled_sprite_cache = {}
        # Per-object visual scale from JSON (render_scale): normalizes
        # perceived size across art styles (thin realistic sheets vs chunky
        # cartoons) without touching collision or gameplay size. Buildings
        # register their construction-site alias too, so a rescaled tower's
        # foundation shrinks with it (§8.2.2 user report: watchtower drew a
        # third wider than everything else, temple undersized).
        self._render_scales = {}
        try:
            import json
            with open('data/units.json') as f:
                for unit in json.load(f):
                    scale = unit.get('render_scale')
                    if scale:
                        self._render_scales[unit['name']] = float(scale)
            with open('data/buildings.json') as f:
                for building in json.load(f):
                    scale = building.get('render_scale')
                    if scale:
                        self._render_scales[building['name']] = float(scale)
                        self._render_scales[f"{building['name']}_construction"] = float(scale)
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

        # §8.9: fountain healing auras lie under everything alive
        self._draw_fountain_auras(map_surface, camera)

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
        self.floating_ui.draw_all_floating_ui(map_surface, camera)

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
        # The hover tooltip draws truly last (§8.2.2): it flies out over the
        # map area, and the ornate map border used to overpaint its right
        # edge because "last" was only last within draw_ui_panel.
        self.game.ui_manager.command_card.draw_tooltip(screen)

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

    def _draw_fountain_auras(self, map_surface, camera):
        """§8.9 (user request): show the healing range — a soft pulsing blue
        disc + rim at FOUNTAIN_HEAL_RADIUS. Surfaces cached per (size, pulse
        step) so the per-frame cost is one blit per fountain."""
        fountains = getattr(self.game, 'fountains', None)
        if not fountains:
            return
        from systems.fountain_system import FOUNTAIN_HEAL_RADIUS

        pulse_step = (self.game.frame_counter // 12) % 8  # ~0.2s per step
        cache = getattr(self, '_aura_cache', None)
        if cache is None:
            cache = self._aura_cache = {}
        for fountain in fountains:
            radius_px = max(8, int(FOUNTAIN_HEAL_RADIUS * camera.zoom))
            key = (radius_px, pulse_step)
            aura = cache.get(key)
            if aura is None:
                if len(cache) > 64:
                    cache.clear()
                size = radius_px * 2 + 4
                aura = pygame.Surface((size, size), pygame.SRCALPHA)
                center = size // 2
                pulse = 1.0 + 0.06 * math.sin(pulse_step / 8.0 * 2 * math.pi)
                rim = max(6, int(radius_px * pulse) - 2)
                pygame.draw.circle(aura, (90, 170, 255, 22), (center, center), radius_px)
                pygame.draw.circle(aura, (130, 200, 255, 60), (center, center), rim, 2)
                cache[key] = aura
            screen_x = (fountain.x * camera.zoom) + camera.x
            screen_y = (fountain.y * camera.zoom) + camera.y
            map_surface.blit(aura, (screen_x - aura.get_width() / 2,
                                    screen_y - aura.get_height() / 2))

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
        # Static neutrals (resources, fountains) draw once EXPLORED, like
        # their minimap dots — they can't move, so the memory stays true.
        # Everything else needs current line of sight.
        explored_check = getattr(fog, "is_display_explored", None)

        # Ghosts of resources depleted out of sight lie under everything
        if fog is not None:
            self._draw_resource_ghosts(map_surface, camera, left, right, top, bottom)

        visible = []
        for group, is_static_neutral in (
            (self.game.resources, True),
            (getattr(self.game, "fountains", ()), True),
            (self.game.buildings, False),
            (self.game.units, False),
            (self.game.construction_sites, False),
        ):
            for obj in group:
                # Sprites are centered on (x, y) with world extents from size
                # (in tiles); pad generously so we never cull a drawn sprite.
                # Height budget uses the full drawn width (size[0]*64): tall
                # sprites (watchtower) extend far above center, and the old
                # tighter margin culled their construction fade-in whenever
                # the site center slipped just off-screen (§8.2.2 bug 7).
                margin = max(obj.radius, obj.size[0] * 64, obj.size[1] * 56) + 8
                if (
                    obj.x + margin < left
                    or obj.x - margin > right
                    or obj.y + margin < top
                    or obj.y - margin > bottom
                ):
                    continue
                if fog is not None:
                    if is_static_neutral and explored_check is not None:
                        if not explored_check(obj.x, obj.y):
                            continue
                    elif not fog.is_object_visible(obj):
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
                elif (obj.__class__.__name__ == "Fountain"
                        and frame >= getattr(obj, '_next_sparkle_frame', 0)):
                    obj._next_sparkle_frame = frame + 18
                    particles.spawn_fountain_sparkles(obj.x, obj.y - 14)
    
    GHOST_ALPHA = 130  # remembered-but-gone resources draw see-through

    def _draw_resource_ghosts(self, map_surface, camera, left, right, top, bottom):
        """Resources that were depleted OUT of the viewer's sight keep
        drawing (translucent) where last seen; FogOfWar prunes each ghost
        the moment its tile is actually revealed."""
        fog = self.game.fog_of_war
        ghosts = getattr(fog, "resource_ghosts", None)
        # Fog off / revealed display shows the true world — no false memories
        if not ghosts or not getattr(fog, "enabled", True) or getattr(fog, "reveal_display", False):
            return
        for ghost in ghosts.values():
            x, y = ghost["x"], ghost["y"]
            if x + 72 < left or x - 72 > right or y + 72 < top or y - 72 > bottom:
                continue
            sprite = self.sprite_manager.get_resource_sprite(ghost["name"])
            if sprite is None:
                continue
            sprite_w, sprite_h = sprite.get_size()
            scale = (TILE_WIDTH / sprite_w) * self._render_scales.get(ghost["name"], 1.0)
            width = max(1, int(sprite_w * scale * camera.zoom))
            height = max(1, int(sprite_h * scale * camera.zoom))
            key = (sprite, width, height, 'fog_ghost')
            faded = self._scaled_sprite_cache.get(key)
            if faded is None:
                if len(self._scaled_sprite_cache) > 2048:
                    self._scaled_sprite_cache.clear()
                faded = pygame.transform.scale(sprite, (width, height)).copy()
                faded.set_alpha(self.GHOST_ALPHA)
                self._scaled_sprite_cache[key] = faded
            map_surface.blit(faded, ((x * camera.zoom) + camera.x - width / 2,
                                     (y * camera.zoom) + camera.y - height / 2))

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
        """§8.5 (user request 2026-07-14): the finished building fades IN over
        the site as progress advances — alpha 0 → 255, "appearing" rather
        than the earlier bottom-slice curtain reveal."""
        duration = getattr(site, 'construction_duration', 0) or 1
        progress = min(1.0, getattr(site, 'construction_progress', 0) / duration)
        if progress <= 0.02:
            return  # bare foundation until work starts
        try:
            player_index = self.game.players.index(site.player)
        except (ValueError, AttributeError):
            return
        sprite = self.sprite_manager.get_building_sprite(site.building_name, player_index)
        if sprite is None:
            return
        sprite_w, sprite_h = sprite.get_size()
        scale = (site.size[0] * TILE_WIDTH) / sprite_w
        # Same visual scale as the finished building, or the ghost pops to a
        # different size the moment construction completes.
        scale *= self._render_scales.get(site.building_name, 1.0)
        width = max(1, int(sprite_w * scale * camera.zoom))
        height = max(1, int(sprite_h * scale * camera.zoom))
        key = (sprite, width, height, False)
        scaled = self._scaled_sprite_cache.get(key)
        if scaled is None:
            if len(self._scaled_sprite_cache) > 2048:
                self._scaled_sprite_cache.clear()
            scaled = pygame.transform.scale(sprite, (width, height))
            self._scaled_sprite_cache[key] = scaled
        # Alpha copies are cached in 32 quantized steps so a site fading over
        # 10-15s costs ~32 copies total, not one per frame.
        alpha_bucket = min(31, int(progress * 32))
        akey = (sprite, width, height, 'fade', alpha_bucket)
        ghost = self._scaled_sprite_cache.get(akey)
        if ghost is None:
            if len(self._scaled_sprite_cache) > 2048:
                self._scaled_sprite_cache.clear()
            ghost = scaled.copy()
            ghost.set_alpha(min(255, alpha_bucket * 8 + 8))
            self._scaled_sprite_cache[akey] = ghost
        map_surface.blit(ghost, (draw_x - width / 2, draw_y - height / 2))
    
    def _fountain_sprite(self):
        """Healing-fountain visual (§8.9). Drop-in art convention: put
        `assets/sprites/Buildings/Fountain.png` in place and it loads
        automatically; until then a procedural stone-basin placeholder
        draws. Cached either way."""
        cached = getattr(self, "_fountain_surface", None)
        if cached is not None:
            return cached
        try:
            art = pygame.image.load("assets/sprites/Buildings/Fountain.png").convert_alpha()
            self._fountain_surface = art
            return art
        except (pygame.error, FileNotFoundError):
            pass
        size = 96
        surface = pygame.Surface((size, size), pygame.SRCALPHA)
        cx = cy = size // 2
        pygame.draw.ellipse(surface, (110, 110, 118), (6, 20, 84, 56))      # outer stone
        pygame.draw.ellipse(surface, (140, 140, 150), (12, 24, 72, 48))     # rim
        pygame.draw.ellipse(surface, (52, 120, 200), (20, 30, 56, 36))      # pool
        pygame.draw.ellipse(surface, (110, 190, 255), (30, 36, 28, 16))     # shimmer
        pygame.draw.ellipse(surface, (170, 225, 255), (40, 40, 12, 7))      # sparkle core
        pygame.draw.ellipse(surface, (90, 90, 100), (38, 8, 20, 26))        # spout pillar
        pygame.draw.ellipse(surface, (150, 210, 255), (43, 6, 10, 10))      # spout water
        self._fountain_surface = surface
        return surface

    def _get_object_sprite(self, obj):
        """Get the appropriate sprite for an object"""
        sprite_to_draw = None

        if obj.__class__.__name__ == "Fountain":
            return self._fountain_sprite()

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
        """Fog of war overlay for the human player — HEXAGONS matching the
        tile art, not the old 0.75-width rectangles (user-reported: boxy
        fog with seams over a hex map).

        All hexes are drawn onto ONE shared SRCALPHA canvas with
        pygame.draw.polygon, which writes pixels directly (no blending):
        neighboring hexes share lattice-exact edges, so rasterization
        overlap can't double-darken a seam and rounding can't open a gap.
        The canvas then composites onto the map in a single blit."""
        fog = getattr(self.game, 'fog_of_war', None)
        if not fog or not fog.enabled:
            return

        human = self.game.players[0] if self.game.players else None
        if not human:
            return

        overlay = self._fog_overlay
        if overlay is None or overlay.get_size() != map_surface.get_size():
            overlay = self._fog_overlay = pygame.Surface(
                map_surface.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 0))

        # Same lattice math as Map.draw, so fog hexes land exactly on tiles
        tile_width = int(TILE_WIDTH * camera.zoom)
        tile_height = int(TILE_HEIGHT * camera.zoom)

        start_col = max(0, int(-camera.x / (tile_width * 0.75)) - 1)
        end_col = min(self.game.game_map.width, int((-camera.x + map_surface.get_width()) / (tile_width * 0.75)) + 1)
        start_row = max(0, int(-camera.y / tile_height) - 1)
        end_row = min(self.game.game_map.height, int((-camera.y + map_surface.get_height()) / tile_height) + 1)

        drew_any = False
        for row in range(start_row, end_row):
            for col in range(start_col, end_col):
                state = fog.get_tile_state(human, row, col)

                if state == fog.UNEXPLORED:
                    alpha = 255       # never seen: solid black
                elif state == fog.EXPLORED:
                    alpha = 150       # seen before: dimmed
                else:
                    continue          # VISIBLE - no overlay

                x = col * tile_width * 0.75 + camera.x
                y = row * tile_height + camera.y
                if col % 2 != 0:
                    y += tile_height / 2

                # Flat-top hex inscribed in the tile's w x h box — the same
                # shape as the tile sprites, so fog interlocks like they do
                w, h = tile_width, tile_height
                pygame.draw.polygon(overlay, (0, 0, 0, alpha), (
                    (x + 0.25 * w, y),
                    (x + 0.75 * w, y),
                    (x + w, y + 0.5 * h),
                    (x + 0.75 * w, y + h),
                    (x + 0.25 * w, y + h),
                    (x, y + 0.5 * h),
                ))
                drew_any = True

        if drew_any:
            map_surface.blit(overlay, (0, 0))
    
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
