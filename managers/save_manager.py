import json
import os
from datetime import datetime

from core.app_paths import user_path


class SaveManager:
    """Handles saving and loading game state"""

    # Relative when run from source; under %LOCALAPPDATA%\RTS when frozen.
    SAVE_DIR = user_path("saves")
    
    @classmethod
    def ensure_save_dir(cls):
        if not os.path.exists(cls.SAVE_DIR):
            os.makedirs(cls.SAVE_DIR)
    
    @classmethod
    def save_game(cls, game, slot=0):
        """Save current game state to a JSON file"""
        cls.ensure_save_dir()
        
        # Build serializable state
        state = {
            "version": 2,
            "timestamp": datetime.now().isoformat(),
            "map_size": ([game.game_map.width, game.game_map.height]
                         if getattr(game, "game_map", None) else None),
            "players": [],
            "buildings": [],
            "units": [],
            "resources": [],
            "construction_sites": [],
            "camera": {
                "x": game.camera.x,
                "y": game.camera.y,
                "zoom": game.camera.zoom,
            },
            "game_speed": game.game_speed,
            # v2 (§9 save/load completeness)
            "sim_time_elapsed": getattr(game, "sim_time_elapsed", 0.0),
            "victory_condition": getattr(game, "victory_condition", "annihilation"),
            "mutators": sorted(getattr(game, "mutators", ())),
            "fog_enabled": bool(getattr(getattr(game, "fog_of_war", None), "enabled", True)),
            "tree_regrowth": list(getattr(game, "_tree_regrowth", [])),
            "fountains": [[f.x, f.y] for f in getattr(game, "fountains", ())],
            "stats_units_trained": {f"{k[0]}|{k[1]}": v for k, v in getattr(game, "stats_units_trained", {}).items()},
            "stats_buildings_built": {f"{k[0]}|{k[1]}": v for k, v in getattr(game, "stats_buildings_built", {}).items()},
            "stats_tower_damage": dict(getattr(game, "stats_tower_damage", {})),
            "stats_resources_gathered": dict(getattr(game, "stats_resources_gathered", {})),
            "fog_explored": cls._serialize_fog(game),
        }
        
        # Save players
        for i, player in enumerate(game.players):
            state["players"].append({
                "index": i,
                "name": player.name,
                "human": player.human,
                "color": player.color,
                "resources": dict(player.resources),
                "upgrades": list(getattr(player, "upgrades", {}).keys()),
            })
        
        # Save buildings
        for building in game.buildings:
            state["buildings"].append({
                "name": building.name,
                "x": building.x,
                "y": building.y,
                "hp": building.hp,
                "player_index": game.players.index(building.player) if building.player in game.players else -1,
                "current_research": {
                    "tech_id": building.current_research["tech_id"],
                    "progress": building.current_research["progress"],
                } if getattr(building, "current_research", None) else None,
                "research_queue": list(getattr(building, "research_queue", [])),
                # v2: production, rally, gate state
                "current_production": {
                    "unit_type": building.current_production["unit_type"],
                    "progress": building.current_production["progress"],
                } if getattr(building, "current_production", None) else None,
                "production_queue": list(getattr(building, "production_queue", [])),
                "rally_point": list(building.rally_point) if getattr(building, "rally_point", None) else None,
                "passable": bool(getattr(building, "passable", False)),
            })
        
        # Save units. Garrisoned units (§8.9) are OUT of game.units — they
        # serialize like any unit plus the index of their host building.
        def _unit_dict(unit, garrisoned_building=None):
            return {
                "name": unit.name,
                "x": unit.x,
                "y": unit.y,
                "hp": unit.hp,
                "player_index": game.players.index(unit.player) if unit.player in game.players else -1,
                "stance": getattr(unit, "stance", "aggressive"),
                "stance_home_position": list(unit.stance_home_position) if getattr(unit, "stance_home_position", None) else None,
                "resource_type": getattr(unit, "resource_type", None),
                "resource_amount": getattr(unit, "resource_amount", 0),
                "garrisoned_building": garrisoned_building,
            }

        for unit in game.units:
            state["units"].append(_unit_dict(unit))
        for building_index, building in enumerate(game.buildings):
            for unit in getattr(building, "garrison", ()):
                state["units"].append(_unit_dict(unit, garrisoned_building=building_index))
        
        # Save resources
        for resource in game.resources:
            state["resources"].append({
                "name": resource.name,
                "x": resource.x,
                "y": resource.y,
                "amount_remaining": getattr(resource, "amount_remaining", 1000),
            })
        
        # Save construction sites
        for site in game.construction_sites:
            state["construction_sites"].append({
                "building_name": site.building_name,
                "x": site.x,
                "y": site.y,
                "hp": site.hp,
                "player_index": game.players.index(site.player) if site.player in game.players else -1,
                "construction_progress": getattr(site, "construction_progress", 0),
                "construction_duration": getattr(site, "construction_duration", site.building_data.get("build_duration", 10)) if hasattr(site, "building_data") else 10,
            })
        
        filepath = os.path.join(cls.SAVE_DIR, f"save_{slot}.json")
        with open(filepath, "w") as f:
            json.dump(state, f, indent=2)
        
        return filepath
    
    @classmethod
    def _serialize_fog(cls, game):
        """Explored tiles per player index, one '01' string per row."""
        fog = getattr(game, "fog_of_war", None)
        if not fog:
            return {}
        out = {}
        for index, player in enumerate(game.players):
            grid = fog.visibility_grid.get(player)
            if grid is None:
                continue
            out[str(index)] = ["".join("1" if cell >= fog.EXPLORED else "0" for cell in row) for row in grid]
        return out

    @classmethod
    def _restore_fog(cls, game, fog_state):
        fog = getattr(game, "fog_of_war", None)
        if not fog or not fog_state:
            return
        for index_str, rows in fog_state.items():
            index = int(index_str)
            if index >= len(game.players):
                continue
            player = game.players[index]
            fog._init_player_grid(player)
            grid = fog.visibility_grid[player]
            explored = 0
            for r, row in enumerate(rows[: fog.map_height]):
                for c, flag in enumerate(row[: fog.map_width]):
                    if flag == "1":
                        grid[r][c] = fog.EXPLORED
                        explored += 1
            fog._explored_count[player] = explored

    @classmethod
    def peek_map_size(cls, slot=0):
        """The save's map dimensions (w, h), so the loader can construct a
        matching Game before restoring objects. None when unknown."""
        filepath = os.path.join(cls.SAVE_DIR, f"save_{slot}.json")
        try:
            with open(filepath, "r") as f:
                size = json.load(f).get("map_size")
            if size and len(size) == 2:
                return int(size[0]), int(size[1])
        except (OSError, ValueError, TypeError):
            pass
        return None

    @classmethod
    def load_game(cls, game, slot=0):
        """Load game state from a JSON file into the existing game object"""
        filepath = os.path.join(cls.SAVE_DIR, f"save_{slot}.json")
        if not os.path.exists(filepath):
            return False, f"Save file not found: {filepath}"
        
        with open(filepath, "r") as f:
            state = json.load(f)
        
        # Validate version (v1 saves load with v2 fields defaulting)
        if state.get("version") not in (1, 2):
            return False, "Unsupported save version"
        
        # Clear existing state (mark old objects dead so stale references fail
        # liveness checks instead of pointing at ghosts)
        for obj in game.buildings + game.units + game.resources + game.construction_sites:
            obj.in_world = False
        game.buildings.clear()
        game.units.clear()
        game.resources.clear()
        game.construction_sites.clear()
        game.selection_manager.selected_objects.clear()
        if hasattr(game, "worker_task_system"):
            for worker in list(game.worker_task_system.tasks.keys()):
                game.worker_task_system.cancel(worker)
        
        # Restore players
        player_map = {}
        for player_data in state["players"]:
            idx = player_data["index"]
            if idx < len(game.players):
                player = game.players[idx]
                player.name = player_data["name"]
                player.human = player_data["human"]
                player.color = tuple(player_data["color"])
                player.resources = player_data["resources"]
                player.upgrades = {
                    tech_id: game.game_data.get("techs", {}).get(tech_id)
                    for tech_id in player_data.get("upgrades", [])
                    if tech_id in game.game_data.get("techs", {})
                }
                player.upgrades_version = getattr(player, "upgrades_version", 0) + 1
                player_map[idx] = player
        
        # Restore buildings
        for bdata in state["buildings"]:
            player_idx = bdata["player_index"]
            player = player_map.get(player_idx)
            if player is None:
                continue
            
            template = game.game_data["buildings"].get(bdata["name"])
            if template is None:
                continue
            
            from entities import Building
            building = Building(
                name=template.name,
                size=template.size,
                hp=bdata["hp"],
                sprite=template.sprite,
                build_duration=template.build_duration,
                radius=template.radius,
                player=player,
                costs=getattr(template, "costs", {}),
                armor_type=getattr(template, "armor_type", "fortified"),
                armor_value=getattr(template, "armor_value", 0),
                can_attack=getattr(template, "can_attack", False),
                min_damage=getattr(template, "min_damage", 0),
                max_damage=getattr(template, "max_damage", 0),
                attack_type=getattr(template, "attack_type", "slash"),
                attack_speed=getattr(template, "attack_speed", 1.0),
                attack_range=getattr(template, "attack_range", 0),
                display_name=getattr(template, "display_name", None),
                role=getattr(template, "role", ""),
                requires=list(getattr(template, "requires", [])),
                buildable=getattr(template, "buildable", True),
                strong_against=list(getattr(template, "strong_against", [])),
                weak_against=list(getattr(template, "weak_against", [])),
            )
            building.x = bdata["x"]
            building.y = bdata["y"]
            current_research = bdata.get("current_research")
            if current_research:
                tech = game.game_data.get("techs", {}).get(current_research.get("tech_id"))
                if tech:
                    building.current_research = {
                        "tech_id": tech["id"],
                        "display_name": tech.get("display_name", tech["id"]),
                        "progress": current_research.get("progress", 0),
                        "total_time": tech.get("research_time", 20),
                        "tech": tech,
                    }
            building.research_queue = [
                tech_id for tech_id in bdata.get("research_queue", [])
                if tech_id in game.game_data.get("techs", {})
            ]
            # v2: production, rally, gate state
            production_manager = getattr(game, "production_manager", None)
            units_data = production_manager.units_data if production_manager else {}
            current_production = bdata.get("current_production")
            if current_production and current_production.get("unit_type") in units_data:
                unit_data = units_data[current_production["unit_type"]]
                building.current_production = {
                    "unit_type": current_production["unit_type"],
                    "progress": current_production.get("progress", 0.0),
                    "total_time": unit_data.get("build_time", 10),
                    "unit_data": unit_data,
                }
            building.production_queue = [
                unit_type for unit_type in bdata.get("production_queue", []) if unit_type in units_data
            ]
            rally = bdata.get("rally_point")
            building.rally_point = tuple(rally) if rally else None
            building.passable = bool(bdata.get("passable", False))
            game.buildings.append(building)
        
        # Restore units
        for udata in state["units"]:
            player_idx = udata["player_index"]
            player = player_map.get(player_idx)
            if player is None:
                continue
            
            template = game.game_data["units"].get(udata["name"])
            if template is None:
                continue
            
            from entities import Unit
            from systems.animation import Animation
            unit = Unit(
                name=template.name,
                size=template.size,
                hp=udata["hp"],
                movement_speed=template.movement_speed,
                attack=template.attack,
                animations=template.animations.copy(),
                radius=template.radius,
                player=player,
                can_build=template.can_build,
                can_attack=template.can_attack_flag,
                min_damage=template.min_damage,
                max_damage=template.max_damage,
                attack_type=template.attack_type,
                armor_type=template.armor_type,
                armor_value=template.armor_value,
                attack_speed=template.attack_speed,
                attack_range=template.attack_range,
                display_name=getattr(template, "display_name", None),
                role=getattr(template, "role", ""),
                requires=list(getattr(template, "requires", [])),
                buildable=getattr(template, "buildable", True),
                strong_against=list(getattr(template, "strong_against", [])),
                weak_against=list(getattr(template, "weak_against", [])),
                building_only_attack=getattr(template, "building_only_attack", False),
            )
            unit.x = udata["x"]
            unit.y = udata["y"]
            unit.stance = udata.get("stance", "aggressive")
            home = udata.get("stance_home_position")
            unit.stance_home_position = tuple(home) if home else None
            unit.resource_type = udata.get("resource_type")
            unit.resource_amount = udata.get("resource_amount", 0)
            
            # Re-link animations
            player_idx = game.players.index(player)
            animations = {}
            for anim_name, anim_path in template.animations.items():
                sheet = game.sprite_manager.get_unit_animation_sheet(template.name, anim_name, player_idx)
                animations[anim_name] = Animation(sheet, 192, 192, 100)
            unit.set_animations(animations)

            # §8.9: garrisoned units go back INSIDE their building, not the map
            host_index = udata.get("garrisoned_building")
            if host_index is not None and 0 <= host_index < len(game.buildings):
                from systems.garrison import garrison_list

                host = game.buildings[host_index]
                unit.garrisoned_in = host
                garrison_list(host).append(unit)
            else:
                game.units.append(unit)
        
        # Restore resources
        for rdata in state["resources"]:
            template = game.game_data["resources"].get(rdata["name"])
            if template is None:
                continue
            
            from entities import Resource
            resource = Resource(
                name=template.name,
                sprite=template.sprite,
                radius=template.radius,
            )
            resource.x = rdata["x"]
            resource.y = rdata["y"]
            resource.amount_remaining = rdata.get("amount_remaining", 1000)
            game.resources.append(resource)
        
        # Restore construction sites
        for cdata in state["construction_sites"]:
            player_idx = cdata["player_index"]
            player = player_map.get(player_idx)
            if player is None:
                continue
            
            template = game.game_data["buildings"].get(cdata["building_name"])
            if template is None:
                continue
            
            from entities import ConstructionSite
            building_data = {
                "name": cdata["building_name"],
                "size": template.size,
                "hp": template.hp,
                "sprite": template.sprite,
                "build_duration": template.build_duration,
                "costs": getattr(template, "costs", {}),
                "armor_type": getattr(template, "armor_type", "fortified"),
                "armor_value": getattr(template, "armor_value", 0),
                "can_attack": getattr(template, "can_attack", False),
                "min_damage": getattr(template, "min_damage", 0),
                "max_damage": getattr(template, "max_damage", 0),
                "attack_type": getattr(template, "attack_type", "slash"),
                "attack_speed": getattr(template, "attack_speed", 1.0),
                "attack_range": getattr(template, "attack_range", 0),
                "display_name": getattr(template, "display_name", None),
                "role": getattr(template, "role", ""),
                "requires": list(getattr(template, "requires", [])),
                "buildable": getattr(template, "buildable", True),
                "strong_against": list(getattr(template, "strong_against", [])),
                "weak_against": list(getattr(template, "weak_against", [])),
            }
            site = ConstructionSite(
                building_name=cdata["building_name"],
                building_data=building_data,
                x=cdata["x"],
                y=cdata["y"],
                radius=template.radius,
                player=player,
            )
            site.hp = cdata["hp"]
            site.construction_progress = cdata.get("construction_progress", 0)
            site.construction_duration = cdata.get("construction_duration", template.build_duration)
            game.construction_sites.append(site)
        
        # Restore camera
        camera_data = state.get("camera", {})
        game.camera.x = camera_data.get("x", game.camera.x)
        game.camera.y = camera_data.get("y", game.camera.y)
        game.camera.zoom = camera_data.get("zoom", game.camera.zoom)
        game.game_speed = state.get("game_speed", 1.0)

        # v2 (§9 save/load completeness): clock, victory mode, stats,
        # tree regrowth, fog exploration
        game.sim_time_elapsed = state.get("sim_time_elapsed", 0.0)
        game.victory_condition = state.get("victory_condition", "annihilation")
        game.mutators = set(state.get("mutators", []))
        game.fog_of_war_enabled = state.get("fog_enabled", True)
        game._tree_regrowth = [tuple(entry) for entry in state.get("tree_regrowth", [])]

        # §8.9 healing fountains (older saves simply have none)
        from entities.fountain import Fountain

        for fountain in getattr(game, "fountains", ()):
            fountain.in_world = False
            game.pathfinder.notify_blocker_removed(fountain)
        game.fountains = []
        for fx, fy in state.get("fountains", []):
            fountain = Fountain(fx, fy)
            game.fountains.append(fountain)
            game.pathfinder.notify_blocker_added(fountain)

        def _unflatten(flat):
            out = {}
            for key, value in flat.items():
                name, _, kind = key.partition("|")
                out[(name, kind)] = value
            return out

        game.stats_units_trained = _unflatten(state.get("stats_units_trained", {}))
        game.stats_buildings_built = _unflatten(state.get("stats_buildings_built", {}))
        game.stats_tower_damage = dict(state.get("stats_tower_damage", {}))
        game.stats_resources_gathered = dict(state.get("stats_resources_gathered", {}))
        cls._restore_fog(game, state.get("fog_explored", {}))

        # Rebuild pathfinding spatial grid (open gates stay passable — the
        # rebuild respects the restored `passable` flags)
        game.pathfinder.mark_dirty()

        return True, "Game loaded successfully"
    
    @classmethod
    def list_saves(cls):
        """List available save files"""
        cls.ensure_save_dir()
        saves = []
        for filename in os.listdir(cls.SAVE_DIR):
            if filename.startswith("save_") and filename.endswith(".json"):
                slot = filename.replace("save_", "").replace(".json", "")
                filepath = os.path.join(cls.SAVE_DIR, filename)
                try:
                    with open(filepath, "r") as f:
                        data = json.load(f)
                    saves.append({
                        "slot": slot,
                        "timestamp": data.get("timestamp", "Unknown"),
                    })
                except:
                    pass
        return saves

    # Number of named slots the save/load screen offers.
    SLOT_COUNT = 6

    @classmethod
    def slot_meta(cls, slot):
        """Friendly metadata for the save/load UI, or None if the slot is
        empty. Reads only the cheap header fields of the save."""
        filepath = os.path.join(cls.SAVE_DIR, f"save_{slot}.json")
        if not os.path.exists(filepath):
            return None
        try:
            with open(filepath, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            return None

        # When the save was written -> "Jul 14, 15:32"
        stamp = data.get("timestamp", "")
        when = "Unknown time"
        try:
            when = datetime.fromisoformat(stamp).strftime("%b %d, %H:%M")
        except (ValueError, TypeError):
            pass

        players = data.get("players", [])
        humans = sum(1 for p in players if p.get("human"))
        kind = "vs AI" if humans and len(players) == 2 else (
            f"{len(players)}-player" if players else "match")
        size = data.get("map_size") or [0, 0]
        secs = int(data.get("sim_time_elapsed", 0))
        clock = f"{secs // 60}:{secs % 60:02d}"
        summary = f"{kind} · {size[0]}×{size[1]} · {clock} played"
        return {"when": when, "summary": summary}
