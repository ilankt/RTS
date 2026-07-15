import pygame
import math
from core.config import MINIMAP_WIDTH, MINIMAP_HEIGHT, TOP_BAR_HEIGHT, MAP_VIEW_WIDTH, MAP_VIEW_HEIGHT


class SelectionManager:
    """Manages object selection and selection visualization"""
    
    def __init__(self, game):
        self.game = game
        self.selected_objects = []
        self.selection_box_active = False
        self.selection_start_pos = None
        
        # Control groups: 1-9 -> list of units
        self.control_groups = {i: [] for i in range(1, 10)}
        
        # Formation type for group movement
        self.formation_type = "ring"  # ring, line, box, wedge

        # Object currently under the mouse cursor (§7.4 readability:
        # hover highlight). Set by game._update_cursor_for_context.
        self.hovered_object = None
    
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
            start_map_pos = (self.selection_start_pos[0], self.selection_start_pos[1] - TOP_BAR_HEIGHT)
            end_map_pos = (selection_end_pos[0], selection_end_pos[1] - TOP_BAR_HEIGHT)
            self._handle_drag_selection(start_map_pos, end_map_pos)
        
        self.selection_start_pos = None
        
        # Update smart cursor based on new selection
        self._update_smart_cursor_for_selection()
    
    def _handle_single_click(self, mouse_pos):
        """Handle single click selection with proper ownership filtering"""
        # Check all objects for selection (construction sites included, so an
        # abandoned foundation can be selected to cancel or resume it)
        all_objects = [
            obj for obj in (self.game.units + self.game.buildings +
                            self.game.resources + self.game.construction_sites)
            if self._is_object_visible_to_human(obj)
        ]
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
            is_shift_held = pygame.key.get_pressed()[pygame.K_LSHIFT]
            clicked_is_human = hasattr(clicked_object, 'player') and clicked_object.player and clicked_object.player.human
            clicked_is_ai = hasattr(clicked_object, 'player') and clicked_object.player and not clicked_object.player.human
            clicked_is_neutral = not hasattr(clicked_object, 'player') or not clicked_object.player
            
            # Check current selection ownership
            current_has_ai = any(hasattr(obj, 'player') and obj.player and not obj.player.human for obj in self.selected_objects)
            
            # Determine if we should clear selection
            should_clear_selection = False
            
            if not is_shift_held:
                # Always clear if not holding shift
                should_clear_selection = True
            elif clicked_is_ai:
                # Always clear when clicking AI units (never multi-select enemy units)
                should_clear_selection = True
            elif clicked_is_human and current_has_ai:
                # Clear if trying to mix human and AI
                should_clear_selection = True
            elif (clicked_is_neutral and current_has_ai):
                # Clear if trying to mix neutral and AI
                should_clear_selection = True
            
            # Clear selection if needed
            if should_clear_selection:
                self._clear_all_selections()
            
            # Handle selection toggle with Shift
            if clicked_object.selected and is_shift_held and not should_clear_selection:
                # Deselect if already selected and using Shift (and we didn't clear)
                clicked_object.selected = False
                if clicked_object in self.selected_objects:
                    self.selected_objects.remove(clicked_object)
            else:
                # Select the object
                clicked_object.selected = True
                
                # Add to selected_objects based on ownership
                if clicked_is_human:
                    # Human player objects - always add for control
                    if clicked_object not in self.selected_objects:
                        self.selected_objects.append(clicked_object)
                elif clicked_is_neutral:
                    # Neutral objects (resources) - add for interaction
                    if clicked_object not in self.selected_objects:
                        self.selected_objects.append(clicked_object)
                # Note: AI objects are not added to selected_objects (visual selection only)
            if clicked_is_human:
                self._play_human_sound("select")
        else:
            # No object clicked - clear selection unless shift is held
            is_shift_held = pygame.key.get_pressed()[pygame.K_LSHIFT]
            if not is_shift_held:
                self._clear_all_selections()
    
    def _categorize_objects_in_rect(self, selection_rect):
        """Categorize objects in selection rectangle by type and ownership"""
        units = []
        buildings = []
        resources = []
        
        all_objects = [
            obj for obj in self.game.units + self.game.buildings + self.game.resources
            if self._is_object_visible_to_human(obj)
        ]
        
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
            if ai_objects:
                return []
            # Only return human objects for multi-selection
            return human_objects + neutral_objects
        else:
            # Single selection - allow any object but prioritize human player
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
            filtered_units = self._filter_selectable_objects(units, allow_multi_select=True)
            objects_to_select = filtered_units
        elif buildings:
            # No units, but there are buildings
            filtered_buildings = self._filter_selectable_objects(buildings, allow_multi_select=True)
            objects_to_select = filtered_buildings
        elif resources:
            # Only resources available
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
            try:
                if hasattr(self.game, 'ui_manager') and self.game.ui_manager:
                    self.game.ui_manager.set_smart_cursor_for_units(selected_units)
            except:
                pass
        else:
            # No units selected, restore default cursor
            try:
                if hasattr(self.game, 'ui_manager') and self.game.ui_manager and self.game.ui_manager.default_cursor:
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
        # Check if clicking on a resource or building
        clicked_object = self._get_object_at_position(world_pos)
        
        # Use singleton pathfinder
        pathfinder = self.game.pathfinder
        
        # Filter only human player units that can move
        movable_units = [obj for obj in self.selected_objects
                        if hasattr(obj, 'destination') and obj.player and obj.player.human]

        # Rally points (§7.4): right-click with own production building(s)
        # selected (and no movable units) sets where new units go on spawn.
        if not movable_units:
            rally_buildings = [
                obj
                for obj in self.selected_objects
                if getattr(obj, "can_produce", None)
                and getattr(obj, "in_world", True)
                and obj.player
                and obj.player.human
            ]
            if rally_buildings:
                rally_resource = clicked_object if clicked_object in self.game.resources else None
                for building in rally_buildings:
                    if rally_resource is not None:
                        building.rally_point = (rally_resource.x, rally_resource.y)
                        building.rally_resource = rally_resource
                    else:
                        building.rally_point = world_pos
                        building.rally_resource = None
                self._play_human_sound("move")
                self._add_order_flash(world_pos, "rally")
                return

        # Shift held = queue the command instead of replacing the current one
        keys = pygame.key.get_pressed()
        shift_held = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]

        # If multiple units moving to empty space, use hexagonal ring formation
        if len(movable_units) > 1 and not clicked_object:
            positions = self._generate_formation_offsets(len(movable_units))
            slots = [
                (world_pos[0] + offset_x, world_pos[1] + offset_y)
                for offset_x, offset_y in positions
            ]
            # Large groups ride ONE shared flow field (Phase 5) instead of
            # issuing a path search per unit (immediate orders only; queued
            # waypoints execute per unit later).
            if not shift_held and len(movable_units) >= 8 and pathfinder.request_group_move(movable_units, world_pos, slots):
                self._play_human_sound("move")
            else:
                for obj, target_pos in zip(movable_units, slots):
                    self._issue_or_queue(obj, ("move", target_pos), shift_held)
            self._add_order_flash(world_pos, "move")
        else:
            # Command units normally (single unit or clicking on object)
            flash_kind = "move"
            for obj in movable_units:
                spec = self._command_spec_for(obj, clicked_object, world_pos)
                if spec[0] in ("gather", "dropoff", "garrison", "build"):
                    flash_kind = "gather"
                elif spec[0] == "attack":
                    flash_kind = "attack"
                self._issue_or_queue(obj, spec, shift_held)
            if movable_units:
                self._play_human_sound("move")
                target = clicked_object if clicked_object is not None else None
                flash_pos = (target.x, target.y) if target is not None else world_pos
                self._add_order_flash(flash_pos, flash_kind)

    def _add_order_flash(self, world_pos, kind):
        """Instant command feedback (§7.4): a brief ring at the order target."""
        flashes = getattr(self.game, "order_flashes", None)
        if flashes is None:
            flashes = self.game.order_flashes = []
        flashes.append((world_pos[0], world_pos[1], kind, pygame.time.get_ticks()))

    # Right-clicking one of these with an empty worker means "work this
    # drop-off": gather its resource type nearby (§7.4 smart commands).
    DROPOFF_RESOURCE = {"lumbermill": "wood", "mine": "gold", "quarry": "stone"}

    def _command_spec_for(self, unit, clicked_object, world_pos):
        """Resolve a right-click into a (kind, payload) command spec."""
        if clicked_object:
            if clicked_object in self.game.resources and unit.name == "worker":
                return ("gather", clicked_object)
            if (
                clicked_object in self.game.buildings
                and clicked_object.player is unit.player
                and clicked_object.name in ("castle", "watchtower")
                and not (unit.name == "worker" and unit.resource_amount > 0
                         and clicked_object.name == "castle")
            ):
                # §8.9 garrison: right-click own castle/watchtower shelters
                # the unit (a carrying worker still drops off at the castle
                # first — that rule is right below)
                return ("garrison", clicked_object)
            if (
                clicked_object in self.game.buildings
                and unit.name == "worker"
                and unit.resource_amount > 0
            ):
                return ("dropoff", clicked_object)
            if (
                clicked_object in self.game.construction_sites
                and unit.name == "worker"
                and clicked_object.player is unit.player
            ):
                return ("build", clicked_object)  # resume an abandoned foundation
            if (
                clicked_object in self.game.buildings
                and unit.name == "worker"
                and clicked_object.player is unit.player
                and clicked_object.name in self.DROPOFF_RESOURCE
            ):
                resource = self._nearest_resource_to(
                    clicked_object, self.DROPOFF_RESOURCE[clicked_object.name]
                )
                if resource is not None:
                    return ("gather", resource)
            if hasattr(clicked_object, 'player') and clicked_object.player != unit.player:
                if unit.can_attack_flag:
                    return ("attack", clicked_object)
                return ("move", world_pos)
            return ("move", world_pos)
        return ("move", world_pos)

    def _nearest_resource_to(self, building, resource_name, max_distance=400):
        """Closest live resource of a type around a drop-off building."""
        best, best_sq = None, max_distance * max_distance
        for resource in self.game.resources:
            if resource.name != resource_name or getattr(resource, "amount_remaining", 0) <= 0:
                continue
            d_sq = (resource.x - building.x) ** 2 + (resource.y - building.y) ** 2
            if d_sq < best_sq:
                best, best_sq = resource, d_sq
        return best

    def _issue_or_queue(self, unit, spec, shift_held):
        """Execute a command spec now, or queue it while the unit is busy (§7.4)."""
        queue = getattr(unit, "command_queue", None)
        if queue is None:
            queue = unit.command_queue = []
        if shift_held and self._unit_busy(unit):
            if len(queue) < 8:
                queue.append(spec)
            return
        if not shift_held:
            queue.clear()
        self._execute_command_spec(unit, spec)

    def _unit_busy(self, unit):
        """Does the unit have a command in flight (so new ones should queue)?"""
        worker_tasks = getattr(self.game, "worker_task_system", None)
        if worker_tasks and worker_tasks.owns(unit):
            return True
        return bool(
            unit.path
            or unit.destination
            or getattr(unit, "flow_field", None) is not None
            or getattr(unit, "_pending_path_seq", None) is not None
            or unit.is_gathering
            or unit.is_building
            or unit.in_combat
            or unit.is_engaging
        )

    def _execute_command_spec(self, unit, spec):
        """Run one (kind, payload) command spec."""
        kind, payload = spec
        pathfinder = self.game.pathfinder
        if kind == "move":
            self._move_unit_to_position(unit, payload, pathfinder)
        elif kind == "gather":
            if getattr(payload, "in_world", True) and getattr(payload, "amount_remaining", 0) > 0:
                self._gather_from_target(unit, payload, pathfinder)
        elif kind == "attack":
            if getattr(payload, "in_world", True) and getattr(payload, "hp", 0) > 0:
                self._attack_target(unit, payload, pathfinder)
        elif kind == "dropoff":
            if getattr(payload, "in_world", True):
                worker_tasks = getattr(self.game, "worker_task_system", None)
                if worker_tasks:
                    worker_tasks.assign_dropoff(unit, payload)
                else:
                    pathfinder.issue_interact(unit, payload, "dropoff")
        elif kind == "garrison":
            if getattr(payload, "in_world", True):
                self._garrison_worker(unit, payload, pathfinder)
        elif kind == "build":
            if getattr(payload, "in_world", True) and payload in self.game.construction_sites:
                worker_tasks = getattr(self.game, "worker_task_system", None)
                if worker_tasks:
                    worker_tasks.assign_build(unit, payload)
                else:
                    pathfinder.issue_interact(unit, payload, "build")

    def _garrison_worker(self, unit, building, pathfinder):
        """Send a unit to garrison into a castle/watchtower (§8.9)."""
        from systems import garrison

        if not garrison.can_accept(building, unit):
            return
        if hasattr(self.game, "worker_task_system") and unit.name == "worker":
            self.game.worker_task_system.cancel(unit)
        unit.is_dropping_off = False
        unit.drop_off_timer = 0.0
        unit.drop_off_target = None

        # Already adjacent: step straight in
        if garrison.try_enter(self.game, unit, building):
            return

        path = pathfinder.find_path((unit.x, unit.y), (building.x, building.y), unit.radius, unit)
        if path:
            unit.path = path
            unit.path_index = 0
            unit.path_target = path[-1]  # Use actual reachable position
            unit.destination = path[0] if path else None
            unit.garrison_target = building  # Mark for garrisoning
            unit.status = "run"

    def drain_command_queues(self):
        """Pop the next queued command for units that finished their current
        one (called once per frame from the game loop)."""
        for unit in self.game.units:
            queue = getattr(unit, "command_queue", None)
            if not queue or unit.hp <= 0 or self._unit_busy(unit):
                continue
            self._execute_command_spec(unit, queue.pop(0))
    
    def _attack_target(self, unit, target, pathfinder, new_destination=None):
        """Command unit to attack a target"""
        if unit.can_attack(target):
            unit.start_attack(target)
            unit.last_task = {"type": "attack", "target": target}
            self._play_unit_sound(unit, "attack")
            return

        if pathfinder.issue_interact(unit, target, "attack"):
            self._play_unit_sound(unit, "attack")
            return

        unit.current_target = None
        unit.is_engaging = False
        unit.status = "idle"
    
    def _gather_from_target(self, worker, resource, pathfinder, new_destination=None):
        """Command worker to gather from a resource using a single, reliable pathfinding call"""
        worker_tasks = getattr(self.game, "worker_task_system", None)
        if worker_tasks and worker_tasks.assign_gather(worker, resource):
            worker.last_task = {"type": "gather", "target": resource}
            self._play_unit_sound(worker, "gather")
            return
        if not worker_tasks and pathfinder.issue_interact(worker, resource, "gather", preferred_point=new_destination):
            worker.last_task = {"type": "gather", "target": resource}
            self._play_unit_sound(worker, "gather")
            return

        worker.gathering_target = None
        worker.is_engaging = False
        worker.status = "idle"
    
    def handle_command_mode_click(self, mouse_pos, command_mode):
        """Handle left click when in command mode"""
        if not self.selected_objects:
            return False
        
        world_pos = self.game.screen_to_world(mouse_pos[0], mouse_pos[1])
        # Check what was clicked
        clicked_object = self._get_object_at_position(world_pos)
        
        # Filter selected units based on command mode requirements
        valid_units = self._get_valid_units_for_command(command_mode)
        if not valid_units:
            return False
        
        # Validate target based on command mode
        is_valid_target = self._is_valid_target_for_command(command_mode, clicked_object, valid_units)
        if not is_valid_target:
            return False
        
        # Execute the command
        return self._execute_command_mode_action(command_mode, valid_units, world_pos, clicked_object)
    
    def _get_valid_units_for_command(self, command_mode):
        """Get units that can execute the given command"""
        valid_units = []
        
        for unit in self.selected_objects:
            # Only human player units
            if not (hasattr(unit, 'player') and unit.player and unit.player.human):
                continue
                
            if command_mode == 'move':
                # Any unit that can move
                if hasattr(unit, 'destination'):
                    valid_units.append(unit)
            elif command_mode == 'gather':
                # Only workers
                if unit.name == 'worker':
                    valid_units.append(unit)
            elif command_mode == 'deposit':
                # Only workers carrying resources
                if unit.name == 'worker' and hasattr(unit, 'resource_amount') and unit.resource_amount > 0:
                    valid_units.append(unit)
            elif command_mode == 'attack':
                # Only combat units
                if hasattr(unit, 'can_attack') and unit.can_attack:
                    valid_units.append(unit)
        
        return valid_units
    
    def _is_valid_target_for_command(self, command_mode, clicked_object, valid_units):
        """Check if the target is valid for the given command"""
        if command_mode == 'move':
            # Can always move to empty space or around objects
            return True
        elif command_mode == 'gather':
            # Must click on a resource
            return clicked_object and clicked_object in self.game.resources
        elif command_mode == 'deposit':
            # Must click on a drop-off building
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
        pathfinder = self.game.pathfinder
        
        if command_mode == 'move':
            # Use existing movement logic from right-click
            if len(valid_units) > 1 and not clicked_object:
                # Multiple units to empty space - use hexagonal formation
                positions = self._generate_formation_offsets(len(valid_units))
                for i, unit in enumerate(valid_units):
                    offset_x, offset_y = positions[i]
                    target_pos = (world_pos[0] + offset_x, world_pos[1] + offset_y)
                    self._move_unit_to_position(unit, target_pos, pathfinder)
            else:
                # Single unit or clicking on object
                for unit in valid_units:
                    self._move_unit_to_position(unit, world_pos, pathfinder)
            
        elif command_mode == 'gather':
            # Command workers to gather from the resource
            for worker in valid_units:
                self._gather_from_target(worker, clicked_object, pathfinder)
                
        elif command_mode == 'deposit':
            # Command workers to drop off at the building
            for worker in valid_units:
                if self._can_drop_off_at_building(worker, clicked_object):
                    worker_tasks = getattr(self.game, "worker_task_system", None)
                    if worker_tasks:
                        worker_tasks.assign_dropoff(worker, clicked_object)
                    else:
                        pathfinder.issue_interact(worker, clicked_object, "dropoff")
                        
        elif command_mode == 'attack':
            # Command units to attack the target
            for unit in valid_units:
                if hasattr(unit, 'current_target'):
                    self._attack_target(unit, clicked_object, pathfinder)
        
        return True

    def _move_unit_to_position(self, unit, world_pos, pathfinder):
        """Move a unit to a specific position"""
        if unit.name == "worker" and hasattr(self.game, "worker_task_system"):
            self.game.worker_task_system.assign_move(unit, world_pos)
            self._play_unit_sound(unit, "move")
            return
        pathfinder.issue_move(unit, world_pos)
        self._play_unit_sound(unit, "move")

    def _play_unit_sound(self, unit, sound_type):
        if not getattr(getattr(unit, "player", None), "human", False):
            return
        # Pass the unit type through so barks / per-type variants play (§8.5)
        self._play_human_sound(sound_type, getattr(unit, "name", None))

    def _play_human_sound(self, sound_type, unit_name=None):
        sound_manager = getattr(self.game, "sound_manager", None)
        if not sound_manager:
            return
        if sound_type == "select":
            sound_manager.play_select(unit_name)
        elif sound_type == "move":
            sound_manager.play_move_order(unit_name)
        elif sound_type == "attack":
            sound_manager.play_attack(unit_name)
        elif sound_type == "gather":
            sound_manager.play_gather()
    
    def cycle_formation(self):
        """Cycle to the next formation type"""
        formations = ["ring", "line", "box", "wedge"]
        idx = formations.index(self.formation_type) if self.formation_type in formations else 0
        self.formation_type = formations[(idx + 1) % len(formations)]
        return self.formation_type
    
    def _generate_formation_offsets(self, count):
        """Generate formation offsets for group movement based on current formation type."""
        spacing = 22  # unit diameter 16 + buffer 6
        
        if self.formation_type == "line":
            return self._generate_line_formation(count, spacing)
        elif self.formation_type == "box":
            return self._generate_box_formation(count, spacing)
        elif self.formation_type == "wedge":
            return self._generate_wedge_formation(count, spacing)
        else:
            return self._generate_ring_formation(count, spacing)
    
    def _generate_ring_formation(self, count, spacing):
        """Hexagonal ring formation."""
        offsets = [(0, 0)]  # Center
        ring = 1
        while len(offsets) < count:
            positions_in_ring = ring * 6
            for k in range(positions_in_ring):
                angle = k * (2 * math.pi / positions_in_ring)
                offsets.append((math.cos(angle) * spacing * ring, math.sin(angle) * spacing * ring))
            ring += 1
        return offsets[:count]
    
    def _generate_line_formation(self, count, spacing):
        """Horizontal line formation."""
        offsets = []
        for i in range(count):
            x = (i - count // 2) * spacing
            offsets.append((x, 0))
        return offsets
    
    def _generate_box_formation(self, count, spacing):
        """Box/grid formation."""
        import math
        cols = math.ceil(math.sqrt(count))
        offsets = []
        for i in range(count):
            col = i % cols
            row = i // cols
            x = (col - (cols - 1) / 2) * spacing
            y = row * spacing
            offsets.append((x, y))
        return offsets
    
    def _generate_wedge_formation(self, count, spacing):
        """Wedge/V formation (good for charges)."""
        offsets = [(0, 0)]  # Tip of wedge
        row = 1
        idx = 1
        while idx < count:
            for col in range(-row, row + 1):
                if idx >= count:
                    break
                x = col * spacing
                y = row * spacing
                offsets.append((x, y))
                idx += 1
            row += 1
        return offsets[:count]

    def _get_object_at_position(self, world_pos):
        """Get the topmost object at a world position"""
        all_objects = [
            obj for obj in (self.game.units + self.game.buildings +
                            self.game.resources + self.game.construction_sites)
            if self._is_object_visible_to_human(obj)
        ]
        
        for obj in sorted(all_objects, key=lambda o: o.y, reverse=True):
            distance = math.sqrt((world_pos[0] - obj.x)**2 + (world_pos[1] - obj.y)**2)
            if distance <= obj.radius:
                return obj
        
        return None

    def _is_object_visible_to_human(self, obj):
        fog = getattr(self.game, "fog_of_war", None)
        if not fog or not getattr(fog, "enabled", True):
            return True
        return fog.is_object_visible(obj)
    
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
        self._draw_rally_flags(surface, camera)
        all_objects = [
            obj for obj in (self.game.units + self.game.buildings +
                            self.game.resources + self.game.construction_sites)
            if self._is_object_visible_to_human(obj)
        ]

        for obj in all_objects:
            if not obj.selected:
                continue

            # Convert world position to screen position
            screen_x = (obj.x * camera.zoom) + camera.x
            screen_y = (obj.y * camera.zoom) + camera.y

            # Selection marker: a subtle ground ellipse at the feet instead of
            # the old debug-green circle + tick marks (user feedback)
            if hasattr(obj, 'player') and obj.player:
                color = (235, 235, 235) if obj.player.human else (230, 175, 80)
            else:
                color = (200, 200, 200)  # resources / neutral

            ellipse_w = max(12, int(obj.radius * 2.2 * camera.zoom))
            ellipse_h = max(5, int(ellipse_w * 0.38))
            feet_y = screen_y + obj.radius * camera.zoom * 0.55
            marker = pygame.Rect(int(screen_x - ellipse_w / 2),
                                 int(feet_y - ellipse_h / 2), ellipse_w, ellipse_h)
            pygame.draw.ellipse(surface, color, marker, 2)
            # (The attack-range ring that used to draw here was removed —
            # user feedback: "remove the ugly range ring from selected units")

        self._draw_hover_marker(surface, camera)

    def _draw_hover_marker(self, surface, camera):
        """§7.4 readability: a dimmer, thinner ground ellipse under the object
        the mouse is over, so hover targets read before you click."""
        obj = self.hovered_object
        if obj is None or getattr(obj, 'selected', False):
            return
        # The hover ref is only refreshed on mouse motion — drop it if the
        # object has since died/depleted or slipped back under the fog.
        if not getattr(obj, 'in_world', True) or getattr(obj, 'hp', 1) <= 0:
            self.hovered_object = None
            return
        if not self._is_object_visible_to_human(obj):
            return

        if hasattr(obj, 'player') and obj.player:
            color = (200, 200, 200) if obj.player.human else (200, 150, 70)
        else:
            color = (170, 170, 170)  # resources / neutral

        screen_x = (obj.x * camera.zoom) + camera.x
        screen_y = (obj.y * camera.zoom) + camera.y
        ellipse_w = max(12, int(obj.radius * 2.2 * camera.zoom))
        ellipse_h = max(5, int(ellipse_w * 0.38))
        feet_y = screen_y + obj.radius * camera.zoom * 0.55
        marker = pygame.Rect(int(screen_x - ellipse_w / 2),
                             int(feet_y - ellipse_h / 2), ellipse_w, ellipse_h)
        pygame.draw.ellipse(surface, color, marker, 1)
    
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
    
    def set_control_group(self, group_number, add=False):
        """Assign selected human units AND buildings to a control group (1-9)
        — buildings joining groups is the §8.2.1 Phase B production model.
        If add=True, append to existing group instead of replacing."""
        if not 1 <= group_number <= 9:
            return

        selected_members = [
            obj for obj in self.selected_objects
            if (obj in self.game.units or obj in self.game.buildings)
            and hasattr(obj, 'player') and obj.player and obj.player.human
        ]

        if add and self.control_groups[group_number]:
            # Add to existing group, avoiding duplicates
            existing = set(id(u) for u in self.control_groups[group_number])
            for member in selected_members:
                if id(member) not in existing:
                    self.control_groups[group_number].append(member)
        else:
            self.control_groups[group_number] = selected_members[:]
    
    def _draw_rally_flags(self, surface, camera):
        """Line + flag from selected own production buildings to their rally point."""
        for obj in self.selected_objects:
            rally = getattr(obj, "rally_point", None)
            if rally is None or not getattr(obj, "player", None) or not obj.player.human:
                continue
            start = ((obj.x * camera.zoom) + camera.x, (obj.y * camera.zoom) + camera.y)
            end = ((rally[0] * camera.zoom) + camera.x, (rally[1] * camera.zoom) + camera.y)
            pygame.draw.line(surface, (240, 220, 90), start, end, 1)
            pole_top = (end[0], end[1] - 14)
            pygame.draw.line(surface, (240, 220, 90), end, pole_top, 2)
            pygame.draw.polygon(
                surface,
                (240, 220, 90),
                [pole_top, (pole_top[0] + 10, pole_top[1] + 3), (pole_top[0], pole_top[1] + 7)],
            )

    def center_camera_on_selection(self):
        """Center the camera on the centroid of the current selection."""
        if not self.selected_objects:
            return False
        centroid_x = sum(obj.x for obj in self.selected_objects) / len(self.selected_objects)
        centroid_y = sum(obj.y for obj in self.selected_objects) / len(self.selected_objects)
        camera = self.game.camera
        camera.x = -centroid_x * camera.zoom + MAP_VIEW_WIDTH / 2
        camera.y = -centroid_y * camera.zoom + MAP_VIEW_HEIGHT / 2
        return True

    def get_idle_workers(self):
        """Human player's idle workers (§7.4 idle-worker management)."""
        players = self.game.players
        human = players[0] if players and getattr(players[0], "human", False) else None
        if human is None:
            return []
        is_idle = self.game.ai_system.worker_brain._is_idle
        return [
            u
            for u in self.game.units
            if u.player is human and u.name == "worker" and u.hp > 0 and is_idle(u)
        ]

    def select_next_idle_worker(self):
        """Select and center on the next idle worker (F1). Returns True if any."""
        idle = self.get_idle_workers()
        if not idle:
            return False
        self._idle_cycle_index = (getattr(self, "_idle_cycle_index", -1) + 1) % len(idle)
        worker = idle[self._idle_cycle_index]

        self._clear_all_selections()
        worker.selected = True
        self.selected_objects.append(worker)
        self._update_smart_cursor_for_selection()

        camera = self.game.camera
        camera.x = -worker.x * camera.zoom + MAP_VIEW_WIDTH / 2
        camera.y = -worker.y * camera.zoom + MAP_VIEW_HEIGHT / 2
        self._play_unit_sound(worker, "select")
        return True

    def select_all_military_production(self):
        """Select every own building that produces military units (§8.2.1 C)
        so one hotkey drives the whole army's production card. Returns True
        if anything was selected."""
        players = self.game.players
        human = players[0] if players and getattr(players[0], "human", False) else None
        if human is None:
            return False
        producers = [
            b for b in self.game.buildings
            if b.player is human and b.hp > 0
            and any(u != "worker" for u in (getattr(b, "can_produce", None) or ()))
        ]
        if not producers:
            return False
        self._clear_all_selections()
        for building in producers:
            building.selected = True
            self.selected_objects.append(building)
        return True

    def recall_control_group(self, group_number):
        """Select a control group's members (1-9), units and buildings alike.
        Returns True if the group had live members."""
        if not 1 <= group_number <= 9:
            return False

        members = self.control_groups.get(group_number, [])
        # Filter out dead/gone members
        valid_members = [
            m for m in members
            if (m in self.game.units or m in self.game.buildings) and m.hp > 0
        ]
        self.control_groups[group_number] = valid_members

        if not valid_members:
            return False

        self._clear_all_selections()
        for member in valid_members:
            member.selected = True
            self.selected_objects.append(member)

        self._update_smart_cursor_for_selection()
        return True
    
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
        """Draw red circles around units' attack targets.

        Skipped entirely in spectator mode (user request): with every AI
        unit ringing its target the map filled with red circles."""
        if getattr(self.game, "spectator_mode", False):
            return
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
                unit_screen_x = (unit.x * camera.zoom) + camera.x
                unit_screen_y = (unit.y * camera.zoom) + camera.y
                target_screen_x = (target.x * camera.zoom) + camera.x
                target_screen_y = (target.y * camera.zoom) + camera.y
                
                # Check current LOS - include ALL potential obstacles except target
                if target == unit.current_target:
                    # Combat target - exclude target from obstacles
                    obstacles = (self.game.buildings + 
                               [u for u in self.game.units if u != unit and u != target] + 
                               self.game.resources)
                else:
                    # Gathering target - exclude target resource from obstacles
                    obstacles = (self.game.buildings + 
                               [u for u in self.game.units if u != unit] + 
                               [r for r in self.game.resources if r != target])
                
                has_los = unit.has_line_of_sight(target, self.game.game_map, obstacles)
                
                # Color code: Green = clear LOS, Red = blocked LOS, Yellow = direct fallback, Blue = gathering
                if target == getattr(unit, 'gathering_target', None):
                    # Gathering target - use blue color scheme
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
