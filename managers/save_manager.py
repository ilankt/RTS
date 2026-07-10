import json
import os
from datetime import datetime


class SaveManager:
    """Handles saving and loading game state"""
    
    SAVE_DIR = "saves"
    
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
            "version": 1,
            "timestamp": datetime.now().isoformat(),
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
            })
        
        # Save units
        for unit in game.units:
            unit_data = {
                "name": unit.name,
                "x": unit.x,
                "y": unit.y,
                "hp": unit.hp,
                "player_index": game.players.index(unit.player) if unit.player in game.players else -1,
                "stance": getattr(unit, "stance", "aggressive"),
                "resource_type": getattr(unit, "resource_type", None),
                "resource_amount": getattr(unit, "resource_amount", 0),
            }
            state["units"].append(unit_data)
        
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
    def load_game(cls, game, slot=0):
        """Load game state from a JSON file into the existing game object"""
        filepath = os.path.join(cls.SAVE_DIR, f"save_{slot}.json")
        if not os.path.exists(filepath):
            return False, f"Save file not found: {filepath}"
        
        with open(filepath, "r") as f:
            state = json.load(f)
        
        # Validate version
        if state.get("version") != 1:
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
            unit.resource_type = udata.get("resource_type")
            unit.resource_amount = udata.get("resource_amount", 0)
            
            # Re-link animations
            player_idx = game.players.index(player)
            animations = {}
            for anim_name, anim_path in template.animations.items():
                sheet = game.sprite_manager.get_unit_animation_sheet(template.name, anim_name, player_idx)
                animations[anim_name] = Animation(sheet, 192, 192, 100)
            unit.set_animations(animations)
            
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
        
        # Rebuild pathfinding spatial grid
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
