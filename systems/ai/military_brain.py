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
                closest_enemy = min(enemies_near_base, key=lambda e: math.hypot(unit.x - e.x, unit.y - e.y))
                # §9: defense conscription overrides an in-progress flight —
                # drop the commitment and its suppression so the unit fights.
                self._release_flight(unit)
                self._command_attack(unit, closest_enemy, ctx)
            return  # Defense takes priority over everything

        # 1b. §8.9 squad retreat: a fight going badly ends NOW — disengage,
        # re-mass, re-engage — instead of bleeding out piecemeal. Only when
        # home isn't under attack (the emergency block above returns first).
        if self._check_squad_retreat(ctx, military, castle):
            return

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
                        if self._is_idle_military(unit):
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
                sent = []
                for unit in squad:
                    if self._is_idle_military(unit):
                        if self._should_retreat(unit, max_hp_cache.get(unit, unit.hp)):
                            continue
                        debug_log.log(
                            f"AI {ctx.player.name}: Sending {unit.name} to attack {target.name} at ({target.x:.0f}, {target.y:.0f})",
                            "AI",
                        )
                        self._command_attack(unit, target, ctx)
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

    def _commit_flee(self, unit, rally, frame, suppress_frames=None):
        """§9 flee commitment: the ONE protocol for starting or re-issuing a
        flight — disengage (clear_all_movement_state drops targets and
        engagement), mark the rally, suppress re-acquisition, order the
        move. _apply_micro maintains the commitment every tick until
        arrival, so every flee path MUST come through here."""
        if suppress_frames is None:
            suppress_frames = self.RETREAT_SUPPRESS_FRAMES
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
