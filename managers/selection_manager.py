import pygame
import math
import random
from typing import List, Tuple
from core.config import SCREEN_HEIGHT, MAP_VIEW_HEIGHT, MINIMAP_WIDTH, MINIMAP_HEIGHT, TOP_BAR_HEIGHT
from systems.pathfinding import Pathfinding


class SelectionManager:
    """Manages object selection and selection visualization"""
    
    def __init__(self, game):
        self.game = game
        self.selected_objects = []
        self.selection_box_active = False
        self.selection_start_pos = None
    
    def handle_left_click(self, mouse_pos):
        """Handle left mouse button down"""
        # Check if clicking on minimap
        if mouse_pos[0] > self.game.screen.get_width() - MINIMAP_WIDTH and mouse_pos[1] < MINIMAP_HEIGHT:
            return False  # Let minimap handle it
        
        self.selection_start_pos = mouse_pos
        self.selection_box_active = True
        return True
    
    def handle_left_release(self, mouse_pos):
        """Handle left mouse button release - perform selection"""
        if not self.selection_box_active:
            return
        
        self.selection_box_active = False
        selection_end_pos = mouse_pos
        
        # Check if it's a click (not a drag)
        if abs(self.selection_start_pos[0] - selection_end_pos[0]) < 5 and abs(self.selection_start_pos[1] - selection_end_pos[1]) < 5:
            self._handle_single_click(selection_end_pos)
        else:
            # Convert to map coordinates for drag selection
            pass
            start_map_pos = (self.selection_start_pos[0], self.selection_start_pos[1] - TOP_BAR_HEIGHT)
            end_map_pos = (selection_end_pos[0], selection_end_pos[1] - TOP_BAR_HEIGHT)
            self._handle_drag_selection(start_map_pos, end_map_pos)
        
        self.selection_start_pos = None
        
        # Update smart cursor based on new selection
        self._update_smart_cursor_for_selection()
    
    def _handle_single_click(self, mouse_pos):
        """Handle single click selection with proper ownership filtering"""
        # Check all objects for selection
        all_objects = self.game.units + self.game.buildings + self.game.resources
        clicked_object = None
        
        # Convert mouse position to map coordinates (accounting for TOP_BAR_HEIGHT)
        map_mouse_x = mouse_pos[0]
        map_mouse_y = mouse_pos[1] - TOP_BAR_HEIGHT
        
        # Find object at click position
        for obj in sorted(all_objects, key=lambda o: o.y, reverse=True):
            obj_screen_x = (obj.x * self.game.camera.zoom) + self.game.camera.x
            obj_screen_y = (obj.y * self.game.camera.zoom) + self.game.camera.y
            
            # Simple distance check with some extra tolerance for easier clicking
            distance = math.sqrt((map_mouse_x - obj_screen_x)**2 + (map_mouse_y - obj_screen_y)**2)
            
            # Use different tolerance for units vs. buildings
            if obj in self.game.units:
                click_radius = obj.radius * self.game.camera.zoom * 2.0  # 100% larger hitbox for units
            else:
                click_radius = obj.radius * self.game.camera.zoom * 1.0  # Normal hitbox for buildings/resources

            if distance <= click_radius:
                clicked_object = obj
                break
        
        if clicked_object:
            # Check if this object can be selected with current selection
            pass
            is_shift_held = pygame.key.get_pressed()[pygame.K_LSHIFT]
            clicked_is_human = hasattr(clicked_object, 'player') and clicked_object.player and clicked_object.player.human
            clicked_is_ai = hasattr(clicked_object, 'player') and clicked_object.player and not clicked_object.player.human
            clicked_is_neutral = not hasattr(clicked_object, 'player') or not clicked_object.player
            
            # Check current selection ownership
            current_has_human = any(hasattr(obj, 'player') and obj.player and obj.player.human for obj in self.selected_objects)
            current_has_ai = any(hasattr(obj, 'player') and obj.player and not obj.player.human for obj in self.selected_objects)
            
            # Determine if we should clear selection
            should_clear_selection = False
            
            if not is_shift_held:
                # Always clear if not holding shift
                pass
                should_clear_selection = True
            elif clicked_is_ai:
                # Always clear when clicking AI units (never multi-select enemy units)
                pass
                should_clear_selection = True
            elif clicked_is_human and current_has_ai:
                # Clear if trying to mix human and AI
                pass
                should_clear_selection = True
            elif (clicked_is_neutral and current_has_ai):
                # Clear if trying to mix neutral and AI
                pass
                should_clear_selection = True
            
            # Clear selection if needed
            if should_clear_selection:
                self._clear_all_selections()
            
            # Handle selection toggle with Shift
            if clicked_object.selected and is_shift_held and not should_clear_selection:
                # Deselect if already selected and using Shift (and we didn't clear)
                pass
                clicked_object.selected = False
                if clicked_object in self.selected_objects:
                    self.selected_objects.remove(clicked_object)
            else:
                # Select the object
                pass
                clicked_object.selected = True
                
                # Add to selected_objects based on ownership
                if clicked_is_human:
                    # Human player objects - always add for control
                    pass
                    if clicked_object not in self.selected_objects:
                        self.selected_objects.append(clicked_object)
                elif clicked_is_neutral:
                    # Neutral objects (resources) - add for interaction
                    pass
                    if clicked_object not in self.selected_objects:
                        self.selected_objects.append(clicked_object)
                # Note: AI objects are not added to selected_objects (visual selection only)
        else:
            # No object clicked - clear selection unless shift is held
            pass
            is_shift_held = pygame.key.get_pressed()[pygame.K_LSHIFT]
            if not is_shift_held:
                self._clear_all_selections()
    
    def _categorize_objects_in_rect(self, selection_rect):
        """Categorize objects in selection rectangle by type and ownership"""
        units = []
        buildings = []
        resources = []
        
        all_objects = self.game.units + self.game.buildings + self.game.resources
        
        for obj in all_objects:
            draw_x = (obj.x * self.game.camera.zoom) + self.game.camera.x
            draw_y = (obj.y * self.game.camera.zoom) + self.game.camera.y
            
            if selection_rect.collidepoint(draw_x, draw_y):
                if obj in self.game.units:
                    units.append(obj)
                elif obj in self.game.buildings:
                    buildings.append(obj)
                else:  # resources
                    resources.append(obj)
        
        return units, buildings, resources
    
    def _can_multi_select_together(self, objects):
        """Check if objects can be multi-selected together based on ownership"""
        if len(objects) <= 1:
            return True
            
        # Get the player of the first object
        first_player = None
        for obj in objects:
            if hasattr(obj, 'player') and obj.player:
                first_player = obj.player
                break
        
        # Check if all objects have the same player
        for obj in objects:
            obj_player = obj.player if hasattr(obj, 'player') else None
            if obj_player != first_player:
                return False
                
        return True
    
    def _filter_selectable_objects(self, objects, allow_multi_select=True):
        """Filter objects to only include those that can be selected together"""
        if not objects:
            return []
            
        # Separate human player objects from others
        human_objects = []
        ai_objects = []
        neutral_objects = []
        
        for obj in objects:
            if hasattr(obj, 'player') and obj.player:
                if obj.player.human:
                    human_objects.append(obj)
                else:
                    ai_objects.append(obj)
            else:
                neutral_objects.append(obj)
        
        # For multi-selection, only allow same-ownership objects
        if allow_multi_select and len(objects) > 1:
            # Never allow multi-selection of AI/enemy units
            pass
            if ai_objects:
                return []
            # Only return human objects for multi-selection
            return human_objects + neutral_objects
        else:
            # Single selection - allow any object but prioritize human player
            pass
            if human_objects:
                return human_objects[:1]
            elif ai_objects:
                return ai_objects[:1]
            else:
                return neutral_objects[:1] if neutral_objects else []
    
    def _handle_drag_selection(self, start_pos, end_pos):
        """Handle drag box selection with proper priority and ownership filtering"""
        # Create selection rectangle
        min_x = min(start_pos[0], end_pos[0])
        max_x = max(start_pos[0], end_pos[0])
        min_y = min(start_pos[1], end_pos[1])
        max_y = max(start_pos[1], end_pos[1])
        
        selection_rect = pygame.Rect(min_x, min_y, max_x - min_x, max_y - min_y)
        
        # Clear previous selections if not holding shift
        if not pygame.key.get_pressed()[pygame.K_LSHIFT]:
            self._clear_all_selections()
        
        # Categorize objects in selection rectangle
        units, buildings, resources = self._categorize_objects_in_rect(selection_rect)
        
        # Apply selection priority: units > buildings > resources
        objects_to_select = []
        
        if units:
            # If there are units, only select units (ignore buildings/resources)
            pass
            filtered_units = self._filter_selectable_objects(units, allow_multi_select=True)
            objects_to_select = filtered_units
        elif buildings:
            # No units, but there are buildings
            pass
            filtered_buildings = self._filter_selectable_objects(buildings, allow_multi_select=True)
            objects_to_select = filtered_buildings
        elif resources:
            # Only resources available
            pass
            filtered_resources = self._filter_selectable_objects(resources, allow_multi_select=True)
            objects_to_select = filtered_resources
        
        # Apply selections
        for obj in objects_to_select:
            obj.selected = True
            
            # Add to selected_objects for control (only human player objects)
            if hasattr(obj, 'player') and obj.player and obj.player.human:
                if obj not in self.selected_objects:
                    self.selected_objects.append(obj)
            # For neutral objects (resources), also add them for potential interaction
            elif not hasattr(obj, 'player') or not obj.player:
                if obj not in self.selected_objects:
                    self.selected_objects.append(obj)
    
    def _clear_all_selections(self):
        """Clear all object selections"""
        all_objects = self.game.units + self.game.buildings + self.game.resources
        for obj in all_objects:
            obj.selected = False
        self.selected_objects.clear()
    
    def _update_smart_cursor_for_selection(self):
        """Update cursor based on current selection (when not in command mode)"""
        # Get human player units from selection
        selected_units = [obj for obj in self.selected_objects 
                         if obj in self.game.units and hasattr(obj, 'player') and obj.player and obj.player.human]
        
        if selected_units:
            # Set smart cursor for selected units
            pass
            self.game.ui_manager.set_smart_cursor_for_units(selected_units)
        else:
            # No units selected, restore default cursor
            pass
            try:
                if self.game.ui_manager.default_cursor:
                    pygame.mouse.set_cursor(self.game.ui_manager.default_cursor)
            except:
                pass
    
    def handle_right_click(self, mouse_pos):
        """Handle right click - move selected units"""
        if not self.selected_objects:
            return
        
        world_pos = self.game.screen_to_world(mouse_pos[0], mouse_pos[1])
        self._handle_regular_right_click(world_pos)
    
    def _handle_regular_right_click(self, world_pos):
        """Handle regular right-click commands"""
        # Debug: Right click position
        
        # Check if clicking on a resource or building
        clicked_object = self._get_object_at_position(world_pos)
        # Debug: Clicked object
        
        # Create pathfinding instance
        pathfinder = Pathfinding(self.game.game_map, self.game)
        
        # Filter only human player units that can move
        movable_units = [obj for obj in self.selected_objects 
                        if hasattr(obj, 'destination') and obj.player and obj.player.human]
        # Debug: Movable units
        
        pass
        # If multiple units moving to empty space, add small offsets to prevent stacking
        if len(movable_units) > 1 and not clicked_object:
            # Calculate offsets in a rough circle around the target
            pass
            offset_radius = 30  # Distance from center for each unit
            
            for i, obj in enumerate(movable_units):
                # Create small random offset for each unit
                pass
                angle = (i / len(movable_units)) * 2 * math.pi + random.uniform(-0.3, 0.3)
                offset_x = math.cos(angle) * offset_radius * random.uniform(0.8, 1.2)
                offset_y = math.sin(angle) * offset_radius * random.uniform(0.8, 1.2)
                
                target_pos = (world_pos[0] + offset_x, world_pos[1] + offset_y)
                self._move_unit_to_position(obj, target_pos, pathfinder)
        else:
            # Command units normally (single unit or clicking on object)
            pass
            for obj in movable_units:
                # Handle different click targets
                pass
                if clicked_object:
                    # Debug: Checking unit against clicked object
                    
                    pass
                    # If clicking on a resource, gather it (workers only)
                    if clicked_object in self.game.resources and obj.name == "worker":
                        # Debug: Calling _gather_from_target
                        pass
                        # Use the new combat-style resource gathering
                        self._gather_from_target(obj, clicked_object, pathfinder)
                    # If clicking on a farm, garrison worker (workers only)
                    elif clicked_object in self.game.buildings and clicked_object.name == "farm" and obj.name == "worker":
                        # Clear any drop-off state
                        pass
                        obj.is_dropping_off = False
                        obj.drop_off_timer = 0.0
                        obj.drop_off_target = None
                        
                        # Move to closest reachable position near farm
                        path = pathfinder.find_path((obj.x, obj.y), (clicked_object.x, clicked_object.y), obj.radius, obj)
                        if path:
                            obj.path = path
                            obj.path_index = 0
                            obj.path_target = path[-1]  # Use actual reachable position
                            obj.destination = path[0] if path else None
                            obj.garrison_target = clicked_object  # Mark for garrisoning
                            obj.status = "run"
                            
                            # Check if we had to redirect
                            final_pos = path[-1]
                            distance_to_farm = math.sqrt((final_pos[0] - clicked_object.x)**2 + (final_pos[1] - clicked_object.y)**2)
                            if distance_to_farm > clicked_object.radius + obj.radius + 10:
                                # Debug: Worker moving to garrison at farm
                                pass
                                pass
                        else:
                            # Debug: Worker cannot reach farm
                            pass
                            pass
                    # If clicking on a drop-off building and carrying resources
                    elif (clicked_object in self.game.buildings and 
                          obj.name == "worker" and 
                          obj.resource_amount > 0):
                        # Set drop-off target on pathfinder to allow collision with this building
                        pathfinder.drop_off_target = clicked_object
                        
                        # Move to closest reachable position near building
                        path = pathfinder.find_path((obj.x, obj.y), (clicked_object.x, clicked_object.y), obj.radius, obj)
                        
                        # Clear drop-off target from pathfinder
                        pathfinder.drop_off_target = None
                        
                        if path:
                            obj.path = path
                            obj.path_index = 0
                            obj.path_target = path[-1]  # Use actual reachable position
                            obj.destination = path[0] if path else None
                            obj.drop_off_target = clicked_object
                            obj.status = "run"
                            
                            # Check if we had to redirect
                            final_pos = path[-1]
                            distance_to_building = math.sqrt((final_pos[0] - clicked_object.x)**2 + (final_pos[1] - clicked_object.y)**2)
                            if distance_to_building > clicked_object.radius + obj.radius + 10:
                                # Debug: Worker moving to drop off
                                pass
                                pass
                        else:
                            # Debug: Worker cannot reach building for drop-off
                            pass
                            pass
                    # If clicking on an enemy unit/building and this unit can attack
                    elif (hasattr(clicked_object, 'player') and 
                          clicked_object.player != obj.player):
                        # Debug: Click on enemy
                        
                        if obj.can_attack_flag:
                            # Attack enemy target - this will automatically find best reachable attack position
                            pass
                            self._attack_target(obj, clicked_object, pathfinder)
                        else:
                            # Can't attack, just move to closest reachable position near target
                            pass
                            # Debug: Unit cannot attack, moving close to target
                            self._move_unit_to_position(obj, world_pos, pathfinder)
                    else:
                        # Regular move to location
                        pass
                        self._move_unit_to_position(obj, world_pos, pathfinder)
                else:
                    # No object clicked, regular move
                    pass
                    self._move_unit_to_position(obj, world_pos, pathfinder)
    
    def _attack_target(self, unit, target, pathfinder, new_destination=None):
        """Command unit to attack a target"""
        # Debug: _attack_target called
        
        # Clear any non-combat state
        unit.is_gathering = False
        unit.gathering_target = None
        unit.is_dropping_off = False
        unit.drop_off_timer = 0.0
        unit.drop_off_target = None
        if hasattr(unit, 'garrison_target'):
            unit.garrison_target = None

        # If a new destination is provided by the watchdog, use it immediately.
        if new_destination:
            path = pathfinder.find_path((unit.x, unit.y), new_destination, unit.radius, unit)
            if path:
                unit.path = path
                unit.path_index = 0
                unit.path_target = path[-1] if path else new_destination
                unit.destination = path[0] if path else None
                unit.status = "run"
                unit.current_target = target
                unit.is_engaging = True
                unit.has_los = False
                unit.is_fallback_movement = False
                unit.last_task = {"type": "attack", "target": target}
            return # Skip the rest of the logic
        
        # Check if target is in attack range
        distance = unit.get_distance_to(target)
        # Debug: Distance and attack check
        
        if unit.can_attack(target):
            # Target is in range, start attacking immediately
            pass
            unit.start_attack(target)
            # Debug: Unit attacking immediately
        else:
            # Target is out of range, determine movement strategy
            pass
            dx = target.x - unit.x
            dy = target.y - unit.y
            
            if distance > 0:
                # Check if we have line of sight to target
                pass
                # Include buildings, other units, AND resources as obstacles
                obstacles = (self.game.buildings + 
                           [u for u in self.game.units if u != unit and u != target] + 
                           self.game.resources)
                has_los = unit.has_line_of_sight(target, self.game.game_map, obstacles)
                
                # Debug: Unit attacking target
                
                # Strategy 1: Pure LOS - if clear path exists, use direct movement
                if has_los:
                    # Debug: Using direct movement - clear LOS
                    pass
                    unit.destination = (target.x, target.y)
                    unit.path = None
                    unit.path_index = 0
                    unit.path_target = None
                    unit.status = "run"
                    unit.current_target = target
                    unit.is_engaging = True
                    unit.has_los = True
                    unit.is_fallback_movement = False  # Clear fallback flag when LOS is available
                    unit.last_task = {"type": "attack", "target": target}
                else:
                    # Strategy 2: No LOS - try pathfinding to get closer
                    pass
                    # Debug: No clear LOS - attempting pathfinding
                    
                    # Try multiple approach positions to increase success chance
                    approach_positions = []
                    
                    # Position 1: Direct approach to target
                    approach_positions.append((target.x, target.y))
                    
                    # Position 2: Stop at attack range distance
                    attack_distance = unit.get_effective_attack_range("approach")
                    if distance > attack_distance:
                        approach_x = target.x - (dx / distance) * attack_distance
                        approach_y = target.y - (dy / distance) * attack_distance
                        approach_positions.append((approach_x, approach_y))
                    
                    # Position 3: Halfway point
                    if distance > unit.get_effective_attack_range("exact") * 2:
                        halfway_x = unit.x + (dx * 0.6)
                        halfway_y = unit.y + (dy * 0.6)
                        approach_positions.append((halfway_x, halfway_y))
                    
                    # Try each position until one works
                    path_found = False
                    for i, (target_x, target_y) in enumerate(approach_positions):
                        path = pathfinder.find_path((unit.x, unit.y), (target_x, target_y), unit.radius, unit)
                        if path:
                            unit.path = path
                            unit.path_index = 0
                            # Use the actual reachable position as target (may be different from requested)
                            unit.path_target = path[-1] if path else (target_x, target_y)
                            unit.destination = path[0] if path else None
                            unit.status = "run"
                            unit.current_target = target
                            unit.is_engaging = True
                            unit.has_los = False
                            unit.is_fallback_movement = False  # Clear fallback flag when pathfinding succeeds
                            
                            # Check if we had to redirect to a different attack position
                            final_pos = path[-1]
                            distance_to_requested = math.sqrt((final_pos[0] - target_x)**2 + (final_pos[1] - target_y)**2)
                            if distance_to_requested > 20:
                                # Debug: Pathfinding redirected to reachable attack position
                                pass
                                pass
                            else:
                                # Debug: Pathfinding successful
                                pass
                                pass
                            path_found = True
                            break
                    
                    # Strategy 3: Direct movement fallback with collision detection
                    if not path_found:
                        # Check if target is completely unreachable due to permanent obstacles
                        pass
                        from systems.pathfinding import Pathfinding
                        temp_pathfinder = Pathfinding(self.game.game_map, self.game)
                        if temp_pathfinder._is_position_permanently_blocked(target.x, target.y, unit.radius):
                            # Try to find a position we can attack from
                            pass
                            closest_reachable = temp_pathfinder._find_closest_reachable_position(
                                (unit.x, unit.y), (target.x, target.y), unit.radius)
                            
                            if closest_reachable:
                                # Debug: Target unreachable - moving to closest attack position
                                pass
                                unit.destination = closest_reachable
                                unit.path = None
                                unit.path_index = 0
                                unit.path_target = closest_reachable
                                unit.status = "run"
                                unit.current_target = target
                                unit.is_engaging = True
                                unit.has_los = False
                                unit.is_fallback_movement = True
                            else:
                                # Debug: Target completely unreachable - cancelling attack
                                pass
                                unit.current_target = None
                                unit.is_engaging = False
                                unit.status = "idle"
                        else:
                            # Debug: Pathfinding failed - direct fallback
                            pass
                            unit.destination = (target.x, target.y)
                            unit.path = None
                            unit.path_index = 0
                            unit.path_target = None
                            unit.status = "run"
                            unit.current_target = target
                            unit.is_engaging = True
                            unit.has_los = False  # Keep LOS accurate - no actual line of sight
                            unit.is_fallback_movement = True  # Flag to indicate this is fallback
    
    def _gather_from_target(self, worker, resource, pathfinder, new_destination=None):
        """Command worker to gather from a resource using a single, reliable pathfinding call"""
        try:
            # Clear any non-gathering state
            worker.current_target = None
            worker.in_combat = False
            worker.is_engaging = False
            worker.is_dropping_off = False
            worker.drop_off_timer = 0.0
            worker.drop_off_target = None
            if hasattr(worker, 'garrison_target'):
                worker.garrison_target = None

            # Set the gathering target so pathfinder doesn't treat it as an obstacle
            pathfinder.gathering_target = resource

            # Determine the destination for pathfinding
            destination = new_destination if new_destination else (resource.x, resource.y)

            # Pathfind to the destination
            path = pathfinder.find_path((worker.x, worker.y), destination, worker.radius, worker)

            if path:
                worker.path = path
                worker.path_index = 0
                worker.path_target = path[-1] if path else destination
                worker.destination = path[0] if path else None
                worker.status = "run"
                worker.gathering_target = resource
                worker.is_engaging = True # Set engaging to true to signal movement towards a target
                worker.last_task = {"type": "gather", "target": resource}

                # Ensure worker is added to resource gatherers list
                if hasattr(resource, 'gatherers') and worker not in resource.gatherers:
                    resource.gatherers.append(worker)
            else:
                # No path found, cancel gathering
                worker.gathering_target = None
                worker.is_engaging = False
                worker.status = "idle"

        except Exception as e:
            import traceback
            traceback.print_exc()
    
    def handle_command_mode_click(self, mouse_pos, command_mode):
        """Handle left click when in command mode"""
        if not self.selected_objects:
            return False
        
        world_pos = self.game.screen_to_world(mouse_pos[0], mouse_pos[1])
        # Debug: Command mode click
        
        # Check what was clicked
        clicked_object = self._get_object_at_position(world_pos)
        
        # Filter selected units based on command mode requirements
        valid_units = self._get_valid_units_for_command(command_mode)
        if not valid_units:
            # Debug: No valid units for command
            pass
            return False
        
        # Validate target based on command mode
        is_valid_target = self._is_valid_target_for_command(command_mode, clicked_object, valid_units)
        if not is_valid_target:
            # Debug: Invalid target for command
            pass
            return False
        
        # Execute the command
        return self._execute_command_mode_action(command_mode, valid_units, world_pos, clicked_object)
    
    def _get_valid_units_for_command(self, command_mode):
        """Get units that can execute the given command"""
        valid_units = []
        
        for unit in self.selected_objects:
            # Only human player units
            pass
            if not (hasattr(unit, 'player') and unit.player and unit.player.human):
                continue
                
            if command_mode == 'move':
                # Any unit that can move
                pass
                if hasattr(unit, 'destination'):
                    valid_units.append(unit)
            elif command_mode == 'gather':
                # Only workers
                pass
                if unit.name == 'worker':
                    valid_units.append(unit)
            elif command_mode == 'deposit':
                # Only workers carrying resources
                pass
                if unit.name == 'worker' and hasattr(unit, 'resource_amount') and unit.resource_amount > 0:
                    valid_units.append(unit)
            elif command_mode == 'attack':
                # Only combat units
                pass
                if hasattr(unit, 'can_attack') and unit.can_attack:
                    valid_units.append(unit)
        
        return valid_units
    
    def _is_valid_target_for_command(self, command_mode, clicked_object, valid_units):
        """Check if the target is valid for the given command"""
        if command_mode == 'move':
            # Can always move to empty space or around objects
            pass
            return True
        elif command_mode == 'gather':
            # Must click on a resource
            pass
            return clicked_object and clicked_object in self.game.resources
        elif command_mode == 'deposit':
            # Must click on a drop-off building
            pass
            if not clicked_object or clicked_object not in self.game.buildings:
                return False
            # Check if any unit can drop off at this building
            for unit in valid_units:
                if self._can_drop_off_at_building(unit, clicked_object):
                    return True
            return False
        elif command_mode == 'attack':
            # Must click on an enemy unit or building
            pass
            if not clicked_object:
                return False
            if clicked_object in self.game.units or clicked_object in self.game.buildings:
                # Check if it's an enemy (different player)
                pass
                human_player = self.game.players[0]
                return (hasattr(clicked_object, 'player') and 
                       clicked_object.player != human_player)
            return False
        
        return False
    
    def _can_drop_off_at_building(self, worker, building):
        """Check if worker can drop off resources at the building"""
        if not hasattr(worker, 'resource_type') or not worker.resource_type:
            return False
            
        resource_type = worker.resource_type
        building_name = building.name
        
        # Castle accepts all resources
        if building_name == "castle":
            return True
        # Mine accepts gold
        elif building_name == "mine" and resource_type == "gold":
            return True
        # Quarry accepts stone  
        elif building_name == "quarry" and resource_type == "stone":
            return True
        # Lumbermill accepts wood
        elif building_name == "lumbermill" and resource_type == "wood":
            return True
            
        return False
    
    def _execute_command_mode_action(self, command_mode, valid_units, world_pos, clicked_object):
        """Execute the command mode action"""
        pathfinder = Pathfinding(self.game.game_map, self.game)
        
        if command_mode == 'move':
            # Use existing movement logic from right-click
            pass
            if len(valid_units) > 1 and not clicked_object:
                # Multiple units to empty space - add offsets
                pass
                offset_radius = 30
                for i, unit in enumerate(valid_units):
                    angle = (i / len(valid_units)) * 2 * math.pi + random.uniform(-0.3, 0.3)
                    offset_x = math.cos(angle) * offset_radius * random.uniform(0.8, 1.2)
                    offset_y = math.sin(angle) * offset_radius * random.uniform(0.8, 1.2)
                    target_pos = (world_pos[0] + offset_x, world_pos[1] + offset_y)
                    self._move_unit_to_position(unit, target_pos, pathfinder)
            else:
                # Single unit or clicking on object
                pass
                for unit in valid_units:
                    self._move_unit_to_position(unit, world_pos, pathfinder)
            
        elif command_mode == 'gather':
            # Command workers to gather from the resource
            pass
            for worker in valid_units:
                self._gather_from_target(worker, clicked_object, pathfinder)
                
        elif command_mode == 'deposit':
            # Command workers to drop off at the building
            pass
            for worker in valid_units:
                if self._can_drop_off_at_building(worker, clicked_object):
                    pathfinder.drop_off_target = clicked_object
                    path = pathfinder.find_path((worker.x, worker.y), (clicked_object.x, clicked_object.y), worker.radius, worker)
                    pathfinder.drop_off_target = None
                    
                    if path:
                        worker.path = path
                        worker.path_index = 0
                        worker.path_target = path[-1]
                        worker.destination = path[0] if path else None
                        worker.drop_off_target = clicked_object
                        worker.status = "run"
                        
        elif command_mode == 'attack':
            # Command units to attack the target
            pass
            for unit in valid_units:
                if hasattr(unit, 'current_target'):
                    unit.current_target = clicked_object
                    unit.status = "run"
                    # Debug: Unit attacking target
        
        # Debug: Executed command
        return True

    def _move_unit_to_position(self, unit, world_pos, pathfinder):
        """Move a unit to a specific position"""
        # Clear any gathering/garrison/drop-off/combat state
        unit.is_gathering = False
        unit.gathering_target = None
        unit.is_dropping_off = False
        unit.drop_off_timer = 0.0
        unit.drop_off_target = None
        unit.current_target = None
        unit.in_combat = False
        unit.is_engaging = False
        if hasattr(unit, 'garrison_target'):
            unit.garrison_target = None
        
        # Find path from unit's current position to target
        # The pathfinder will automatically find closest reachable position if target is blocked
        path = pathfinder.find_path((unit.x, unit.y), world_pos, unit.radius, unit)
        
        if path:
            # Set the path for the unit
            pass
            unit.path = path
            unit.path_index = 0
            # Use the final waypoint as the actual target (may be different from original if target was blocked)
            unit.path_target = path[-1] if path else world_pos
            unit.destination = path[0] if path else None
            unit.status = "run"
            unit.last_task = {"type": "move", "target": world_pos}
            
            # Check if we had to redirect to a different position
            final_target = path[-1]
            distance_to_original = math.sqrt((final_target[0] - world_pos[0])**2 + (final_target[1] - world_pos[1])**2)
            if distance_to_original > 20:  # If we redirected more than 20 units
                # Debug: Unit redirected to closest reachable position
                pass
                pass
        else:
            # No path found - target completely unreachable
            pass
            # Debug: Unit cannot reach target
            unit.path = None
            unit.path_index = 0
            unit.path_target = None
            unit.destination = None
            unit.status = "idle"
    
    def _get_object_at_position(self, world_pos):
        """Get the topmost object at a world position"""
        all_objects = self.game.units + self.game.buildings + self.game.resources
        
        for obj in sorted(all_objects, key=lambda o: o.y, reverse=True):
            distance = math.sqrt((world_pos[0] - obj.x)**2 + (world_pos[1] - obj.y)**2)
            if distance <= obj.radius:
                return obj
        
        return None
    
    def draw_selection_box(self, surface):
        """Draw the selection box if active"""
        if not self.selection_box_active or not self.selection_start_pos:
            return
        
        current_pos = pygame.mouse.get_pos()
        
        # Adjust coordinates for map surface (which is offset by TOP_BAR_HEIGHT)
        start_x = self.selection_start_pos[0]
        start_y = self.selection_start_pos[1] - TOP_BAR_HEIGHT
        end_x = current_pos[0]
        end_y = current_pos[1] - TOP_BAR_HEIGHT
        
        min_x = min(start_x, end_x)
        max_x = max(start_x, end_x)
        min_y = min(start_y, end_y)
        max_y = max(start_y, end_y)
        
        rect = pygame.Rect(min_x, min_y, max_x - min_x, max_y - min_y)
        pygame.draw.rect(surface, (0, 255, 0), rect, 2)
    
    def draw_selection_circles(self, surface, camera):
        """Draw selection circles around selected objects"""
        all_objects = self.game.units + self.game.buildings + self.game.resources
        
        for obj in all_objects:
            if not obj.selected:
                continue
            
            # Convert world position to screen position
            screen_x = (obj.x * camera.zoom) + camera.x
            screen_y = (obj.y * camera.zoom) + camera.y
            
            # Draw selection circle
            radius = int(obj.radius * camera.zoom * 1.2)
            
            # Choose color based on ownership
            if hasattr(obj, 'player') and obj.player:
                if obj.player.human:
                    # Human player - bright green
                    pass
                    color = (0, 255, 0)
                else:
                    # AI player - yellow
                    pass
                    color = (255, 255, 0)
            else:
                # No player (resources) - white
                pass
                color = (255, 255, 255)
            
            # Draw circle
            pygame.draw.circle(surface, color, (int(screen_x), int(screen_y)), radius, 2)
            
            # Draw small tick marks
            for angle in range(0, 360, 45):
                rad = math.radians(angle)
                inner_x = screen_x + (radius - 5) * math.cos(rad)
                inner_y = screen_y + (radius - 5) * math.sin(rad)
                outer_x = screen_x + radius * math.cos(rad)
                outer_y = screen_y + radius * math.sin(rad)
                pygame.draw.line(surface, color, (int(inner_x), int(inner_y)), (int(outer_x), int(outer_y)), 2)
            
            # Draw attack range for buildings that can attack (like watchtowers)
            if hasattr(obj, 'can_attack') and obj.can_attack and hasattr(obj, 'attack_range'):
                # Choose color based on ownership - green for player, red for enemy
                if hasattr(obj, 'player') and obj.player:
                    if obj.player.human:
                        range_color = (0, 255, 0, 64)  # Semi-transparent green
                    else:
                        range_color = (255, 0, 0, 64)  # Semi-transparent red
                else:
                    range_color = (255, 255, 255, 64)  # Semi-transparent white
                
                # Draw attack range circle
                attack_radius = int(obj.attack_range * camera.zoom)
                
                # Create a surface for semi-transparent circle
                range_surface = pygame.Surface((attack_radius * 2 + 4, attack_radius * 2 + 4), pygame.SRCALPHA)
                pygame.draw.circle(range_surface, range_color, (attack_radius + 2, attack_radius + 2), attack_radius, 2)
                
                # Draw the range circle
                surface.blit(range_surface, (int(screen_x - attack_radius - 2), int(screen_y - attack_radius - 2)))
                
                # Also draw a solid outline
                outline_color = range_color[:3]  # Remove alpha
                pygame.draw.circle(surface, outline_color, (int(screen_x), int(screen_y)), attack_radius, 1)
    
    def get_selected_unit_names(self):
        """Get names of selected units"""
        unit_counts = {}
        for obj in self.selected_objects:
            if hasattr(obj, 'destination'):  # Is a unit
                name = obj.name
                unit_counts[name] = unit_counts.get(name, 0) + 1
        
        names = []
        for name, count in unit_counts.items():
            if count > 1:
                names.append(f"{count} {name}s")
            else:
                names.append(name)
        
        return names
    
    def get_action_buttons(self):
        """Get action buttons for selected units"""
        # If no selection or mixed selection, return empty
        if not self.selected_objects:
            return []
        
        # Check if all selected objects are units of the same type
        unit_types = set()
        for obj in self.selected_objects:
            if hasattr(obj, 'destination'):  # Is a unit
                unit_types.add(obj.name)
        
        # If mixed unit types or non-units selected, return basic move/stop
        if len(unit_types) != 1:
            return []
        
        unit_type = list(unit_types)[0]
        
        # Return buttons based on unit type
        if unit_type == "worker":
            return ["move", "stop", "gather", "build"]
        else:
            # Check if any selected unit can attack
            pass
            can_attack = any(hasattr(obj, 'can_attack_flag') and obj.can_attack_flag for obj in self.selected_objects)
            if can_attack:
                return ["move", "stop", "attack"]
            else:
                return ["move", "stop"]
    
    def draw_unit_paths(self, surface, camera):
        """Draw paths for selected units (debug visualization)"""
        if not self.game.debug_overlay:
            return
        
        for unit in self.selected_objects:
            if hasattr(unit, 'path') and unit.path and len(unit.path) > unit.path_index:
                # Draw remaining path
                pass
                path_to_draw = [(unit.x, unit.y)] + unit.path[unit.path_index:]
                
                # Convert to screen coordinates
                screen_path = []
                for x, y in path_to_draw:
                    screen_x = (x * camera.zoom) + camera.x
                    screen_y = (y * camera.zoom) + camera.y
                    screen_path.append((int(screen_x), int(screen_y)))
                
                # Draw path
                if len(screen_path) > 1:
                    pygame.draw.lines(surface, (255, 255, 0), False, screen_path, 2)
                    
                    # Draw waypoints
                    for point in screen_path[1:]:
                        pygame.draw.circle(surface, (255, 200, 0), point, 3)
                
                # Draw final destination
                if unit.path_target:
                    target_screen_x = (unit.path_target[0] * camera.zoom) + camera.x
                    target_screen_y = (unit.path_target[1] * camera.zoom) + camera.y
                    pygame.draw.circle(surface, (255, 0, 0), (int(target_screen_x), int(target_screen_y)), 5, 2)
    
    def draw_attack_targets(self, surface, camera):
        """Draw red circles around units' attack targets"""
        drawn_targets = set()  # Avoid drawing multiple circles on same target
        
        for unit in self.game.units:
            if unit.current_target and unit.current_target not in drawn_targets:
                target = unit.current_target
                
                # Convert world position to screen position
                screen_x = (target.x * camera.zoom) + camera.x
                screen_y = (target.y * camera.zoom) + camera.y
                
                # Draw red circle around target
                radius = int(target.radius * camera.zoom * 1.3)
                pygame.draw.circle(surface, (255, 0, 0), (int(screen_x), int(screen_y)), radius, 3)
                
                # Draw smaller inner circle for emphasis
                inner_radius = int(target.radius * camera.zoom * 0.8)
                pygame.draw.circle(surface, (200, 0, 0), (int(screen_x), int(screen_y)), inner_radius, 2)
                
                drawn_targets.add(target)
    
    def draw_los_debug(self, surface, camera):
        """Draw line of sight debug visualization"""
        if not self.game.debug_overlay:
            return
        
        for unit in self.game.units:
            target = None
            
            # Check for combat targets
            if unit.is_engaging and unit.current_target:
                target = unit.current_target
            # Check for gathering targets
            elif (unit.is_engaging and hasattr(unit, 'gathering_target') and unit.gathering_target):
                target = unit.gathering_target
            
            if target:
                # Draw LOS line
                pass
                unit_screen_x = (unit.x * camera.zoom) + camera.x
                unit_screen_y = (unit.y * camera.zoom) + camera.y
                target_screen_x = (target.x * camera.zoom) + camera.x
                target_screen_y = (target.y * camera.zoom) + camera.y
                
                # Check current LOS - include ALL potential obstacles except target
                if target == unit.current_target:
                    # Combat target - exclude target from obstacles
                    pass
                    obstacles = (self.game.buildings + 
                               [u for u in self.game.units if u != unit and u != target] + 
                               self.game.resources)
                else:
                    # Gathering target - exclude target resource from obstacles
                    pass
                    obstacles = (self.game.buildings + 
                               [u for u in self.game.units if u != unit] + 
                               [r for r in self.game.resources if r != target])
                
                has_los = unit.has_line_of_sight(target, self.game.game_map, obstacles)
                
                # Color code: Green = clear LOS, Red = blocked LOS, Yellow = direct fallback, Blue = gathering
                if target == getattr(unit, 'gathering_target', None):
                    # Gathering target - use blue color scheme
                    pass
                    if has_los:
                        color = (0, 150, 255)  # Blue - gathering with LOS
                        strategy_text = "GATHER_LOS"
                    elif getattr(unit, 'is_fallback_movement', False):
                        color = (255, 150, 0)  # Orange - gathering fallback
                        strategy_text = "GATHER_FALLBACK"
                    elif unit.path:
                        color = (150, 0, 150)  # Purple - gathering pathfinding
                        strategy_text = "GATHER_PATH"
                    else:
                        color = (100, 100, 100)  # Dark gray - gathering no strategy
                        strategy_text = "GATHER_NONE"
                else:
                    # Combat target - use original color scheme
                    pass
                    if has_los:
                        color = (0, 255, 0)  # Green - clear LOS
                        strategy_text = "LOS"
                    elif getattr(unit, 'is_fallback_movement', False):
                        color = (255, 255, 0)  # Yellow - direct movement fallback
                        strategy_text = "FALLBACK"
                    elif unit.path:
                        color = (255, 0, 0)  # Red - pathfinding
                        strategy_text = "PATH"
                    else:
                        color = (128, 128, 128)  # Gray - no strategy
                        strategy_text = "NONE"
                
                # Draw line
                pygame.draw.line(surface, color, 
                               (int(unit_screen_x), int(unit_screen_y)), 
                               (int(target_screen_x), int(target_screen_y)), 3)
                font = pygame.font.Font(None, 24)
                text_surface = font.render(strategy_text, True, color)
                surface.blit(text_surface, (int(unit_screen_x) + 20, int(unit_screen_y) - 10))