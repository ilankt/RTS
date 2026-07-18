"""Military AI logic - defense, micro, and squad-based attack commands.

Reads only the per-tick GoalContext blackboard. Attack orders go out one
squad per tick (rotating), so a big army never issues all its paths in a
single tick (the C1 spike).
"""
import math
from systems.ai.utility.context import combatants_of, is_castle_under_attack
from systems.ai.utility.personality import raid_army_limit
from systems.combat_rules import is_building_target
from utils.debug_logger import debug_log


class MilitaryBrain:
    """Every tick: defend base, micro units, send one squad to attack."""

    RETREAT_HP_PERCENT = 0.30  # Retreat when below 30% HP
    ARCHER_KITE_DISTANCE = 80  # Minimum distance archers try to maintain from melee
    SQUAD_SIZE = 10            # Units per squad; one squad is commanded per tick

    # §7 P3 army roles: the front line soaks, the back line shoots over it,
    # siege gets escorted, flankers hunt what they counter.
    ROLE_FRONT = ("warrior", "spearman")
    ROLE_BACK = ("archer",)
    ROLE_SIEGE = ("ram",)

    # §7 P3 counter-targeting: how many px of extra distance a countered
    # target is worth in target selection (spearman walks past a warrior to
    # reach the cavalry), and how far around the squad target the army will
    # look for counter-targets without splitting.
    COUNTER_DISTANCE_BONUS = 260
    COUNTER_TARGET_RADIUS = 400

    # §7 P3 ram escort contract: keep this many fighters within escort range
    # of every ram that is out working (battery: 70 % of ram-samples had the
    # ram >150 px from ANY fighter — interleaved send order alone doesn't
    # survive the speed difference on the march).
    RAM_ESCORT_DISTANCE = 150
    ESCORTS_PER_RAM = 2

    # §7 P3 back-line march discipline: archers leash to the nearest front
    # fighter while approaching (like healers do) and open fire when the
    # front engages within support range. The leash point sits BEHIND the
    # fighter relative to its threat — on it, archers stood in the melee
    # line (first battery after P3: mean archer-front gap shrank to 34 px).
    BACKLINE_FOLLOW_DISTANCE = 110
    BACKLINE_STANDOFF = 90
    BACKLINE_SUPPORT_RANGE = 320
    BACKLINE_RELEASE_RANGE = 400  # front this close to the target frees the back line
    # §8.11 emergency defense: units fighting within this range of the castle
    # keep their targets during a full recall; everyone farther comes home.
    EMERGENCY_KEEP_FIGHT_RADIUS = 600
    # §8.9 squad retreat & regroup: a fight is "lost" when local enemy
    # strength exceeds ours by this factor — the army disengages, re-masses
    # at home (or a scouted fountain), and re-engages when regrouped.
    RETREAT_ODDS = 1.8
    BATTLE_RADIUS = 400        # how far around the fight centroid to weigh
    REGROUP_SECONDS = 20.0     # attack goals stay silent while re-massing
    RETREAT_SUPPRESS_FRAMES = 120  # no retaliation/re-acquire while fleeing
    # §9 flee commitment: a retreat is maintained until ARRIVAL, not for one
    # fixed window — 120 frames covers ~100 px of flight (warrior 50 px/s),
    # so units on a multi-hundred-px trip home turned to fight every ~2 s,
    # endlessly (user-reported flee/attack oscillation). While a flight is
    # live, _apply_micro refreshes the suppression every tick.
    # FLEE_REFRESH_FRAMES must outlive the LONGEST tick gap or the fleer is
    # re-acquirable between ticks: easy difficulty ticks at 1.0 s (~60
    # frames) and covert DDA stretches that 1.5x (~90) — 150 covers both
    # with margin. Within FLEE_HOME_RADIUS of the rally the unit counts as
    # arrived: the commitment drops, suppression lifts, and it defends
    # normally. A flight whose move order keeps dying (unreachable rally,
    # e.g. a fountain offset landing in water) is abandoned after
    # FLEE_MAX_REISSUES re-commits — fighting where you stand beats
    # standing suppressed forever.
    FLEE_HOME_RADIUS = 150
    FLEE_REFRESH_FRAMES = 150
    FLEE_MAX_REISSUES = 4

    def __init__(self, game):
        self.game = game
        self._next_squad_index = {}  # player -> rotating squad cursor
        self._regroup_until = {}     # player name -> sim time (§8.9 retreat)

    def is_regrouping(self, player) -> bool:
        """§8.9: is this player's army re-massing after a retreat?"""
        until = self._regroup_until.get(getattr(player, "name", ""), 0.0)
        return getattr(self.game, "sim_time_elapsed", 0.0) < until

    def update(self, ctx, should_attack: bool):
        """Run military logic for one AI player from the blackboard snapshot."""
        castle = ctx.castle
        if not castle:
            # §8.12: losing the castle used to lobotomize the military —
            # the whole brain bailed here. Now it's a last stand.
            self._last_stand(ctx)
            return

        military = ctx.military
        enemies_near_base = ctx.enemies_near_base

        # Pre-compute max HP for retreat checks
        max_hp_cache = {}
        for unit in military:
            max_hp_cache[unit] = self._get_unit_max_hp(unit)

        # §9 healers (2026-07-17): support units (can_attack false) never
        # take combat commands — an attack order just walks them into the
        # enemy. They trail the army; combat_system heals automatically.
        combatants = combatants_of(military)
        healers = [u for u in military if not getattr(u, "can_attack_flag", True)]

        # 0a. Gates (§8.10): open for the economy, slam shut under threat
        self._manage_gates(ctx)

        # 0. Micro: retreat damaged units, kite with archers
        self._apply_micro(military, castle, max_hp_cache)
        self._manage_healers(healers, combatants, castle, max_hp_cache)

        # 1. Emergency defense - all hands, defense outranks squad pacing.
        # §8.11: when the CASTLE itself is being hit, this escalates to a
        # full recall — units marching/fighting far away abort and come home
        # (losing the castle loses the game; there is nothing better to do).
        if enemies_near_base:
            emergency = getattr(ctx, "castle_under_attack", False)
            debug_log.log(
                f"AI {ctx.player.name}: {len(enemies_near_base)} enemies near base! "
                f"{'CASTLE UNDER ATTACK - full recall.' if emergency else 'Defending.'}",
                "AI",
            )
            for unit in combatants:
                if unit.in_combat or unit.is_engaging:
                    if not emergency:
                        continue  # normal defense never interrupts fights
                    # Units already fighting near home keep their targets;
                    # everyone farther gets recalled (micro-retreat template)
                    if math.hypot(unit.x - castle.x, unit.y - castle.y) <= self.EMERGENCY_KEEP_FIGHT_RADIUS:
                        continue
                    unit.clear_all_movement_state()
                    unit.current_target = None
                    unit.in_combat = False
                    unit.is_engaging = False
                # In an emergency even hurt units fight - the castle is worth
                # more than any single soldier.
                elif not emergency and self._should_retreat(unit, max_hp_cache.get(unit, unit.hp)):
                    continue
                # §7 P3 counter-targeting: prefer the threat this unit is
                # strong against (spearman meets the cavalry, not the warrior)
                defense_target = self._pick_engagement_target(unit, enemies_near_base)
                # §9: defense conscription overrides an in-progress flight —
                # drop the commitment and its suppression so the unit fights.
                # §7 P4: it dissolves guard duty too — home outranks the mid.
                unit._guard_post = None
                self._release_flight(unit)
                self._command_attack(unit, defense_target, ctx)
            return  # Defense takes priority over everything

        # 1b. §8.9 squad retreat: a fight going badly ends NOW — disengage,
        # re-mass, re-engage — instead of bleeding out piecemeal. Only when
        # home isn't under attack (the emergency block above returns first).
        if self._check_squad_retreat(ctx, military, castle):
            return

        # 1c. §7 P3/P4 standing discipline (every tick, not just attack ticks):
        # rams keep their escorts, the back line keeps a front to stand
        # behind, the fountain detail stays on station.
        self._maintain_ram_escorts(ctx, combatants)
        self._maintain_backline(ctx, combatants)
        self._maintain_fountain_guards(ctx, combatants)

        # 2b. Armed scouting (§8.11 fair perception): a standing army with NO
        # known enemy buildings can't attack — AttackGoal never fires. Send
        # one squad probing the likely spawn areas so the army finds the
        # fight instead of idling at home while the lone scout wanders.
        if not ctx.enemy_buildings and len(combatants) >= 5 and not getattr(ctx, "regrouping", False):
            scout_brain = getattr(getattr(self.game, "ai_system", None), "scout_brain", None)
            if scout_brain is not None:
                anchor = scout_brain.next_unexplored_anchor(ctx.player, (castle.x, castle.y))
                if anchor is not None:
                    squad = self._next_squad(ctx.player, combatants)
                    for unit in squad:
                        if self._is_idle_military(unit) and not getattr(unit, "_guard_post", None):
                            self.game.selection_manager._move_unit_to_position(
                                unit, anchor, self.game.pathfinder)
                    return

        # 2. Attack phase: send ONE squad of idle military per tick
        if should_attack:
            target = self._find_attack_target(ctx)
            if target:
                focus_target = self._find_focus_fire_target(ctx, combatants)
                if focus_target:
                    target = focus_target
                squad = self._next_squad(ctx.player, combatants)
                # §7 P3: the back line holds until a front fighter has closed
                # on the target (or there is no front line to wait for) —
                # _maintain_backline walks the archers with the fighters.
                fronts = [u for u in combatants if u.name in self.ROLE_FRONT]
                front_released = not fronts or any(
                    u.in_combat or u.is_engaging
                    or math.hypot(u.x - target.x, u.y - target.y) <= self.BACKLINE_RELEASE_RANGE
                    for u in fronts)
                sent = []
                for unit in squad:
                    if self._is_idle_military(unit):
                        if getattr(unit, "_guard_post", None):
                            continue  # §7 P4: the fountain detail stays home
                        if self._should_retreat(unit, max_hp_cache.get(unit, unit.hp)):
                            continue
                        if unit.name in self.ROLE_BACK and not front_released:
                            continue
                        # §7 P3 counter-targeting: near the squad target,
                        # each unit prefers what it's strong against
                        # (cavalry hunts archers/workers, spearman cavalry)
                        per_target = self._counter_target_for(unit, ctx, target.x, target.y) or target
                        debug_log.log(
                            f"AI {ctx.player.name}: Sending {unit.name} to attack {per_target.name} at ({per_target.x:.0f}, {per_target.y:.0f})",
                            "AI",
                        )
                        self._command_attack(unit, per_target, ctx)
                        sent.append(unit)
                if sent:
                    self._telegraph_attack(ctx, target, sent)

    def _check_squad_retreat(self, ctx, military, castle) -> bool:
        """§8.9: detect a losing fight and pull the army out. Returns True
        when a retreat was ordered this tick."""
        engaged = [u for u in military if u.in_combat or u.is_engaging]
        if len(engaged) < 3:
            return False
        cx = sum(u.x for u in engaged) / len(engaged)
        cy = sum(u.y for u in engaged) / len(engaged)
        radius_sq = self.BATTLE_RADIUS ** 2

        friendly = sum(u.hp for u in engaged
                       if (u.x - cx) ** 2 + (u.y - cy) ** 2 <= radius_sq)
        enemy = sum(e.hp for e in ctx.enemy_units
                    if (e.x - cx) ** 2 + (e.y - cy) ** 2 <= radius_sq)
        # Defensive buildings weigh in at half hp — they hurt but don't chase
        enemy += sum(b.hp * 0.5 for b in ctx.enemy_buildings
                     if b.name == "watchtower"
                     and (b.x - cx) ** 2 + (b.y - cy) ** 2 <= radius_sq)
        if friendly <= 0 or enemy <= friendly * self.RETREAT_ODDS:
            return False

        # Rally point: home castle, or a scouted fountain if it's nearer to
        # the army and quiet (wounded units regroup AND heal there)
        rally = (castle.x, castle.y)
        for fountain in getattr(ctx, "fountains", ()):
            if ctx.threat_at(fountain.x, fountain.y) > 0:
                continue
            if (math.hypot(fountain.x - cx, fountain.y - cy)
                    < math.hypot(rally[0] - cx, rally[1] - cy)):
                rally = (fountain.x + 90, fountain.y + 90)

        frame = getattr(self.game, "frame_counter", 0)
        for unit in engaged:
            self._commit_flee(unit, rally, frame)

        # §9 healers: support units near the collapsing fight retreat with
        # the army (they can never be "engaged", so the loop above misses them)
        for unit in military:
            if getattr(unit, "can_attack_flag", True):
                continue
            if (unit.x - cx) ** 2 + (unit.y - cy) ** 2 > radius_sq:
                continue
            self._commit_flee(unit, rally, frame)

        self._regroup_until[ctx.player.name] = (
            getattr(self.game, "sim_time_elapsed", 0.0) + self.REGROUP_SECONDS)
        debug_log.log(
            f"AI {ctx.player.name}: RETREAT — outmatched {enemy:.0f} vs {friendly:.0f}, "
            f"regrouping at ({rally[0]:.0f}, {rally[1]:.0f})", "AI")
        return True

    def _last_stand(self, ctx):
        """§8.12 castle lost: guard the rebuild site if one exists, otherwise
        take the fight to the enemy with everything left. No castle does not
        mean no teeth."""
        military = ctx.military
        if not military:
            return

        # A castle rebuild in progress is the one thing worth protecting
        rebuild_site = next(
            (s for s in ctx.construction_sites if s.building_name == "castle"), None)
        if rebuild_site is not None:
            defenders_needed = False
            for enemy in ctx.enemy_units:
                if (enemy.x - rebuild_site.x) ** 2 + (enemy.y - rebuild_site.y) ** 2 <= 500 ** 2:
                    defenders_needed = True
                    break
            for unit in military:
                if unit.in_combat or unit.is_engaging:
                    continue
                # §9: healers guard the site by standing near it, never charge
                if defenders_needed and getattr(unit, "can_attack_flag", True):
                    closest = min(
                        ctx.enemy_units,
                        key=lambda e: (unit.x - e.x) ** 2 + (unit.y - e.y) ** 2)
                    # conscription overrides any stale flight commitment
                    self._release_flight(unit)
                    self._command_attack(unit, closest, ctx)
                elif (unit.x - rebuild_site.x) ** 2 + (unit.y - rebuild_site.y) ** 2 > 400 ** 2:
                    self.game.selection_manager._move_unit_to_position(
                        unit, (rebuild_site.x + 80, rebuild_site.y + 80), self.game.pathfinder)
            return

        # No rebuild underway: nothing to protect, so fight with all of it
        target = self._find_attack_target(ctx)
        if target is None:
            return
        for unit in military:
            if not getattr(unit, "can_attack_flag", True):
                continue  # §9: healers follow the fight, they don't lead it
            if not unit.in_combat and not unit.is_engaging:
                # conscription overrides any stale flight commitment
                self._release_flight(unit)
                self._command_attack(unit, target, ctx)

    def _telegraph_attack(self, ctx, target, squad):
        """§7.2 telegraph: a push at the human gets a scoutable cue — but only
        if the human can actually SEE part of the marching squad (fair
        perception; no free intel about armies massing in unexplored fog)."""
        target_player = getattr(target, "player", None)
        if target_player is None or not getattr(target_player, "human", False):
            return
        ui = getattr(self.game, "ui_manager", None)
        fog = getattr(self.game, "fog_of_war", None)
        if ui is None:
            return
        visible = None
        if fog is not None and fog.enabled:
            visible = next(
                (u for u in squad if fog.is_visible(target_player, u.x, u.y)), None
            )
        else:
            visible = squad[0]  # no fog: the march is plainly visible
        if visible is None:
            return
        ui.add_alert(
            "Enemy attack incoming!",
            (visible.x, visible.y),
            throttle_key=f"telegraph_{ctx.player.name}",
            throttle_ms=45000,
        )

    def _manage_gates(self, ctx):
        """Keep own gates open so workers path through, closed when enemy
        strength registers near the gate (coarse threat map, §8.10). The
        toggle drives the incremental nav notifications, mirroring the
        human G-key path in core/game.py."""
        for gate in ctx.buildings.get("gate", []):
            if gate.hp <= 0:
                continue
            should_be_open = ctx.threat_at(gate.x, gate.y) <= 0
            if should_be_open == gate.passable:
                continue
            now_open = gate.toggle_gate()
            if now_open:
                self.game.pathfinder.notify_blocker_removed(gate)
            else:
                self.game.pathfinder.notify_blocker_added(gate)
            debug_log.log(
                f"AI {ctx.player.name}: gate {'opened' if now_open else 'closed'} "
                f"at ({gate.x:.0f}, {gate.y:.0f})",
                "AI",
            )

    def _next_squad(self, player, military):
        """Rotating squad view over the army (index-chunked, stable order).

        §8.12 batch 3: the army is INTERLEAVED by unit type before chunking.
        Raw production order put consecutively-trained rams into pure-ram
        squads that marched to the enemy unescorted (user-reported); round-
        robin by type gives every squad a mix of fighters and siege."""
        if not military:
            return []
        by_type = {}
        for unit in military:
            by_type.setdefault(unit.name, []).append(unit)
        buckets = list(by_type.values())
        interleaved = []
        index = 0
        while len(interleaved) < len(military):
            bucket = buckets[index % len(buckets)]
            if bucket:
                interleaved.append(bucket.pop(0))
            else:
                buckets.pop(index % len(buckets))
                continue
            index += 1
        squad_count = max(1, (len(interleaved) + self.SQUAD_SIZE - 1) // self.SQUAD_SIZE)
        cursor = self._next_squad_index.get(player, 0) % squad_count
        self._next_squad_index[player] = (cursor + 1) % squad_count
        start = cursor * self.SQUAD_SIZE
        return interleaved[start:start + self.SQUAD_SIZE]

    # §9 healers: how close a healer stays to the army's center of mass
    # (HEALER_HEAL_RANGE covers the rest — this is a follow leash, not a
    # heal trigger).
    HEALER_FOLLOW_DISTANCE = 120

    def _manage_healers(self, healers, combatants, castle, max_hp_cache):
        """§9 healers (2026-07-17): keep support units trailing the fighters.
        Healing itself is automatic (combat_system._update_healer); the brain
        only handles positioning. Anchors on the NEAREST fighter, not the
        army centroid — a split army's centroid is a militarily meaningless
        midpoint healers would cross the map alone to reach. Committed
        flights and wounded healers (the HP retreat owns those) are left
        alone."""
        for healer in healers:
            if getattr(healer, "_flee_rally", None) is not None:
                continue  # committed flight — don't interrupt
            if self._should_retreat(healer, max_hp_cache.get(healer, healer.hp)):
                continue  # wounded: never send it back toward the fight
            if not self._is_idle_military(healer):
                continue  # already moving, or mid-heal (cast pose)
            if combatants:
                nearest = min(combatants,
                              key=lambda u: (u.x - healer.x) ** 2 + (u.y - healer.y) ** 2)
                anchor_x, anchor_y = nearest.x, nearest.y
            elif castle is not None:
                anchor_x, anchor_y = castle.x + 60, castle.y + 60
            else:
                continue
            if math.hypot(healer.x - anchor_x, healer.y - anchor_y) > self.HEALER_FOLLOW_DISTANCE:
                self.game.selection_manager._move_unit_to_position(
                    healer, (anchor_x, anchor_y), self.game.pathfinder)

    # --- §7 P3: roles, counters, escorts ---------------------------------

    def _strong_tags(self, unit) -> set:
        """This unit's strong_against tags from the data templates."""
        template = self.game.game_data["units"].get(unit.name)
        return set(getattr(template, "strong_against", ()) or ())

    def _pick_engagement_target(self, unit, candidates):
        """Nearest candidate, counter-weighted: a target this unit is strong
        against is worth COUNTER_DISTANCE_BONUS px of detour."""
        tags = self._strong_tags(unit)

        def cost(enemy):
            d = math.hypot(unit.x - enemy.x, unit.y - enemy.y)
            if getattr(enemy, "name", None) in tags:
                d -= self.COUNTER_DISTANCE_BONUS
            return d

        return min(candidates, key=cost)

    def _counter_target_for(self, unit, ctx, anchor_x, anchor_y):
        """A visible enemy UNIT near the squad target that this unit counters,
        or None. Radius-bounded so counter-hunting never splits the army."""
        tags = self._strong_tags(unit) - {"building", "watchtower", "castle"}
        if not tags:
            return None
        best, best_d = None, float("inf")
        for enemy in ctx.enemy_units:
            if enemy.name not in tags or enemy.hp <= 0:
                continue
            if math.hypot(enemy.x - anchor_x, enemy.y - anchor_y) > self.COUNTER_TARGET_RADIUS:
                continue
            d = math.hypot(enemy.x - unit.x, enemy.y - unit.y)
            if d < best_d:
                best, best_d = enemy, d
        return best

    def _maintain_ram_escorts(self, ctx, combatants):
        """§7 P3 ram escort contract: every ram that is out working keeps
        ESCORTS_PER_RAM fighters within escort range. Fighters that outran
        their ram on the march get pulled back to it; fighters mid-fight or
        mid-flight are never conscripted."""
        rams = [u for u in combatants if u.name in self.ROLE_SIEGE]
        if not rams:
            return
        fighters = [u for u in combatants if u.name not in self.ROLE_SIEGE]
        if not fighters:
            return
        taken = set()
        for ram in rams:
            working = (ram.destination or ram.path or ram.in_combat or ram.is_engaging
                       or getattr(ram, "_pending_path_seq", None) is not None)
            if not working:
                continue  # a ram parked at home needs no escort detail
            # A ram never presses on beyond its escort: while not actually
            # swinging (in_combat), a ram whose nearest fighter is far drops
            # its march/attack order and closes on that fighter instead —
            # toward the front when the army is ahead, back home when the
            # army died. Attack approaches set is_engaging the moment the
            # order is issued (pathfinding issue_interact), so gate on
            # in_combat only. Ram-side only by design: yanking marching
            # fighters back would re-open the §9 order-oscillation class.
            if not ram.in_combat:
                nearest_f = min(
                    fighters, key=lambda u: (u.x - ram.x) ** 2 + (u.y - ram.y) ** 2)
                if math.hypot(nearest_f.x - ram.x, nearest_f.y - ram.y) > self.RAM_ESCORT_DISTANCE * 2:
                    dest = getattr(ram, "destination", None)
                    already_falling_back = dest and math.hypot(
                        dest[0] - nearest_f.x, dest[1] - nearest_f.y) <= self.RAM_ESCORT_DISTANCE * 2
                    if not already_falling_back:
                        ram.clear_all_movement_state()
                        ram.current_target = None
                        ram.is_engaging = False
                        self.game.selection_manager._move_unit_to_position(
                            ram, (nearest_f.x + 40, nearest_f.y + 40), self.game.pathfinder)
            covered = 0
            for f in sorted(fighters,
                            key=lambda u: (u.x - ram.x) ** 2 + (u.y - ram.y) ** 2):
                if covered >= self.ESCORTS_PER_RAM:
                    break
                if id(f) in taken:
                    continue
                if math.hypot(f.x - ram.x, f.y - ram.y) <= self.RAM_ESCORT_DISTANCE:
                    taken.add(id(f))
                    covered += 1
                    continue
                if f.in_combat or f.is_engaging:
                    continue  # never yank a fighter out of a fight to babysit
                if getattr(f, "_flee_rally", None) is not None:
                    continue  # committed flights own the unit
                if getattr(f, "_guard_post", None):
                    continue  # §7 P4: the fountain detail holds its ground
                dest = getattr(f, "destination", None)
                if dest and math.hypot(dest[0] - ram.x, dest[1] - ram.y) <= self.RAM_ESCORT_DISTANCE:
                    taken.add(id(f))
                    covered += 1
                    continue  # already on its way — don't spam re-orders
                self.game.selection_manager._move_unit_to_position(
                    f, (ram.x + 40, ram.y + 40), self.game.pathfinder)
                taken.add(id(f))
                covered += 1

    def _maintain_backline(self, ctx, combatants):
        """§7 P3 back-line discipline: archers leash to the nearest front
        fighter on the march (the healer-follow pattern) and open fire on the
        front's target once it engages within support range. With no front
        line alive, archers fight unleashed — the attack phase commands them
        directly."""
        backline = [u for u in combatants if u.name in self.ROLE_BACK]
        if not backline:
            return
        fronts = [u for u in combatants if u.name in self.ROLE_FRONT]
        if not fronts:
            return
        for archer in backline:
            if archer.in_combat or archer.is_engaging:
                continue
            if getattr(archer, "_flee_rally", None) is not None:
                continue
            if getattr(archer, "_guard_post", None):
                continue  # §7 P4: posted at the fountain, not in the line
            nearest = min(fronts,
                          key=lambda u: (u.x - archer.x) ** 2 + (u.y - archer.y) ** 2)
            dist = math.hypot(archer.x - nearest.x, archer.y - nearest.y)
            # Front engaged nearby: join from behind (support fire)
            if ((nearest.in_combat or nearest.is_engaging)
                    and nearest.current_target is not None
                    and getattr(nearest.current_target, "hp", 0) > 0
                    and dist <= self.BACKLINE_SUPPORT_RANGE):
                self._command_attack(archer, nearest.current_target, ctx)
                continue
            if not self._is_idle_military(archer):
                continue  # marching under an earlier order
            if dist > self.BACKLINE_FOLLOW_DISTANCE:
                # Leash point: BACKLINE_STANDOFF behind the fighter, away
                # from its threat (its target, else the nearest enemy).
                threat = nearest.current_target
                if threat is None or getattr(threat, "hp", 0) <= 0:
                    threat = min(
                        ctx.enemy_units,
                        key=lambda e: (e.x - nearest.x) ** 2 + (e.y - nearest.y) ** 2,
                        default=None)
                px, py = nearest.x, nearest.y
                if threat is not None:
                    away_x, away_y = nearest.x - threat.x, nearest.y - threat.y
                    away_len = math.hypot(away_x, away_y)
                    if away_len > 1:
                        px += away_x / away_len * self.BACKLINE_STANDOFF
                        py += away_y / away_len * self.BACKLINE_STANDOFF
                self.game.selection_manager._move_unit_to_position(
                    archer, (px, py), self.game.pathfinder)

    # --- §7 P4 fountain control ------------------------------------------

    FOUNTAIN_GUARD_RADIUS = 250   # a fighter this close counts as holding it
    FOUNTAIN_POST_RADIUS = 120    # guard posts ring the fountain (radius 70 blocks center)
    FOUNTAIN_ARMY_SPARE = 2       # army must exceed the detail by this many fighters

    def fountain_guard_shortfall(self, ctx):
        """(fountain, fighters still needed) for the guard detail, or
        (None, 0) when no detail should exist: nothing scouted, army too
        small to spare one, or the enemy holds the ground in real force."""
        from systems.ai.utility.personality import fountain_guard_target

        target = fountain_guard_target(getattr(ctx.player, "ai_personality", "balanced"))
        if target <= 0 or not ctx.castle:
            return (None, 0)
        fountains = getattr(ctx, "fountains", ())
        if not fountains:
            return (None, 0)
        combatants = combatants_of(ctx.military)
        if len(combatants) < target + self.FOUNTAIN_ARMY_SPARE:
            return (None, 0)
        castle = ctx.castle
        fountain = min(fountains,
                       key=lambda f: (f.x - castle.x) ** 2 + (f.y - castle.y) ** 2)
        # Contest light presence, don't feed a held position: the detail
        # only deploys while enemy strength there is below ~60 % of the army
        army_hp = sum(u.hp for u in combatants)
        if ctx.threat_at(fountain.x, fountain.y) > army_hp * 0.6:
            return (None, 0)
        present = sum(
            1 for u in combatants
            if math.hypot(u.x - fountain.x, u.y - fountain.y) <= self.FOUNTAIN_GUARD_RADIUS)
        return (fountain, max(0, target - present))

    def post_fountain_guards(self, ctx) -> bool:
        """Order idle fighters onto ring posts around the fountain. Returns
        True when at least one new guard was posted (the goal's execute)."""
        fountain, needed = self.fountain_guard_shortfall(ctx)
        if fountain is None or needed <= 0:
            return False
        candidates = [
            u for u in combatants_of(ctx.military)
            if not u.in_combat and not u.is_engaging
            and getattr(u, "_flee_rally", None) is None
            and not getattr(u, "_guard_post", None)
            and u.name not in self.ROLE_SIEGE
        ]
        candidates.sort(key=lambda u: (u.x - fountain.x) ** 2 + (u.y - fountain.y) ** 2)
        posted = 0
        for i, unit in enumerate(candidates[:needed]):
            angle = 2 * math.pi * i / max(1, needed)
            post = (fountain.x + self.FOUNTAIN_POST_RADIUS * math.cos(angle),
                    fountain.y + self.FOUNTAIN_POST_RADIUS * math.sin(angle))
            unit._guard_post = post
            self.game.selection_manager._move_unit_to_position(
                unit, post, self.game.pathfinder)
            posted += 1
        return posted > 0

    def _maintain_fountain_guards(self, ctx, combatants):
        """Keep posted guards on station; dissolve the detail when the army
        can no longer justify it (fountain_guard_shortfall says None)."""
        posted = [u for u in combatants if getattr(u, "_guard_post", None)]
        if not posted:
            return
        fountain, _ = self.fountain_guard_shortfall(ctx)
        if fountain is None:
            for unit in posted:
                unit._guard_post = None
            return
        for unit in posted:
            if unit.in_combat or unit.is_engaging:
                continue  # fighting at the post — that's the job
            if getattr(unit, "_flee_rally", None) is not None:
                unit._guard_post = None
                continue
            if not self._is_idle_military(unit):
                continue  # still walking to the post
            post = unit._guard_post
            if math.hypot(unit.x - post[0], unit.y - post[1]) > 60:
                self.game.selection_manager._move_unit_to_position(
                    unit, post, self.game.pathfinder)

    def _commit_flee(self, unit, rally, frame, suppress_frames=None):
        """§9 flee commitment: the ONE protocol for starting or re-issuing a
        flight — disengage (clear_all_movement_state drops targets and
        engagement), mark the rally, suppress re-acquisition, order the
        move. _apply_micro maintains the commitment every tick until
        arrival, so every flee path MUST come through here."""
        if suppress_frames is None:
            suppress_frames = self.RETREAT_SUPPRESS_FRAMES
        unit._guard_post = None  # §7 P4: a flight dissolves the guard duty
        unit.clear_all_movement_state()
        unit._flee_rally = rally
        unit._retreating_until = frame + suppress_frames
        unit._next_target_scan_frame = frame + suppress_frames
        self.game.selection_manager._move_unit_to_position(unit, rally, self.game.pathfinder)

    def _release_flight(self, unit):
        """§9: end a flight commitment and lift its suppression immediately
        (arrival, conscription, or an abandoned unreachable flight) — a
        leftover window would leave the unit standing acquisition-blind."""
        unit._flee_rally = None
        unit._flee_reissues = 0
        unit._retreating_until = 0
        unit._next_target_scan_frame = 0

    def _apply_micro(self, military, castle, max_hp_cache):
        """Apply micro-management: retreat (whole-flight committed), kiting"""
        frame = getattr(self.game, "frame_counter", 0)
        # §8.11: while the castle itself is being hit, hurt units fight — the
        # HP retreat stands down entirely (the emergency block in update()
        # would conscript them right back, and that retreat/attack pair every
        # tick was the §9 oscillation at its worst: 23 flee + 23 attack
        # orders measured on one unit in 12 s).
        emergency = is_castle_under_attack(castle, frame)

        for unit in military:
            max_hp = max_hp_cache.get(unit, unit.hp)

            # §9 flee commitment: maintain an in-progress flight every tick.
            rally = getattr(unit, "_flee_rally", None)
            if rally is not None:
                if emergency or math.hypot(unit.x - rally[0], unit.y - rally[1]) <= self.FLEE_HOME_RADIUS:
                    self._release_flight(unit)
                elif (unit.in_combat or unit.is_engaging
                        or (not unit.destination and not unit.path
                            and getattr(unit, "_pending_path_seq", None) is None)):
                    # The flee order died en route (dropped queue command,
                    # watchdog teleport) or a gate-bypassing path re-engaged
                    # the unit — re-commit the flight, but give up on a
                    # rally that keeps proving unreachable. A command still
                    # waiting in the cross-frame path queue
                    # (_pending_path_seq) is en route, not lost.
                    reissues = getattr(unit, "_flee_reissues", 0) + 1
                    if reissues > self.FLEE_MAX_REISSUES:
                        self._release_flight(unit)
                    else:
                        unit._flee_reissues = reissues
                        self._commit_flee(unit, rally, frame, self.FLEE_REFRESH_FRAMES)
                else:
                    unit._flee_reissues = 0
                    unit._retreating_until = frame + self.FLEE_REFRESH_FRAMES
                    unit._next_target_scan_frame = frame + self.FLEE_REFRESH_FRAMES
                continue

            # Retreat if heavily damaged — order once, then commit (above).
            # Support units (healers) qualify WITHOUT being engaged: nothing
            # ever engages them, but focus fire still kills them (§9).
            # No re-order when already home: the guard measures against the
            # RALLY point — the same predicate the arrival check uses — or
            # units bounced in the ring where "far enough from the castle"
            # and "arrived at the rally" overlapped.
            if self._should_retreat(unit, max_hp):
                rally = (castle.x + 30, castle.y + 30)
                threatened = (unit.is_engaging or unit.in_combat
                              or not getattr(unit, "can_attack_flag", True))
                if (not emergency and threatened
                        and math.hypot(unit.x - rally[0], unit.y - rally[1]) > self.FLEE_HOME_RADIUS):
                    debug_log.log(f"AI: {unit.name} retreating to castle at {unit.hp}/{max_hp} HP", "AI")
                    self._commit_flee(unit, rally, frame)
                continue

            # Archer kiting: if engaged and enemy melee is close, move away
            if unit.name == "archer" and unit.is_engaging and unit.current_target:
                target = unit.current_target
                dist = math.hypot(unit.x - target.x, unit.y - target.y)
                # If enemy is melee (short range) and getting close, kite backward
                if hasattr(target, 'attack_range') and target.attack_range <= 60 and dist < self.ARCHER_KITE_DISTANCE:
                    dx = unit.x - target.x
                    dy = unit.y - target.y
                    if dist > 0:
                        kite_x = unit.x + (dx / dist) * 40
                        kite_y = unit.y + (dy / dist) * 40
                        unit.destination = (kite_x, kite_y)
                        unit.path = None
                        unit.path_index = 0
                        unit.status = "run"

    def _should_retreat(self, unit, max_hp):
        """Check if a unit should retreat due to low HP"""
        if max_hp <= 0:
            return False
        return unit.hp / max_hp < self.RETREAT_HP_PERCENT

    def _find_focus_fire_target(self, ctx, military):
        """Find the weakest enemy near the army for focus fire (blackboard)."""
        if not military:
            return None
        # Army centroid - O(units) once instead of O(enemies x units)
        cx = sum(u.x for u in military) / len(military)
        cy = sum(u.y for u in military) / len(military)

        best = None
        best_score = float('inf')
        for enemy in ctx.enemy_units:
            max_hp = self._get_unit_max_hp(enemy)
            hp_pct = enemy.hp / max(max_hp, 1)
            dist = math.hypot(cx - enemy.x, cy - enemy.y)
            score = hp_pct * 200 + dist
            if score < best_score:
                best_score = score
                best = enemy
        for enemy in ctx.enemy_buildings:
            hp_pct = enemy.hp / max(getattr(enemy, 'hp', 1000), 1)
            dist = math.hypot(cx - enemy.x, cy - enemy.y)
            score = hp_pct * 200 + dist
            if score < best_score:
                best_score = score
                best = enemy

        return best

    def _get_unit_max_hp(self, unit):
        """Get max HP for a unit from cached game data."""
        template = self.game.game_data["units"].get(unit.name)
        if template:
            return template.hp
        return getattr(unit, 'hp', 100)

    # --- Private helpers ---

    def _is_idle_military(self, unit) -> bool:
        """Military unit with nothing to do."""
        if unit.in_combat or unit.is_engaging:
            return False
        if unit.status == "idle" or (unit.status == "run" and not unit.destination and not unit.path):
            return True
        return False

    # How strongly the influence map repels target selection: one point of
    # threat costs this many px of extra "distance".
    THREAT_DISTANCE_WEIGHT = 0.8

    # §7.3 risk/reward: forward economy buildings are raid bait. A raid-sized
    # army prefers them when they're meaningfully softer than the castle.
    ECONOMY_RAID_TARGETS = ("lumbermill", "mine", "quarry", "farm")
    RAID_SOFTNESS = 0.6  # econ target must be < this fraction of castle threat

    def _find_attack_target(self, ctx):
        """Best enemy target: castles first, then buildings, then units —
        each scored by distance + local threat from the influence map.
        Exception (§7.3): a raid-sized army hits undefended expansions
        (forward dropoffs/farms) instead of walking into castle defenses —
        expanding greedily without protection is now punishable. Fog rules
        still apply: ctx.enemy_buildings only contains what was scouted."""
        ref_x = ctx.castle.x if ctx.castle else 0
        ref_y = ctx.castle.y if ctx.castle else 0

        def score(obj):
            return math.hypot(obj.x - ref_x, obj.y - ref_y) + ctx.threat_at(obj.x, obj.y) * self.THREAT_DISTANCE_WEIGHT

        castles = [b for b in ctx.enemy_buildings if b.name == "castle"]

        # §9: raid sizing counts FIGHTERS — healers don't make an army raid-proof
        if castles and len(combatants_of(ctx.military)) <= raid_army_limit(getattr(ctx.player, "ai_personality", "balanced")):
            econ = [b for b in ctx.enemy_buildings if b.name in self.ECONOMY_RAID_TARGETS]
            if econ:
                best_econ = min(econ, key=score)
                castle_threat = min(ctx.threat_at(c.x, c.y) for c in castles)
                if ctx.threat_at(best_econ.x, best_econ.y) < castle_threat * self.RAID_SOFTNESS:
                    return best_econ

        # Prefer the least-defended enemy castle
        if castles:
            return min(castles, key=score)

        # Then the least-defended / nearest enemy building
        if ctx.enemy_buildings:
            return min(ctx.enemy_buildings, key=score)

        # Then nearest enemy unit
        if ctx.enemy_units:
            return min(ctx.enemy_units, key=score)
        return None

    def _command_attack(self, unit, target, ctx):
        """Send a military unit to attack a target."""
        if getattr(unit, "building_only_attack", False) and not is_building_target(target):
            target = self._find_attack_target(ctx)
            if not target:
                return
        self.game.selection_manager._attack_target(unit, target, self.game.pathfinder)
