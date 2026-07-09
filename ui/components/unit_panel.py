import pygame
from entities import ConstructionSite


class UnitPanel:
    """Manages the unit selection and information panel"""
    
    def __init__(self, game):
        self.game = game
        self.font = pygame.font.Font(None, 30)
        self.small_font = pygame.font.Font(None, 20)
        self.button_font = pygame.font.Font(None, 24)
        self.stat_font = pygame.font.Font(None, 18)
        
        # Pre-load and cache unit panel icons for performance
        self.unit_panel_icons = {}
        self._load_unit_panel_icons()
        
    def _load_unit_panel_icons(self):
        """Pre-load and cache unit panel icons at different sizes for performance"""
        # Define the unit types and required sizes
        unit_types = ['worker', 'warrior', 'archer', 'spearman', 'cavalry', 'ram', 'healer']
        sizes = {
            'single': 64,  # For single unit selection
            'multi': 48    # For multi-unit selection
        }
        
        for unit_type in unit_types:
            self.unit_panel_icons[unit_type] = {}
            icon_path = f"assets/ui/Units/{unit_type}_icon.png"
            
            try:
                # Load the original icon once
                original_icon = pygame.image.load(icon_path).convert_alpha()
                
                # Pre-scale to both required sizes and cache them
                for size_name, size_pixels in sizes.items():
                    scaled_icon = pygame.transform.scale(original_icon, (size_pixels, size_pixels))
                    self.unit_panel_icons[unit_type][size_name] = scaled_icon
                
            except:
                # Create placeholder icons for missing files
                for size_name, size_pixels in sizes.items():
                    placeholder = pygame.Surface((size_pixels, size_pixels))
                    placeholder.fill((100, 100, 100))
                    pygame.draw.rect(placeholder, (150, 150, 150), (0, 0, size_pixels, size_pixels), 2)
                    # Add text to indicate unit type
                    font = pygame.font.Font(None, max(12, size_pixels // 4))
                    text = font.render(unit_type[:4].upper(), True, (255, 255, 255))
                    text_rect = text.get_rect(center=(size_pixels // 2, size_pixels // 2))
                    placeholder.blit(text, text_rect)
                    self.unit_panel_icons[unit_type][size_name] = placeholder
    
    def get_selected_objects(self):
        """Get all selected objects"""
        selected_objects = []
        all_objects = self.game.units + self.game.buildings + self.game.resources + self.game.construction_sites
        
        for obj in all_objects:
            if obj.selected:
                selected_objects.append(obj)
        
        return selected_objects
    
    def get_selected_object_info(self):
        """Get information about the currently selected object"""
        all_objects = self.game.units + self.game.buildings + self.game.resources + self.game.construction_sites
        
        for obj in all_objects:
            if obj.selected:
                # Check if ConstructionSite
                if isinstance(obj, ConstructionSite):
                    return {
                        "name": f"{obj.building_type.title()} (Under Construction)",
                        "type": "Construction",
                        "owner": obj.player.name if obj.player else "Unknown",
                        "player_color": obj.player.color if obj.player else (100, 100, 100),
                        "object": obj
                    }
                
                # Regular object info
                obj_type = obj.__class__.__name__
                
                # Determine type for display
                if obj in self.game.units:
                    display_type = "Unit"
                elif obj in self.game.buildings:
                    display_type = "Building"
                elif obj in self.game.resources:
                    display_type = "Resource"
                else:
                    display_type = obj_type
                
                info = {
                    "name": getattr(obj, "display_name", obj.name if hasattr(obj, 'name') else obj_type),
                    "type": display_type,
                    "owner": obj.player.name if hasattr(obj, 'player') and obj.player else "Neutral",
                    "player_color": obj.player.color if hasattr(obj, 'player') and obj.player else (100, 100, 100),
                    "object": obj
                }
                
                # Add HP if available
                if hasattr(obj, 'hp'):
                    info["hp"] = f"{obj.hp}"
                
                return info
        
        return None
    
    def draw_panel(self, panel_surface, ui_width, selected_objects):
        """Draw the unit panel content"""
        # Handle multi-unit selection
        if len(selected_objects) > 1:
            self._draw_multi_selection(panel_surface, selected_objects)
            return None, 0  # Return None for selected_info and 0 for y_offset
        elif len(selected_objects) == 1:
            # Get selected object info for single selection
            selected_info = self.get_selected_object_info()
            return self._draw_single_selection(panel_surface, ui_width, selected_info)
        else:
            # No selection
            no_selection_text = self.font.render("No Selection", True, (150, 150, 150))
            panel_surface.blit(no_selection_text, (10, 20))
            return None, 0
    
    def _draw_single_selection(self, panel_surface, ui_width, selected_info):
        """Draw single unit/building selection"""
        if not selected_info:
            return None, 0
            
        y_offset = 10
        
        # For units, show new layout
        if selected_info["type"] == "Unit":
            unit = selected_info["object"]
            
            # Draw unit icon (centered) - use cached icon for performance
            icon_size = 64
            icon_x = (ui_width - icon_size) // 2
            
            # Get cached icon if available
            if unit.name in self.unit_panel_icons and 'single' in self.unit_panel_icons[unit.name]:
                cached_icon = self.unit_panel_icons[unit.name]['single']
                panel_surface.blit(cached_icon, (icon_x, y_offset))
            else:
                # Fallback placeholder
                placeholder = pygame.Surface((icon_size, icon_size))
                placeholder.fill((100, 100, 100))
                pygame.draw.rect(placeholder, (150, 150, 150), (0, 0, icon_size, icon_size), 2)
                panel_surface.blit(placeholder, (icon_x, y_offset))
            
            y_offset += icon_size + 10
            
            # Draw health bar
            bar_width = 150
            bar_height = 20
            bar_x = (ui_width - bar_width) // 2
            
            # Get max HP from unit data
            max_hp = self._get_unit_max_hp(unit)
            hp_percentage = unit.hp / max_hp if max_hp > 0 else 0
            
            # Background bar
            pygame.draw.rect(panel_surface, (60, 60, 60), (bar_x, y_offset, bar_width, bar_height))
            # Health fill
            fill_width = int(bar_width * hp_percentage)
            health_color = self._get_health_color(hp_percentage)
            pygame.draw.rect(panel_surface, health_color, (bar_x, y_offset, fill_width, bar_height))
            # Border
            pygame.draw.rect(panel_surface, (100, 100, 100), (bar_x, y_offset, bar_width, bar_height), 2)
            
            # HP text
            hp_text = self.stat_font.render(f"{unit.hp}/{max_hp} HP", True, (255, 255, 255))
            hp_text_rect = hp_text.get_rect(center=(ui_width // 2, y_offset + bar_height // 2))
            panel_surface.blit(hp_text, hp_text_rect)
            
            y_offset += bar_height + 15
            
            # Combat stats for fighting units (exclude workers)
            if hasattr(unit, 'can_attack') and unit.can_attack and unit.name != 'worker':
                # Damage range and type
                damage_text = self.stat_font.render(
                    f"Damage: {unit.get_effective_min_damage()}-{unit.get_effective_max_damage()} ({unit.attack_type.title()})",
                    True,
                    (255, 200, 100),
                )
                panel_surface.blit(damage_text, (10, y_offset))
                y_offset += 20
                
                # Attack range
                range_text = self.stat_font.render(f"Range: {int(unit.get_effective_attack_range())}", True, (100, 200, 255))
                panel_surface.blit(range_text, (10, y_offset))
                y_offset += 20
                
                # Attack speed
                speed_text = self.stat_font.render(f"Attack Speed: {unit.attack_speed:.1f}/s", True, (200, 255, 100))
                panel_surface.blit(speed_text, (10, y_offset))
                y_offset += 25
            
            # Armor info
            armor_text = self.stat_font.render(
                f"Armor: {unit.armor_type.title()} ({unit.get_effective_armor_value()})",
                True,
                (200, 200, 200),
            )
            panel_surface.blit(armor_text, (10, y_offset))
            y_offset += 25
            
            # Stance info for combat units
            if hasattr(unit, 'stance') and hasattr(unit, 'can_attack_flag') and unit.can_attack_flag:
                stance_colors = {
                    'aggressive': (255, 100, 100),
                    'defensive': (100, 200, 255),
                    'stand_ground': (255, 200, 100),
                    'no_attack': (150, 150, 150),
                }
                stance_color = stance_colors.get(unit.stance, (200, 200, 200))
                stance_label = unit.stance.replace('_', ' ').title()
                stance_text = self.stat_font.render(f"Stance: {stance_label} (Press S)", True, stance_color)
                panel_surface.blit(stance_text, (10, y_offset))
                y_offset += 25
            
            # Owner info
            owner_color = selected_info["player_color"]
            owner_text = self.small_font.render(f"Owner: {selected_info['owner']}", True, owner_color)
            panel_surface.blit(owner_text, (10, y_offset))
            y_offset += 25
            
            # Show worker carrying capacity if worker
            if unit.name == "worker" and hasattr(unit, 'resource_amount') and unit.resource_amount > 0:
                resource_display = unit.resource_type.replace('_', ' ').title() if unit.resource_type else 'Unknown'
                capacity_text = self.small_font.render(
                    f"Carrying: {int(unit.resource_amount)} {resource_display}", 
                    True, (255, 200, 100)
                )
                panel_surface.blit(capacity_text, (10, y_offset))
                y_offset += 25
        else:
            # Original layout for non-units
            # Object name
            name_text = self.font.render(selected_info["name"], True, (255, 255, 255))
            panel_surface.blit(name_text, (10, y_offset))
            y_offset += 35
            
            # Object type
            type_text = self.font.render(f"Type: {selected_info['type']}", True, (200, 200, 200))
            panel_surface.blit(type_text, (10, y_offset))
            y_offset += 30
            
            # Owner
            owner_color = selected_info["player_color"]
            owner_text = self.font.render(f"Owner: {selected_info['owner']}", True, owner_color)
            panel_surface.blit(owner_text, (10, y_offset))
            y_offset += 30
            
            # HP (if available)
            if "hp" in selected_info:
                hp_text = self.font.render(f"HP: {selected_info['hp']}", True, (255, 255, 255))
                panel_surface.blit(hp_text, (10, y_offset))
                y_offset += 30
            
            # Combat stats for buildings that can attack (like watchtowers)
            obj = selected_info["object"]
            if (selected_info["type"] == "Building" and 
                hasattr(obj, 'can_attack') and obj.can_attack):
                y_offset += 10  # Add some spacing
                
                # Combat stats header
                combat_header = self.font.render("Combat Stats:", True, (255, 200, 100))
                panel_surface.blit(combat_header, (10, y_offset))
                y_offset += 25
                
                # Damage range and type
                damage_text = self.stat_font.render(
                    f"Damage: {obj.get_effective_min_damage()}-{obj.get_effective_max_damage()} ({obj.attack_type.title()})",
                    True, (255, 200, 100)
                )
                panel_surface.blit(damage_text, (10, y_offset))
                y_offset += 20
                
                # Attack range
                range_text = self.stat_font.render(f"Range: {int(obj.get_effective_attack_range())}", True, (100, 200, 255))
                panel_surface.blit(range_text, (10, y_offset))
                y_offset += 20
                
                # Attack speed
                speed_text = self.stat_font.render(f"Attack Speed: {obj.attack_speed:.1f}/s", True, (200, 255, 100))
                panel_surface.blit(speed_text, (10, y_offset))
                y_offset += 20
                
                # Armor info
                armor_text = self.stat_font.render(
                    f"Armor: {obj.armor_type.title()} ({obj.get_effective_armor_value()})",
                    True, (200, 200, 200)
                )
                panel_surface.blit(armor_text, (10, y_offset))
                y_offset += 25
            
            # Show resource amount if selected
            if selected_info["type"] == "Resource":
                for resource in self.game.resources:
                    if resource.selected:
                        amount_text = self.small_font.render(
                            f"Remaining: {int(resource.amount_remaining)}", 
                            True, (100, 255, 100)
                        )
                        panel_surface.blit(amount_text, (10, y_offset))
                        y_offset += 25
                        break
                        
            # Show construction progress if selected
            if selected_info["type"] == "Construction":
                construction_site = selected_info["object"]
                if isinstance(construction_site, ConstructionSite):
                    # Progress bar
                    progress = construction_site.construction_progress / construction_site.construction_duration
                    bar_width = 150
                    bar_height = 20
                    bar_x = 25
                    bar_y = y_offset + 10
                    
                    # Draw progress bar background
                    pygame.draw.rect(panel_surface, (50, 50, 50), 
                                   (bar_x, bar_y, bar_width, bar_height))
                    # Draw progress bar fill
                    fill_width = int(bar_width * progress)
                    pygame.draw.rect(panel_surface, (0, 200, 0), 
                                   (bar_x, bar_y, fill_width, bar_height))
                    # Draw progress bar border
                    pygame.draw.rect(panel_surface, (150, 150, 150), 
                                   (bar_x, bar_y, bar_width, bar_height), 2)
                    
                    # Progress text
                    progress_text = self.small_font.render(
                        f"Progress: {int(progress * 100)}%", 
                        True, (255, 255, 255)
                    )
                    panel_surface.blit(progress_text, (bar_x, bar_y + bar_height + 5))
                    y_offset = bar_y + bar_height + 30
        
        return selected_info, y_offset
    
    def _draw_multi_selection(self, panel_surface, selected_objects):
        """Draw multi-unit selection with small icons and health bars"""
        # Title
        title_text = self.font.render(f"{len(selected_objects)} Units Selected", True, (255, 255, 255))
        panel_surface.blit(title_text, (10, 10))
        
        # Formation type indicator
        formation = getattr(self.game.selection_manager, 'formation_type', 'ring')
        formation_text = self.small_font.render(f"Formation: {formation.title()} (Press F)", True, (200, 200, 200))
        panel_surface.blit(formation_text, (10, 35))
        
        # Small icon configuration
        icon_size = 48
        icon_spacing = 4
        icons_per_row = 4
        start_x = 10
        start_y = 60
        
        # Draw each selected unit
        for i, unit in enumerate(selected_objects):
            # Skip non-units in multi-selection
            if unit not in self.game.units:
                continue
                
            # Calculate position in grid
            row = i // icons_per_row
            col = i % icons_per_row
            x = start_x + col * (icon_size + icon_spacing)
            y = start_y + row * (icon_size + icon_spacing + 15)  # Extra space for health bar
            
            # Draw unit icon - use cached icon for performance
            if unit.name in self.unit_panel_icons and 'multi' in self.unit_panel_icons[unit.name]:
                cached_icon = self.unit_panel_icons[unit.name]['multi']
                panel_surface.blit(cached_icon, (x, y))
            else:
                # Fallback placeholder
                placeholder = pygame.Surface((icon_size, icon_size))
                placeholder.fill((100, 100, 100))
                pygame.draw.rect(placeholder, (150, 150, 150), (0, 0, icon_size, icon_size), 2)
                panel_surface.blit(placeholder, (x, y))
            
            # Draw small health bar below icon
            bar_y = y + icon_size + 2
            bar_width = icon_size
            bar_height = 4
            
            # Get health percentage
            max_hp = self._get_unit_max_hp(unit)
            hp_percentage = unit.hp / max_hp if max_hp > 0 else 0
            
            # Background bar
            pygame.draw.rect(panel_surface, (60, 60, 60), (x, bar_y, bar_width, bar_height))
            # Health fill
            fill_width = int(bar_width * hp_percentage)
            health_color = self._get_health_color(hp_percentage)
            pygame.draw.rect(panel_surface, health_color, (x, bar_y, fill_width, bar_height))
    
    def _get_unit_max_hp(self, unit):
        """Get the maximum HP for a unit from cached game data."""
        template = self.game.game_data["units"].get(unit.name)
        if template:
            return template.hp
        return 100
    
    def _get_health_color(self, hp_percentage):
        """Get health bar color based on HP percentage"""
        if hp_percentage >= 0.75:
            return (0, 200, 0)  # Green
        elif hp_percentage >= 0.5:
            return (200, 200, 0)  # Yellow
        elif hp_percentage >= 0.25:
            return (200, 200, 0)  # Yellow
        else:
            return (200, 0, 0)  # Red
