"""AI Debug Dashboard for monitoring AI players and game state"""
import pygame
from typing import Dict, Optional, Tuple


class AIDebugPanel:
    """Debug panel for monitoring AI players and their states"""
    
    def __init__(self, game):
        self.game = game
        self.visible = False
        self.collapsed = False
        
        # Panel dimensions and position
        self.panel_width = 500  # Significantly increased width for better readability
        self.panel_height = 700  # Significantly increased height for more info
        self.panel_x = 10
        self.panel_y = 80  # Below the top resource bar
        
        # Colors
        self.bg_color = (0, 0, 0, 200)  # Slightly more opaque
        self.border_color = (120, 120, 120)
        self.header_color = (40, 40, 60)  # Darker blue header
        self.text_color = (255, 255, 255)
        self.ai_text_color = (120, 220, 255)  # Brighter blue for AI info
        self.status_colors = {
            "idle": (255, 200, 100),     # Orange for idle
            "gathering": (100, 255, 100), # Green for gathering
            "building": (150, 150, 255),  # Blue for building
            "military": (255, 100, 100),  # Red for military
        }
        self.resource_colors = {
            "gold": (255, 215, 0),
            "wood": (139, 69, 19),
            "stone": (128, 128, 128),
            "food": (255, 140, 0)
        }
        
        # Fonts - significantly increased sizes
        self.header_font = pygame.font.Font(None, 32)  # Increased from 24
        self.player_font = pygame.font.Font(None, 26)  # Increased from 20
        self.resource_font = pygame.font.Font(None, 22)  # Increased from 16
        self.ai_font = pygame.font.Font(None, 20)  # Increased from 14
        
        # Panel state
        self.last_update = 0
        self.update_interval = 0.5  # Update every 0.5 seconds for performance
        self.cached_data = {}
        
        # UI elements
        self.header_rect = None
        self.collapse_button_rect = None
        self.scroll_offset = 0
        self.max_scroll = 0
        
        # Data collection
        self.player_data = {}
        
    def toggle_visibility(self) -> None:
        """Toggle panel visibility"""
        self.visible = not self.visible
        if self.visible:
            self._update_data()
    
    def toggle_collapsed(self) -> None:
        """Toggle panel collapsed state"""
        self.collapsed = not self.collapsed
    
    def update(self, delta_time: float) -> None:
        """Update panel data periodically"""
        if not self.visible:
            return
            
        self.last_update += delta_time
        if self.last_update >= self.update_interval:
            self._update_data()
            self.last_update = 0
    
    def handle_click(self, pos: Tuple[int, int]) -> bool:
        """Handle mouse clicks on panel elements"""
        if not self.visible:
            return False
        
        # Check if click is on collapse button
        if self.collapse_button_rect and self.collapse_button_rect.collidepoint(pos):
            self.toggle_collapsed()
            return True
        
        # Check if click is on header (for dragging in future)
        if self.header_rect and self.header_rect.collidepoint(pos):
            return True
        
        return False
    
    def draw(self, screen: pygame.Surface) -> None:
        """Draw the debug panel"""
        if not self.visible:
            return
        
        # Calculate panel height based on collapsed state
        if self.collapsed:
            panel_height = 40  # Just header (increased from 30)
        else:
            content_height = self._calculate_content_height()
            panel_height = min(content_height + 40, self.panel_height)  # Increased header space
        
        # Create panel surface with alpha
        panel_surface = pygame.Surface((self.panel_width, panel_height), pygame.SRCALPHA)
        panel_surface.fill(self.bg_color)
        
        # Draw border
        pygame.draw.rect(panel_surface, self.border_color, 
                        (0, 0, self.panel_width, panel_height), 2)
        
        # Draw header
        self._draw_header(panel_surface)
        
        if not self.collapsed:
            # Draw content
            self._draw_content(panel_surface)
        
        # Blit to screen
        screen.blit(panel_surface, (self.panel_x, self.panel_y))
    
    def _draw_header(self, surface: pygame.Surface) -> None:
        """Draw panel header"""
        header_height = 40  # Increased from 30 to accommodate larger font
        
        # Header background
        header_rect = pygame.Rect(2, 2, self.panel_width - 4, header_height - 2)
        pygame.draw.rect(surface, self.header_color, header_rect)
        self.header_rect = pygame.Rect(self.panel_x + 2, self.panel_y + 2, 
                                     self.panel_width - 4, header_height - 2)
        
        # Title
        title_text = self.header_font.render("AI Debug Panel", True, self.text_color)
        surface.blit(title_text, (10, 8))  # Adjusted position
        
        # Collapse button
        button_size = 28  # Increased from 20
        button_x = self.panel_width - button_size - 8
        button_y = 6
        
        collapse_symbol = "−" if not self.collapsed else "+"
        button_rect = pygame.Rect(button_x, button_y, button_size, button_size)
        pygame.draw.rect(surface, self.border_color, button_rect, 1)
        
        symbol_text = self.header_font.render(collapse_symbol, True, self.text_color)
        symbol_rect = symbol_text.get_rect(center=button_rect.center)
        surface.blit(symbol_text, symbol_rect)
        
        # Store button rect for click detection
        self.collapse_button_rect = pygame.Rect(self.panel_x + button_x, self.panel_y + button_y,
                                               button_size, button_size)
    
    def _draw_content(self, surface: pygame.Surface) -> None:
        """Draw panel content"""
        y_offset = 45  # Start below header (increased from 35)
        
        for i, (player, data) in enumerate(self.player_data.items()):
            if y_offset > self.panel_height - 30:  # Don't draw beyond panel
                break
                
            y_offset = self._draw_player_info(surface, player, data, y_offset)
            y_offset += 8  # Increased spacing between players (from 5)
    
    def _draw_player_info(self, surface: pygame.Surface, player, data: Dict, y_offset: int) -> int:
        """Draw information for a single player"""
        # Player name with color indicator
        player_color = getattr(player, 'color', (255, 255, 255))
        
        # Color indicator circle
        pygame.draw.circle(surface, player_color, (15, y_offset + 8), 6)
        pygame.draw.circle(surface, self.border_color, (15, y_offset + 8), 6, 1)
        
        # Player name and type
        player_name = getattr(player, 'name', 'Unknown')
        player_type = " (AI)" if not getattr(player, 'human', True) else ""
        name_text = self.player_font.render(f"{player_name}{player_type}", True, self.text_color)
        surface.blit(name_text, (35, y_offset))
        y_offset += 26  # Increased from 20
        
        # Resources in a compact format
        resources = data.get('resources', {})
        resource_line = ""
        for resource, amount in resources.items():
            if resource_line:
                resource_line += " | "
            resource_line += f"{resource.title()}: {int(amount)}"
        
        if resource_line:
            resource_text = self.resource_font.render(resource_line, True, self.text_color)
            surface.blit(resource_text, (15, y_offset))
            y_offset += 22  # Increased from 16
        
        # Population
        population = data.get('population', {})
        if population:
            pop_text = f"Pop: {population.get('current', 0)}/{population.get('max', 0)}"
            pop_surface = self.resource_font.render(pop_text, True, self.text_color)
            surface.blit(pop_surface, (15, y_offset))
            y_offset += 22  # Increased from 16
        
        # AI-specific information
        ai_info = data.get('ai_info')
        if ai_info:
            # AI state
            state = ai_info.get('state', 'Unknown')
            state_text = self.ai_font.render(f"Phase: {state}", True, self.ai_text_color)
            surface.blit(state_text, (20, y_offset))
            y_offset += 22  # Increased from 14
            
            # Workers breakdown with clear labels and colors
            workers = ai_info.get('workers', {})
            building_workers = ai_info.get('building_workers', 0)
            if workers or building_workers:
                idle = workers.get('idle', 0)
                gathering = workers.get('gathering', 0)
                building = building_workers
                
                # Worker status with color coding
                worker_parts = []
                if idle > 0:
                    worker_parts.append((f"{idle} Idle", self.status_colors["idle"]))
                if gathering > 0:
                    worker_parts.append((f"{gathering} Gathering", self.status_colors["gathering"]))
                if building > 0:
                    worker_parts.append((f"{building} Building", self.status_colors["building"]))
                
                # Draw "Workers:" label
                label_text = self.ai_font.render("Workers: ", True, self.ai_text_color)
                surface.blit(label_text, (20, y_offset))
                x_offset = 20 + label_text.get_width()
                
                # Draw each worker type with color
                for i, (text, color) in enumerate(worker_parts):
                    if i > 0:
                        sep = self.ai_font.render(", ", True, self.ai_text_color)
                        surface.blit(sep, (x_offset, y_offset))
                        x_offset += sep.get_width()
                    
                    worker_text = self.ai_font.render(text, True, color)
                    surface.blit(worker_text, (x_offset, y_offset))
                    x_offset += worker_text.get_width()
                
                y_offset += 24  # Increased from 16
            
            # Military units with breakdown
            military_info = ai_info.get('military_breakdown', {})
            total_military = ai_info.get('military_units', 0)
            if total_military > 0:
                if military_info:
                    # Show breakdown by unit type
                    mil_parts = []
                    for unit_type, count in military_info.items():
                        if count > 0:
                            mil_parts.append(f"{count} {unit_type.title()}s")
                    
                    if mil_parts:
                        mil_text = f"Military: {', '.join(mil_parts)}"
                    else:
                        mil_text = f"Military: {total_military} units"
                else:
                    mil_text = f"Military: {total_military} units"
                
                mil_surface = self.ai_font.render(mil_text, True, self.status_colors["military"])
                surface.blit(mil_surface, (20, y_offset))
                y_offset += 24  # Increased from 16
            
            # Formations
            formations = ai_info.get('formations', 0)
            if formations > 0:
                form_text = self.ai_font.render(f"Formations: {formations}", True, self.ai_text_color)
                surface.blit(form_text, (20, y_offset))
                y_offset += 22
            
            # Buildings summary with production info
            buildings = ai_info.get('buildings', {})
            production_info = ai_info.get('production_queue', {})
            if buildings:
                total_buildings = buildings.get('total', 0)
                houses = buildings.get('houses', 0)
                barracks = buildings.get('barracks', 0)
                
                # Building counts
                build_parts = [f"{total_buildings} Total"]
                if houses > 0:
                    build_parts.append(f"{houses} Houses")
                if barracks > 0:
                    build_parts.append(f"{barracks} Barracks")
                
                build_text = f"Buildings: {', '.join(build_parts)}"
                build_surface = self.ai_font.render(build_text, True, self.ai_text_color)
                surface.blit(build_surface, (20, y_offset))
                y_offset += 24  # Increased from 16
                
                # Production queue if any
                if production_info:
                    queue_text = f"Producing: {production_info}"
                    queue_surface = self.ai_font.render(queue_text, True, (200, 200, 100))
                    surface.blit(queue_surface, (20, y_offset))
                    y_offset += 24  # Increased from 16
            
            priority_resource = ai_info.get('priority_resource')
            if priority_resource and priority_resource != 'Unknown':
                # Color-code priority resource
                resource_color = self.resource_colors.get(priority_resource.lower(), self.ai_text_color)
                pri_text = self.ai_font.render(f"Priority Resource: {priority_resource.title()}", True, resource_color)
                surface.blit(pri_text, (20, y_offset))
                y_offset += 24  # Increased from 16
            
            # Current AI tasks/objectives
            current_tasks = ai_info.get('current_tasks', [])
            if current_tasks:
                task_text = f"Active Tasks: {len(current_tasks)}"
                task_surface = self.ai_font.render(task_text, True, (255, 255, 100))
                surface.blit(task_surface, (20, y_offset))
                y_offset += 24  # Increased from 16
            
            # Decision timer with better formatting
            decision_timer = ai_info.get('decision_timer', 0)
            if decision_timer > 0:
                timer_text = self.ai_font.render(f"Next Decision: {decision_timer:.1f}s", True, (150, 150, 150))
            else:
                timer_text = self.ai_font.render("Decision: Ready", True, (100, 255, 100))
            surface.blit(timer_text, (20, y_offset))
            y_offset += 24  # Increased from 16
        
        # Draw separator line
        if y_offset < self.panel_height - 30:
            pygame.draw.line(surface, self.border_color, 
                           (8, y_offset), (self.panel_width - 8, y_offset))
            y_offset += 5  # Increased from 3
        
        return y_offset
    
    def _calculate_content_height(self) -> int:
        """Calculate required height for content"""
        height = 15  # Base padding (increased)
        
        for player in self.player_data:
            height += 26  # Player name (increased)
            height += 22  # Resources (increased)  
            height += 22  # Population (increased)
            
            # AI info adds variable height
            ai_info = self.player_data[player].get('ai_info')
            if ai_info:
                height += 24 * 8  # Increased for all AI info lines (state, workers, military, buildings, priority, tasks, timer)
            
            height += 13  # Separator and spacing (increased)
        
        return height
    
    def _update_data(self) -> None:
        """Update cached player data"""
        self.player_data.clear()
        
        for player in self.game.players:
            data = {
                'resources': self._get_player_resources(player),
                'population': self._get_player_population(player),
            }
            
            # Add AI-specific data for AI players
            if not getattr(player, 'human', True):
                data['ai_info'] = self._get_ai_info(player)
            
            self.player_data[player] = data
    
    def _get_player_resources(self, player) -> Dict[str, int]:
        """Get player's current resources"""
        resources = {}
        player_resources = getattr(player, 'resources', {})
        
        for resource_type in ['gold', 'wood', 'stone', 'food']:
            resources[resource_type] = player_resources.get(resource_type, 0)
        
        return resources
    
    def _get_player_population(self, player) -> Dict[str, int]:
        """Get player's population info"""
        # Count units
        current_pop = len([u for u in self.game.units if getattr(u, 'player', None) == player])
        
        # Calculate max population
        max_pop = 5  # Base castle limit
        houses = [b for b in self.game.buildings 
                 if getattr(b, 'player', None) == player and getattr(b, 'name', '') == 'house']
        max_pop += len(houses) * 5  # Each house adds 5 population
        
        return {'current': current_pop, 'max': max_pop}
    
    def _get_ai_info(self, player) -> Optional[Dict]:
        """Get AI-specific information"""
        ai_system = getattr(self.game, 'ai_system', None)
        if not ai_system or not hasattr(ai_system, 'get_ai_debug_info'):
            return None
        
        # Use the AI system's debug info method
        debug_info = ai_system.get_ai_debug_info(player)
        if not debug_info:
            return None
        
        # Map to the format expected by the UI
        ai_info = {
            'state': debug_info.get('game_phase', 'Unknown'),
            'formations': debug_info.get('formations', 0),
            'priority_resource': debug_info.get('priority_resource', 'Unknown'),
            'decision_timer': debug_info.get('decision_timer', 0.0),
            'workers': {
                'idle': debug_info.get('idle_workers', 0),
                'gathering': debug_info.get('gathering_workers', 0),
            },
            'military_units': debug_info.get('military_units', 0),
            'buildings': debug_info.get('buildings', {})
        }
        
        return ai_info
