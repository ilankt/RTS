"""Data-driven building research for the strategy vertical slice."""
from __future__ import annotations

from systems.upgrade_effects import has_required_buildings, is_tech_completed
from utils.debug_logger import debug_log


class ResearchManager:
    """Manages one-time upgrades researched at buildings."""

    def __init__(self, game):
        self.game = game

    def start_research(self, building, tech_id: str):
        """Start or queue a technology at a building."""
        if building is None or not getattr(building, "player", None):
            return False, "No research building"

        ok, reason = self.research_status(building.player, tech_id, building=building)
        if not ok:
            return False, reason

        if building.current_research:
            if tech_id in building.research_queue:
                return False, "Already queued"
            building.research_queue.append(tech_id)
            return True, f"Queued {tech_id}"

        return self._start_immediate_research(building, tech_id)

    def can_research(self, player, tech_id: str) -> bool:
        ok, _ = self.research_status(player, tech_id)
        return ok

    def research_status(self, player, tech_id: str, building=None, in_progress=None):
        tech = self.game.game_data.get("techs", {}).get(tech_id)
        if not tech:
            return False, "Unknown tech"
        if is_tech_completed(player, tech_id):
            return False, "Already researched"
        if in_progress is not None:
            if tech_id in in_progress:
                return False, "Already in progress"
        elif self._is_in_progress_or_queued(player, tech_id):
            return False, "Already in progress"
        if building is not None and building.name != tech.get("building"):
            return False, f"Requires {tech.get('building', 'research building')}"
        if not has_required_buildings(self.game, player, tech.get("requires", [])):
            return False, "Missing prerequisite"
        # §8.17 upgrades follow-up: tiered techs chain on the previous level
        for required_tech in tech.get("requires_tech", []):
            if not is_tech_completed(player, required_tech):
                return False, "Missing prerequisite"
        costs = tech.get("costs", {})
        for resource, amount in costs.items():
            if player.resources.get(resource, 0) < amount:
                return False, "Insufficient resources"
        return True, "Ready"

    def get_research_info(self, building):
        research = getattr(building, "current_research", None)
        if not research:
            return None
        total_time = max(0.001, research["total_time"])
        return {
            "tech_id": research["tech_id"],
            "display_name": research.get("display_name", research["tech_id"]),
            "progress": min(1.0, research["progress"] / total_time),
            "time_remaining": max(0.0, total_time - research["progress"]),
            "queue_length": len(getattr(building, "research_queue", [])),
        }

    def available_for_building(self, building):
        """Techs this building can show. §8.17 upgrades follow-up (user):
        each tiered family shows only its NEXT level — completed levels and
        not-yet-unlocked higher levels are hidden entirely, so a finished
        family's button disappears from the card. Building-gated locks
        (e.g. siege tech before the workshop) still show with their reason."""
        if not building or not getattr(building, "player", None):
            return []
        player = building.player
        techs = []
        for tech in self.game.game_data.get("techs", {}).values():
            if tech.get("building") != building.name:
                continue
            if is_tech_completed(player, tech["id"]):
                continue  # done — the button disappears
            if any(not is_tech_completed(player, req)
                   for req in tech.get("requires_tech", [])):
                continue  # a higher level; hidden until its turn
            ok, reason = self.research_status(player, tech["id"], building=building)
            techs.append((tech, ok, reason))
        return techs

    def update(self, delta_time: float):
        for building in self.game.buildings:
            if building.current_research:
                self._update_building_research(building, delta_time)

    def _start_immediate_research(self, building, tech_id: str):
        tech = self.game.game_data["techs"][tech_id]
        for resource, amount in tech.get("costs", {}).items():
            building.player.resources[resource] -= amount

        building.current_research = {
            "tech_id": tech_id,
            "display_name": tech.get("display_name", tech_id),
            "progress": 0.0,
            "total_time": tech.get("research_time", 20),
            "tech": tech,
        }
        debug_log.log(f"{building.player.name}: started research {tech_id}", "PRODUCTION")
        return True, f"Started {tech_id}"

    def _update_building_research(self, building, delta_time: float):
        research = building.current_research
        research["progress"] += delta_time
        if research["progress"] < research["total_time"]:
            return

        tech = research["tech"]
        building.player.upgrades[tech["id"]] = tech
        building.player.upgrades_version = getattr(building.player, "upgrades_version", 0) + 1
        debug_log.log(f"{building.player.name}: completed research {tech['id']}", "PRODUCTION")
        if hasattr(self.game, "sound_manager") and self.game.sound_manager:
            self.game.sound_manager.play_research_complete()
        if getattr(building.player, "human", False) and getattr(self.game, "ui_manager", None):
            name = tech.get("display_name", tech["id"])
            self.game.ui_manager.add_alert(f"Research complete: {name}", (building.x, building.y))
        self._show_power_spike(building.player, tech)
        if hasattr(self.game, "ai_system") and self.game.ai_system:
            self.game.ai_system.invalidate_memory_cache(building.player)

        building.current_research = None
        self._start_next_queued_research(building)

    POWER_SPIKE_FLOAT_CAP = 15  # don't flood huge armies with floats

    @staticmethod
    def affected_unit_names(tech):
        """Unit types a tech's effect touches (§7.2 power spikes)."""
        effect = tech.get("effects") or tech.get("effect") or {}
        names = set(effect.get("unit_stat_multipliers", {}))
        names |= set(effect.get("unit_stat_bonuses", {}))
        if effect.get("gather_rate_multipliers"):
            names.add("worker")
        return names

    def _show_power_spike(self, player, tech):
        """Float the upgrade name over affected units so tech completion is a
        visible, feelable moment (§7.2), for every player — the floats only
        render where the viewer can see anyway."""
        floating_ui = getattr(self.game, "floating_ui", None)
        if floating_ui is None:
            return
        affected = self.affected_unit_names(tech)
        if not affected:
            return
        label = "+" + tech.get("display_name", tech["id"])
        shown = 0
        for unit in self.game.units:
            if unit.player is player and unit.hp > 0 and unit.name in affected:
                floating_ui.add_buff_notification(unit, label)
                shown += 1
                if shown >= self.POWER_SPIKE_FLOAT_CAP:
                    break

    def cancel_research(self, building):
        """Cancel the in-progress tech at a building — 50% refund, mirroring
        production cancel (§8.2.1 Phase C global-queue strip). Queued techs
        start as usual."""
        research = getattr(building, "current_research", None)
        if not research:
            return False, "Nothing in progress"
        tech = research.get("tech") or self.game.game_data.get("techs", {}).get(
            research["tech_id"], {})
        for resource, amount in tech.get("costs", {}).items():
            building.player.resources[resource] += amount // 2
        building.current_research = None
        debug_log.log(
            f"{building.player.name}: cancelled research {research['tech_id']}",
            "PRODUCTION",
        )
        self._start_next_queued_research(building)
        return True, "Cancelled"

    def _start_next_queued_research(self, building):
        while building.research_queue:
            next_tech_id = building.research_queue.pop(0)
            ok, _ = self.research_status(building.player, next_tech_id, building=building)
            if ok:
                self._start_immediate_research(building, next_tech_id)
                return

    def _is_in_progress_or_queued(self, player, tech_id: str) -> bool:
        for building in self.game.buildings:
            if getattr(building, "player", None) is not player:
                continue
            current = getattr(building, "current_research", None)
            if current and current.get("tech_id") == tech_id:
                return True
            if tech_id in getattr(building, "research_queue", []):
                return True
        return False
