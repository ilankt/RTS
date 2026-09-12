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
from systems.ai.operations import OperationLedger, escort_delivery


class MilitaryBrain:
    """Every tick: defend base, micro units, send one squad to attack."""

    RETREAT_HP_PERCENT = 0.30  # Retreat when below 30% HP
    ARCHER_KITE_DISTANCE = 80  # Minimum distance archers try to maintain from melee
    SQUAD_SIZE = 10            # Units per squad; one squad is commanded per tick

    # §7 P3 army roles: the front line soaks, the back line shoots over it,
    # siege gets escorted, flankers hunt what they counter.
    ROLE_FRONT = ("warrior", "spearman", "axeman")
    ROLE_BACK = ("archer", "horse_archer")
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

    # §8.14 (user-reported): rams NEVER march alone. With zero live fighters
    # a working ram falls back home and waits — unless fielding a fighter has
    # become impossible (none queued, and no live/under-construction trainer
    # or nothing affordable), which sanctions the desperate all-in.
    ESCORT_CAPABLE = ("warrior", "spearman", "archer", "cavalry", "horse_archer", "axeman")
    FIGHTER_TRAINERS = ("barracks", "stable")
    RAM_HOME_RADIUS = 300  # a waiting ram parks within this range of the castle

    # §8.14 group musters (user-reported: units trickled at the enemy one by
    # one as they finished training and died piecemeal). Attack ticks now
    # gather idle fighters at a forward rally first; the wave launches when
    # enough are formed up, when the group has waited long enough (send
    # whoever showed up), or when the rally point itself comes under threat.
    MUSTER_RADIUS = 170
    MUSTER_WAVE_SIZE = 5
    MUSTER_TIMEOUT_S = 25.0

    # §8.16 endgame close-out (2026-07-19 balance report change 6): the v2
    # battery showed dominant AIs choosing attack for THOUSANDS of ticks
    # without finishing — a 204-fighter army trickling 5-unit waves into a
    # towered base forever, or idling because the loser's last workers hid
    # in fog on a fully-explored map (elimination requires the last worker,
    # §8.12 comeback rule). When fighting strength is OVERWHELMING, waves
    # launch at full size and idle squads sweep explored ground for
    # remnants instead of waiting for targets that never appear.
    OVERWHELM_MIN_FIGHTERS = 12
    OVERWHELM_RATIO = 3.0      # my fighters vs the enemy's VISIBLE fighters
    # 3 -> 5 (§8.15 residue): on a 70x70 map the 3x3 lattice left ~1.5k px
    # between anchors — the v3 battery's seed-3044 loser survived with two
    # buildings parked exactly between them. 5x5 + skipping anchors that are
    # already visible + a visited-rotation covers the map in corridors.
    SWEEP_GRID = 5

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
        self._musters = {}           # player name -> {"point", "since"} (§8.14)
        self._sweep_index = {}       # player name -> rotating sweep anchor (§8.16)
        self._objective_backoff = {}
        self.operation_counts = {}
        self.operations = OperationLedger()
        self._escort_waits = {}

    def _count_operation(self, event, amount=1):
        self.operation_counts[event] = self.operation_counts.get(event, 0) + amount

    def overwhelming(self, ctx, target=None) -> bool:
        """§8.16: does this player hold decisive fighting superiority?
        Compares own fighters against VISIBLE enemy fighters — fog hides
        the rest, but an army this large should be closing regardless.

        §8.15 residue (FFA close-out): measured PER ENEMY PLAYER, against
        the weakest — in a 4p FFA the old summed count meant a clear leader
        (57 fighters vs two 30-fighter survivors) never read as dominant
        and mop-up never started. Being able to crush at least ONE enemy
        decisively is what starts sequential eliminations; 1v1 semantics
        are unchanged (a single enemy is its own minimum)."""
        from systems.ai.utility.context import combatants_of

        mine = sum(not self._should_retreat(u, self._get_unit_max_hp(u))
                   and not getattr(u, '_local_defense_target', None)
                   for u in combatants_of(ctx.military))
        if mine < self.OVERWHELM_MIN_FIGHTERS:
            return False
        MILITARY = ("warrior", "archer", "spearman", "cavalry", "ram", "horse_archer", "axeman")
        per_enemy = {}
        for e in ctx.enemy_units:
            owner = getattr(getattr(e, "player", None), "name", None)
            if e.name in MILITARY and owner is not None:
                per_enemy[owner] = per_enemy.get(owner, 0) + 1
        owner = getattr(getattr(target, 'player', None), 'name', None)
        weakest = per_enemy.get(owner, 0) if owner else (min(per_enemy.values()) if per_enemy else 0)
        return mine >= self.OVERWHELM_RATIO * max(1, weakest)

    def is_regrouping(self, player) -> bool:
        """§8.9: is this player's army re-massing after a retreat?"""
        until = self._regroup_until.get(getattr(player, "name", ""), 0.0)
        return getattr(self.game, "sim_time_elapsed", 0.0) < until

    def update(self, ctx, should_attack: bool):
        try:
            self._update_orders(ctx, should_attack)
        finally:
            self.operations.sample(ctx, getattr(self.game, 'sim_time_elapsed', 0))

    def _update_orders(self, ctx, should_attack: bool):
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
        self._update_recovery(ctx, combatants, healers)
        self._reconcile_operations(ctx)

        # 0. Micro: retreat damaged units, kite with archers
        self._apply_micro(military, castle, max_hp_cache)
        self._manage_healers(healers, combatants, castle, max_hp_cache)
        if not enemies_near_base:
            self._release_stalled_pursuits(ctx, combatants)

        # 1. Emergency defense - all hands, defense outranks squad pacing.
        # §8.11: when the CASTLE itself is being hit, this escalates to a
        # full recall — units marching/fighting far away abort and come home
        # (losing the castle loses the game; there is nothing better to do).
        if enemies_near_base and getattr(ctx, "castle_under_attack", False):
            # §8.14: home defense dissolves any gathering muster — its units
            # are being conscripted below anyway
            self._musters.pop(ctx.player.name, None)
            emergency = getattr(ctx, "castle_under_attack", False)
            attackers = getattr(ctx, 'building_attackers', ())
            debug_log.log(
                f"AI {ctx.player.name}: {len(enemies_near_base)} enemies near base! "
                f"{'CASTLE UNDER ATTACK - full recall.' if emergency else 'Defending.'}",
                "AI",
            )
            for unit in combatants:
                unit._assault_order = None
                unit._assembly_muster = None
                if unit.in_combat or unit.is_engaging:
                    intercept = (attackers and is_building_target(getattr(unit, 'current_target', None))
                                 and any(math.hypot(unit.x-e.x, unit.y-e.y) <= 600 for e in attackers))
                    if not emergency and not intercept:
                        continue  # normal defense never interrupts fights
                    # Units already fighting near home keep their targets;
                    # everyone farther gets recalled (micro-retreat template)
                    if not intercept and math.hypot(unit.x - castle.x, unit.y - castle.y) <= self.EMERGENCY_KEEP_FIGHT_RADIUS:
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
                defense_target = self._pick_engagement_target(unit, attackers or enemies_near_base)
                # §9: defense conscription overrides an in-progress flight —
                # drop the commitment and its suppression so the unit fights.
                # §7 P4: it dissolves guard duty too — home outranks the mid.
                unit._guard_post = None
                self._release_flight(unit)
                self._command_attack(unit, defense_target, ctx)
            return  # Defense takes priority over everything

        # An outpost raid owns a local detail, not the entire military tick.
        defenders = self._assign_local_defense(ctx, combatants, max_hp_cache)
        combatants = [u for u in combatants if u not in defenders]
        self._advance_assaults(ctx, combatants)
        self._maintain_operation_escorts(ctx)

        # Idle soldiers clear nearby foundations without waiting for a wave.
        sites = getattr(ctx, 'enemy_construction_sites', ())
        for unit in combatants:
            if self._is_idle_military(unit) and not self._should_retreat(unit, max_hp_cache[unit]):
                nearby = [s for s in sites if s.hp > 0 and math.hypot(s.x-unit.x, s.y-unit.y) <= 300]
                if nearby:
                    self._command_attack(unit, min(nearby, key=lambda s: math.hypot(s.x-unit.x, s.y-unit.y)), ctx)

        # 1b. §8.9 squad retreat: a fight going badly ends NOW — disengage,
        # re-mass, re-engage — instead of bleeding out piecemeal. Only when
        # home isn't under attack (the emergency block above returns first).
        if self._check_squad_retreat(ctx, combatants + healers, castle):
            return

        # 1c. §7 P3/P4 standing discipline (every tick, not just attack ticks):
        # rams keep their escorts, the back line keeps a front to stand
        # behind, the fountain detail stays on station.
        self._maintain_ram_escorts(ctx, combatants)
        self._maintain_backline(ctx, combatants)
        self._maintain_fountain_guards(ctx, combatants)
        # §8.14: an in-progress muster advances every tick (gathers
        # stragglers, launches when the wave is formed) even on ticks where
        # AttackGoal wasn't the chosen goal.
        self._advance_muster(ctx, combatants)

        # 2b. Armed scouting (§8.11 fair perception): a standing army with NO
        # known enemy buildings can't attack — AttackGoal never fires. Send
        # one squad probing the likely spawn areas so the army finds the
        # fight instead of idling at home while the lone scout wanders.
        if not ctx.enemy_buildings and not sites and len(combatants) >= 1 and not getattr(ctx, "regrouping", False):
            scout_brain = getattr(getattr(self.game, "ai_system", None), "scout_brain", None)
            if scout_brain is not None:
                anchor = scout_brain.next_unexplored_anchor(ctx.player, (castle.x, castle.y))
                # §8.16: on a fully-explored map next_unexplored_anchor is
                # None, but the last enemy WORKERS can still be hiding in
                # fog (explored != currently visible, and elimination needs
                # the last worker — §8.12). Sweep explored ground so sight
                # bubbles re-cover it; the moment anything is spotted,
                # ctx.enemy_units fills and the attack path takes over.
                if anchor is None and not ctx.enemy_units:
                    anchor = self._next_sweep_anchor(ctx)
                if anchor is not None:
                    squad = self._next_squad(ctx.player, combatants)
                    for unit in squad:
                        if self._is_idle_military(unit) and not getattr(unit, "_guard_post", None):
                            self.game.selection_manager._move_unit_to_position(
                                unit, anchor, self.game.pathfinder)
                    return

        # 2. Attack phase (§8.14): instead of firing every ready unit at the
        # enemy the moment the goal picks (units trickled in one by one and
        # died piecemeal), an attack tick opens a MUSTER — idle fighters
        # rally at the forwardmost member and launch together as a wave
        # (_advance_muster above runs the gathering and the launch).
        if should_attack and ctx.player.name not in self._musters:
            target = self._find_attack_target(ctx)
            if target:
                self._create_muster(ctx, combatants, target)

    def _check_squad_retreat(self, ctx, military, castle) -> bool:
        # Distinct fights cannot share a centroid or one retreat order.
        groups = []
        for unit in military:
            group = next((g for g in groups if math.hypot(unit.x-g[0].x, unit.y-g[0].y) <= self.BATTLE_RADIUS), None)
            if group is None:
                groups.append([unit])
            else:
                group.append(unit)
        retreated = False
        for group in groups:
            retreated = self._retreat_local_battle(ctx, group, castle) or retreated
        return retreated and not any(self._is_idle_military(u) for u in military)

    def _retreat_local_battle(self, ctx, military, castle) -> bool:
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

        state = self._musters.get(ctx.player.name)
        if state and any(u in engaged for u in state.get('members', ())):
            self._musters.pop(ctx.player.name, None)
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
        self._musters.pop(ctx.player.name, None)  # §8.14: no staging in a last stand
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

    # --- §8.14: attack musters (group waves, not trickles) ----------------

    def _next_sweep_anchor(self, ctx):
        """§8.16 remnant sweep, fog-routed (§8.15 residue): rotate through a
        SWEEP_GRID x SWEEP_GRID lattice, skipping anchors the player can
        already SEE — sweeping ground you're looking at is wasted marching.
        Falls back to plain rotation when everything is somehow visible."""
        game_map = getattr(self.game, "game_map", None)
        if game_map is None:
            return None
        from core.config import TILE_WIDTH, TILE_HEIGHT

        world_w = game_map.width * TILE_WIDTH
        world_h = game_map.height * TILE_HEIGHT
        n = self.SWEEP_GRID
        fog = getattr(self.game, "fog_of_war", None)
        fog_on = bool(fog and getattr(fog, "enabled", True))

        index = self._sweep_index.get(ctx.player.name, 0)
        for step in range(n * n):
            probe = (index + step) % (n * n)
            row, col = divmod(probe, n)
            anchor = (world_w * (2 * col + 1) / (2 * n),
                      world_h * (2 * row + 1) / (2 * n))
            reachable = getattr(getattr(self.game, 'pathfinder', None), 'exploration_reachable', None)
            castle = getattr(ctx, 'castle', None)
            origin = (castle.x, castle.y) if castle else None
            if reachable and origin and not reachable(ctx.player, origin, anchor):
                continue
            if not fog_on or not fog.is_visible(ctx.player, anchor[0], anchor[1]):
                self._sweep_index[ctx.player.name] = (probe + 1) % (n * n)
                return anchor
        # everything visible (tiny map / fog off): plain rotation
        self._sweep_index[ctx.player.name] = (index + 1) % (n * n)
        row, col = divmod(index, n)
        return (world_w * (2 * col + 1) / (2 * n),
                world_h * (2 * row + 1) / (2 * n))

    def _create_muster(self, ctx, combatants, target):
        """Open a muster: this tick's squad rallies at its forwardmost
        member (toward the target) instead of charging in singly."""
        squad = combatants if self.overwhelming(ctx, target) else self._next_squad(ctx.player, combatants)
        members = [
            u for u in squad
            if self._is_idle_military(u)
            and not getattr(u, "_guard_post", None)
            and getattr(u, "_flee_rally", None) is None
            and not self._should_retreat(u, self._get_unit_max_hp(u))
            and getattr(u, '_recovery_job', None) is None
        ]
        if not members:
            return
        anchor = min(members, key=lambda u: math.hypot(u.x - target.x, u.y - target.y))
        point = (anchor.x, anchor.y)
        now = getattr(self.game, 'sim_time_elapsed', 0.0)
        travel = max(math.hypot(u.x-point[0], u.y-point[1]) /
                     max(1, getattr(u, 'movement_speed', 50)) for u in members)
        operation = self.operations.open(ctx.player.name, target, members, now, travel)
        escorts = [u for u in members if u.name not in self.ROLE_SIEGE]
        for ram in (u for u in members if u.name in self.ROLE_SIEGE):
            assigned = sorted(escorts, key=lambda u: math.hypot(u.x-ram.x, u.y-ram.y))[:2]
            operation.escorts[ram] = assigned
            for escort in assigned:
                escorts.remove(escort)
        state = self._musters[ctx.player.name] = {
            "point": point,
            "since": getattr(self.game, "sim_time_elapsed", 0.0),
            "members": members,
            "target": target,
            "operation": operation,
            "retry_at": now,
        }
        for unit in members:
            unit._assembly_muster = state
            unit._army_operation = operation
        self._rally_to_muster(members, point)
        debug_log.log(
            f"AI {ctx.player.name}: mustering {len(members)} units at "
            f"({point[0]:.0f}, {point[1]:.0f})", "AI")

    def _advance_muster(self, ctx, combatants):
        """Launch the assigned assembly members when formed or timed out.

        A launch may replace this assembly's pending movement, but cannot
        consume unrelated orders. Failed members retain the muster.
        """
        state = self._musters.get(ctx.player.name)
        if state is None:
            return
        now = getattr(self.game, 'sim_time_elapsed', 0.0)
        if now < state.get('retry_at', 0):
            return
        point = state["point"]
        members = state.setdefault("members", list(combatants))
        eligible = [
            u for u in members if u in combatants and getattr(u, "hp", 0) > 0
            if not getattr(u, "_guard_post", None)
            and getattr(u, "_flee_rally", None) is None
            and getattr(u, "_assault_order", None) is None
            and not u.in_combat and not u.is_engaging
        ]
        if not eligible:
            self._musters.pop(ctx.player.name, None)
            for unit in members:
                if getattr(unit, '_assembly_muster', None) is state:
                    unit._assembly_muster = None
            return
        formed = [u for u in eligible
                  if math.hypot(u.x - point[0], u.y - point[1]) <= self.MUSTER_RADIUS]
        waited = (getattr(self.game, "sim_time_elapsed", 0.0) - state["since"]
                  >= self.MUSTER_TIMEOUT_S)
        threatened = ctx.threat_at(point[0], point[1]) > 0
        # §8.16: a dominant army launches at FULL strength — 5-unit waves
        # against a fortified base were suicide-by-trickle (v2 battery:
        # 3,193 attack ticks without a kill). The small-wave cadence is for
        # even fights, where reinforcing a committed push matters more.
        overwhelming = self.overwhelming(ctx, state.get('target'))
        if overwhelming:
            wave_target = len(eligible)
        else:
            wave_target = min(self.MUSTER_WAVE_SIZE, len(eligible))
        if len(formed) >= wave_target or waited or threatened:
            # §8.16: a dominant push commits everyone — stragglers converge
            # on the target instead of seeding the next 5-unit trickle.
            wave = eligible if overwhelming else (formed if formed else eligible)
            self._launch_wave(ctx, wave)
            state['retry_at'] = now + 3
            accepted = [u for u in wave if getattr(u, "_assault_order", None)]
            self._count_operation("launch_members", len(wave))
            self._count_operation("launch_accepted", len(accepted))
            if accepted:
                # Retain unlaunched members instead of silently losing orders.
                state["members"] = [u for u in eligible if u not in accepted]
                if not state["members"]:
                    self._musters.pop(ctx.player.name, None)
            else:
                self._count_operation("launch_without_acceptance")
                deadline = getattr(state.get('operation'), 'deadline', state['since'] + 2 * self.MUSTER_TIMEOUT_S)
                if now >= deadline:
                    self._count_operation("assembly_failed")
                    self._musters.pop(ctx.player.name, None)
                    operation = state.get('operation')
                    if operation:
                        self.operations.close(operation, now, 'failed', 'assembly_deadline')
                    for unit in members:
                        if self._owns_assembly_move(unit, state):
                            unit.clear_all_movement_state()
                        unit._assembly_muster = None
            return
        self._rally_to_muster(
            [u for u in eligible if self._is_idle_military(u)], point)

    def _rally_to_muster(self, units, point):
        """Walk units to ringed spots around the rally point. Capped at
        SQUAD_SIZE orders per call (path pacing — the rest get called on a
        later tick); units already there or already en route are left be."""
        ordered = 0
        for i, unit in enumerate(units):
            if getattr(unit, "_pending_path_seq", None) is not None:
                continue
            if ordered >= self.SQUAD_SIZE:
                break
            if math.hypot(unit.x - point[0], unit.y - point[1]) <= self.MUSTER_RADIUS:
                continue
            dest = getattr(unit, "destination", None)
            if dest and math.hypot(dest[0] - point[0], dest[1] - point[1]) <= self.MUSTER_RADIUS + 60:
                continue
            angle = (i % 8) * (math.pi / 4)
            offset = 30 + 18 * (i // 8)
            self.game.selection_manager._move_unit_to_position(
                unit, (point[0] + math.cos(angle) * offset,
                       point[1] + math.sin(angle) * offset),
                self.game.pathfinder)
            unit._assembly_target = (point[0] + math.cos(angle) * offset,
                                     point[1] + math.sin(angle) * offset)
            ordered += 1

    def _launch_wave(self, ctx, wave):
        """Send a mustered wave at the current best target — the pre-§8.14
        per-squad send rules intact: back line waits for a front, per-unit
        counter-targets near the anchor, telegraph on human-bound pushes,
        and (§8.14) rams only leave with fighters in the field."""
        state = self._musters.get(ctx.player.name)
        target = state.get("target") if state else None
        if target is None or getattr(target, "hp", 0) <= 0:
            target = self._find_attack_target(ctx)
        if target is None:
            return
        focus_target = self._find_focus_fire_target(ctx, wave)
        strategic_target = target
        if focus_target:
            target = focus_target
        combatants = list(state.get("members", wave)) if state else list(wave)
        operation = state.get('operation') if state else None
        fighters_alive = any(u.name not in self.ROLE_SIEGE and
                             not self._should_retreat(u, self._get_unit_max_hp(u)) for u in combatants)
        # All roles depart together; operation escorts own march spacing.
        sent = []
        for unit in wave:
            assembly = state is not None and self._owns_assembly_move(unit, state)
            if not self._is_idle_military(unit) and not assembly:
                self.operations.record(getattr(self.game, 'sim_time_elapsed', 0), operation, 'superseded', 'other_order', unit)
                continue
            if getattr(unit, "_guard_post", None):
                self.operations.record(getattr(self.game, 'sim_time_elapsed', 0), operation, 'superseded', 'guard_duty', unit)
                continue
            if self._should_retreat(unit, self._get_unit_max_hp(unit)):
                self.operations.record(getattr(self.game, 'sim_time_elapsed', 0), operation, 'temporarily_blocked', 'wounded', unit)
                continue
            if (unit.name in self.ROLE_SIEGE and not fighters_alive
                    and self._fighters_incoming(ctx)):
                self.operations.record(getattr(self.game, 'sim_time_elapsed', 0), operation, 'temporarily_blocked', 'paid_escort', unit)
                continue  # §8.14: a ram never marches alone while escorts can exist
            # §7 P3 counter-targeting: near the squad target, each unit
            # prefers what it's strong against (cavalry hunts archers,
            # spearman meets the cavalry)
            per_target = self._counter_target_for(unit, ctx, target.x, target.y) or target
            if unit.name in self.ROLE_SIEGE and is_building_target(strategic_target):
                per_target = strategic_target
            elif not is_building_target(per_target) and is_building_target(strategic_target):
                assigned = sum(u.current_target is per_target for u in combatants)
                if assigned >= max(3, min(8, math.ceil(per_target.hp / 40))):
                    per_target = strategic_target
            debug_log.log(
                f"AI {ctx.player.name}: Sending {unit.name} to attack {per_target.name} at ({per_target.x:.0f}, {per_target.y:.0f})",
                "AI",
            )
            if assembly:
                unit.clear_all_movement_state()
            if self._command_attack(unit, per_target, ctx):
                unit._assembly_muster = None
                unit._assault_order = dict(target=strategic_target,
                    progress_at=getattr(self.game, "sim_time_elapsed", 0.0),
                    distance=math.hypot(unit.x-strategic_target.x, unit.y-strategic_target.y),
                    hp=strategic_target.hp, phase="advance")
                unit._assault_order['operation'] = operation
                unit._assault_order['position'] = (unit.x, unit.y)
                unit._assault_order['deadline'] = getattr(self.game, 'sim_time_elapsed', 0) + 180 + 3 * (
                    unit._assault_order['distance'] / max(1, getattr(unit, 'movement_speed', 50)))
                if operation:
                    operation.phase = 'march'
                sent.append(unit)
                self.operations.record(getattr(self.game, 'sim_time_elapsed', 0), operation, 'accepted', 'attack', unit)
            else:
                self.operations.record(getattr(self.game, 'sim_time_elapsed', 0), operation, 'temporarily_blocked', 'navigation_rejected', unit)
        if sent:
            self._telegraph_attack(ctx, target, sent)
        return sent

    @staticmethod
    def _owns_assembly_move(unit, state):
        if (getattr(unit, "_assembly_muster", None) is not state
                or unit.in_combat or unit.is_engaging
                or getattr(unit, "_flee_rally", None) is not None):
            return False
        point = getattr(unit, "_assembly_target", None)
        pending = getattr(unit, "_pending_path_intent", None)
        if pending:
            return pending[0] == "move" and pending[1] == point
        task = getattr(unit, "last_task", None) or {}
        return point is not None and task.get("type") == "move" and task.get("target") == point

    def _assign_local_defense(self, ctx, combatants, max_hp):
        from copy import copy
        clusters = []
        for threat in ctx.enemies_near_base:
            if getattr(threat, 'hp', 0) <= 0:
                continue
            group = next((g for g in clusters if any(math.hypot(threat.x-t.x, threat.y-t.y) < 500 for t in g)), None)
            if group is None:
                clusters.append([threat])
            else:
                group.append(threat)
        if len(clusters) <= 1:
            return self._assign_defense_cluster(ctx, combatants, max_hp)
        selected = set()
        for group in clusters:
            local = copy(ctx)
            local.enemies_near_base = group
            local.building_attackers = [t for t in getattr(ctx, 'building_attackers', ()) if t in group]
            selected.update(self._assign_defense_cluster(local, [u for u in combatants if u not in selected], max_hp))
        return selected

    def _assign_defense_cluster(self, ctx, combatants, max_hp):
        threats = [t for t in ctx.enemies_near_base if getattr(t, "hp", 0) > 0]
        attackers = getattr(ctx, "building_attackers", ())
        urgent = [t for t in threats if t in attackers or getattr(t, "can_attack_flag", False)
                  or getattr(t, "name", "") in ("watchtower", "castle")]
        # Foundations/passive structures get a small demolition detail too.
        targets = urgent or threats
        if not targets:
            for unit in combatants:
                unit._local_defense_target = None
            return set()
        budget = sum(t.hp for t in urgent) * 1.5 if urgent else 0
        needed = 2 if not urgent else max(2, len(urgent))
        selected = set()
        strength = 0
        candidates = [u for u in combatants if not self._should_retreat(u, max_hp[u])
                      and getattr(u, "_flee_rally", None) is None
                      and (not u.in_combat or u.current_target in targets)]
        def distance(u):
            return min(math.hypot(u.x-t.x, u.y-t.y) for t in targets)
        # Existing defenders stay assigned; nearby free troops come next.
        candidates.sort(key=lambda u: (getattr(u, "_local_defense_target", None) not in targets,
                                       bool(getattr(u, "_assault_order", None)), distance(u)))
        for unit in candidates:
            if len(selected) >= needed and strength >= budget:
                break
            target = min(targets, key=lambda t: math.hypot(unit.x-t.x, unit.y-t.y))
            if not urgent and distance(unit) > 600:
                continue  # a harmless remote structure cannot recall the army
            if (distance(unit) > 600
                    and (unit.is_engaging or getattr(unit, "_assault_order", None)
                         or getattr(unit, "_pending_path_seq", None) is not None)
                    and getattr(unit, "_local_defense_target", None) not in targets):
                continue  # only a castle emergency recalls committed distant troops
            unit._local_defense_target = target
            unit._assault_order = None
            unit._assembly_muster = None
            if not unit.in_combat and not (unit.is_engaging and unit.current_target in targets):
                if unit.is_engaging:
                    unit.clear_all_movement_state()
                pending = getattr(unit, "_pending_path_intent", None)
                if pending and not (pending[0] == "interact" and pending[1] is target):
                    unit.clear_all_movement_state()
                self._command_attack(unit, target, ctx)
            selected.add(unit)
            strength += unit.hp
        for unit in combatants:
            if unit not in selected:
                unit._local_defense_target = None
        self._count_operation("local_defender_ticks", len(selected))
        self._count_operation("offense_available_during_local_threat", len(combatants)-len(selected))
        return selected

    def _advance_assaults(self, ctx, combatants):
        now = getattr(self.game, "sim_time_elapsed", 0.0)
        for unit in combatants:
            order = getattr(unit, "_assault_order", None)
            if not order:
                continue
            target = order["target"]
            if target.hp <= 0 or not getattr(target, "in_world", True):
                unit._assault_order = None
                self._count_operation("objective_destroyed")
                continue
            if getattr(unit, "_flee_rally", None) is not None:
                unit._assault_order = None
                continue
            distance = math.hypot(unit.x-target.x, unit.y-target.y)
            position = order.get('position', (unit.x, unit.y))
            travelled = math.hypot(unit.x-position[0], unit.y-position[1])
            # Navigation detours are progress too, within a total travel budget.
            # Remote damage cannot indefinitely renew an unmoving soldier.
            attacking = unit.in_combat and unit.current_target is target
            if distance < order["distance"]-20 or travelled > 20 or (attacking and target.hp < order['hp']):
                order.update(progress_at=now, distance=distance, hp=target.hp)
                order['position'] = (unit.x, unit.y)
            order["phase"] = "siege" if distance <= unit.attack_range + target.radius + 80 else "advance"
            self._count_operation("assault_" + order["phase"] + "_ticks")
            if now-order["progress_at"] >= 40 or now >= order.get('deadline', float('inf')):
                unit._assault_order = None
                self._objective_backoff[(ctx.player.name, id(target))] = now + 15
                if not unit.in_combat:
                    unit.clear_all_movement_state()
                self._count_operation("objective_no_progress")
                self.operations.record(now, order.get('operation'), 'failed', 'member_no_progress', unit)
                continue
            if (not unit.in_combat and not unit.is_engaging and not unit.path
                    and getattr(unit, "_pending_path_seq", None) is None
                    and not unit.destination):
                self._command_attack(unit, target, ctx)

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
            patients = [u for u in combatants if
                        (getattr(u, '_recovery_job', None) or {}).get('healer') is healer]
            if patients:
                continue  # recovery patients travel to this reserved healer
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
            if (getattr(healer, "_pending_path_seq", None) is None
                    and math.hypot(healer.x - anchor_x, healer.y - anchor_y) > self.HEALER_FOLLOW_DISTANCE):
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
            if d > self.COUNTER_TARGET_RADIUS:
                continue
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
            # §8.14: no escort exists AT ALL — the old early-return let a
            # ram whose escorts died march on alone. Unless fielding a
            # fighter has become impossible (the desperate all-in), working
            # rams abort and wait at home for the escort to exist.
            if self._fighters_incoming(ctx):
                self._recall_unescorted_rams(ctx, rams)
            return
        taken = set()
        for ram in rams:
            if getattr(ram, '_assault_order', None) or getattr(ram, '_assembly_muster', None):
                continue  # assigned escorts travel in the same operation
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
                    pending = getattr(ram, "_pending_path_intent", None)
                    dest = pending[1] if pending and pending[0] == "move" else getattr(ram, "destination", None)
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
                if getattr(f, "_pending_path_seq", None) is not None:
                    continue
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

    def _fighters_incoming(self, ctx) -> bool:
        """Wait only for paid production, and never renew its deadline forever."""
        now = getattr(self.game, 'sim_time_elapsed', 0.0)
        delivery = escort_delivery(ctx, self.game)
        if delivery is None:
            return False
        producer, eta = delivery
        waiting = self._escort_waits.get(ctx.player.name)
        if waiting is None or not getattr(waiting[0], 'in_world', True) or waiting[0].hp <= 0:
            waiting = self._escort_waits[ctx.player.name] = (producer, now + eta + 30)
        return waiting[0] is producer and now < waiting[1]

    def _update_recovery(self, ctx, combatants, healers):
        """Wounded troops recover at a real healer or eventually fight as-is.

        Recovery has a single deadline, retained through failed movement. A
        healed soldier can retreat again after taking fresh damage; a soldier
        with no usable healing cannot cycle between home and the same muster.
        """
        now = getattr(self.game, 'sim_time_elapsed', 0.0)
        for unit in combatants:
            maximum = self._get_unit_max_hp(unit)
            if unit.hp >= maximum * .6:
                unit._last_stand_ready = False
                unit._recovery_job = None
                continue
            job = getattr(unit, '_recovery_job', None)
            if ((unit.hp >= maximum * self.RETREAT_HP_PERCENT and job is None)
                    or getattr(unit, '_last_stand_ready', False)):
                continue
            if job is None:
                options = [h for h in healers if h.hp > 0 and not getattr(h, '_flee_rally', None)]
                healer = min(options, key=lambda h: math.hypot(h.x-unit.x, h.y-unit.y)) if options else None
                distance = math.hypot(healer.x-unit.x, healer.y-unit.y) if healer else 0
                job = unit._recovery_job = dict(healer=healer, deadline=now +
                    (distance / max(1, getattr(unit, 'movement_speed', 50)) + 60 if healer else 10))
                unit._assault_order = None
                unit._assembly_muster = None
                if healer:
                    self._commit_flee(unit, (healer.x + 35, healer.y + 35), getattr(self.game, 'frame_counter', 0))
            healer = job['healer']
            if now >= job['deadline'] or (healer is not None and healer.hp <= 0):
                unit._recovery_job = None
                unit._last_stand_ready = True
                self._release_flight(unit)
                if not unit.in_combat:
                    unit.clear_all_movement_state()
                self.operations.record(now, getattr(unit, '_army_operation', None), 'failed', 'recovery_unavailable', unit)

    def _maintain_operation_escorts(self, ctx):
        for operation in self.operations.active.values():
            if operation.player != ctx.player.name or operation.phase != 'march':
                continue
            for ram, escorts in operation.escorts.items():
                if ram.hp <= 0:
                    continue
                for escort in escorts:
                    order = getattr(escort, '_assault_order', None) or {}
                    if (escort.hp <= 0 or order.get('operation') is not operation
                            or escort.in_combat or getattr(escort, '_flee_rally', None)):
                        continue
                    if math.hypot(escort.x-ram.x, escort.y-ram.y) <= 220:
                        continue
                    # A leased escort rejoins its Ballista; the assault will
                    # resume after this move. Never steal an unrelated command.
                    pending = getattr(escort, '_pending_path_intent', None)
                    if pending and pending[0] == 'move':
                        continue
                    if escort.destination and not escort.is_engaging:
                        continue
                    escort.clear_all_movement_state()
                    self.game.selection_manager._move_unit_to_position(
                        escort, (ram.x + 40, ram.y + 40), self.game.pathfinder)

    def _reconcile_operations(self, ctx):
        now = getattr(self.game, 'sim_time_elapsed', 0.0)
        for operation in list(self.operations.active.values()):
            if operation.player != ctx.player.name:
                continue
            if operation.target.hp <= 0:
                self.operations.close(operation, now, 'completed', 'objective_destroyed')
            elif not any(u.hp > 0 and
                         ((getattr(u, '_assault_order', None) or {}).get('operation') is operation
                          or ((getattr(u, '_assembly_muster', None) or {}).get('operation') is operation
                              and self._musters.get(ctx.player.name) is getattr(u, '_assembly_muster', None)))
                         for u in operation.members):
                interrupted = any(getattr(u, '_local_defense_target', None) or getattr(u, '_flee_rally', None)
                                  for u in operation.members if u.hp > 0)
                self.operations.close(operation, now, 'superseded' if interrupted else 'failed', 'members_released')
        live = {id(u) for u in ctx.military}
        for operation in list(self.operations.active.values()):
            if operation.player == ctx.player.name:
                operation.members[:] = [u for u in operation.members if id(u) in live and u.hp > 0]

    def _recall_unescorted_rams(self, ctx, rams):
        """§8.14: pull escortless rams back to the castle to wait. Rams
        already swinging (in_combat) finish their work — a lone ram
        retreating across the map dies anyway."""
        castle = ctx.castle
        if castle is None:
            return
        home = (castle.x + 60, castle.y + 60)
        for ram in rams:
            if ram.in_combat:
                continue
            near_home = math.hypot(ram.x - home[0], ram.y - home[1]) <= self.RAM_HOME_RADIUS
            working = (ram.destination or ram.path or ram.is_engaging
                       or getattr(ram, "_pending_path_seq", None) is not None)
            if near_home and not working:
                continue  # parked and waiting, as ordered
            pending = getattr(ram, "_pending_path_intent", None)
            dest = pending[1] if pending and pending[0] == "move" else getattr(ram, "destination", None)
            if dest and math.hypot(dest[0] - home[0], dest[1] - home[1]) <= self.RAM_HOME_RADIUS:
                continue  # already falling back — don't spam re-orders
            ram.clear_all_movement_state()
            ram.current_target = None
            ram.is_engaging = False
            self.game.selection_manager._move_unit_to_position(
                ram, home, self.game.pathfinder)
            debug_log.log(
                f"AI {ctx.player.name}: unescorted ram recalled home", "AI")

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
            if getattr(archer, '_assault_order', None) or getattr(archer, '_assembly_muster', None):
                continue  # the operation owns movement and target selection
            if getattr(archer, "_pending_path_seq", None) is not None:
                continue
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
            and self._is_idle_military(u)
            and getattr(u, '_assembly_muster', None) is None
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
        unit._assault_order = None
        unit._assembly_muster = None
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
            if getattr(unit, '_kite_remaining', 0) > 0:
                continue

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
            if self._kite_horse_archer(unit):
                continue
            if unit.name == "archer" and (unit.is_engaging or unit.in_combat) and unit.current_target:
                target = unit.current_target
                dist = math.hypot(unit.x - target.x, unit.y - target.y)
                # If enemy is melee (short range) and getting close, kite backward
                if hasattr(target, 'attack_range') and target.attack_range <= 60 and dist < self.ARCHER_KITE_DISTANCE:
                    dx = unit.x - target.x
                    dy = unit.y - target.y
                    if dist > 0:
                        kite_x = unit.x + (dx / dist) * 40
                        kite_y = unit.y + (dy / dist) * 40
                        if self.game.pathfinder.issue_move(unit, (kite_x, kite_y)):
                            unit.current_target = None
                            unit.in_combat = unit.is_engaging = False
                            unit.status = "run"
                            unit._kite_remaining = .6

    def _kite_horse_archer(self, unit):
        """Commit a short, navigable retreat before acquiring another shot."""
        target = getattr(unit, 'current_target', None)
        if (unit.name != 'horse_archer' or target is None or target.hp <= 0
                or getattr(target, 'attack_range', 0) > 60):
            return False
        dx, dy = unit.x - target.x, unit.y - target.y
        distance = math.hypot(dx, dy)
        if not 0 < distance < 120:
            return False
        point = (unit.x + dx / distance * 70, unit.y + dy / distance * 70)
        if not self.game.pathfinder.issue_move(unit, point):
            return False
        unit.current_target = None
        unit.in_combat = unit.is_engaging = False
        unit.status = 'run'
        unit._kite_remaining = .9
        return True

    def _should_retreat(self, unit, max_hp):
        """Check if a unit should retreat due to low HP"""
        if getattr(unit, '_last_stand_ready', False):
            return False
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
            if dist > self.BATTLE_RADIUS:
                continue  # tactical focus must not replace a cross-map siege
            score = hp_pct * 200 + dist
            if score < best_score:
                best_score = score
                best = enemy
        for enemy in ctx.enemy_buildings:
            template = getattr(self.game, 'game_data', {}).get('buildings', {}).get(enemy.name)
            max_hp = getattr(template, 'hp', getattr(enemy, 'max_hp', enemy.hp))
            hp_pct = enemy.hp / max(max_hp, 1)
            dist = math.hypot(cx - enemy.x, cy - enemy.y)
            if dist > self.BATTLE_RADIUS:
                continue
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
        if (getattr(unit, '_recovery_job', None) is not None
                or getattr(unit, '_flee_rally', None) is not None):
            return False
        if getattr(unit, "_assault_order", None) is not None:
            return False
        if getattr(unit, "_pending_path_seq", None) is not None:
            return False
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
    ECONOMY_RAID_TARGETS = ("lumbermill", "mine", "farm")
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

        now = getattr(self.game, "sim_time_elapsed", 0.0)
        self._objective_backoff = {k: until for k, until in self._objective_backoff.items() if until > now}
        def available(obj):
            key = (ctx.player.name, id(obj))
            if key in self._objective_backoff or getattr(obj, 'hp', 0) <= 0:
                return False
            failure = self.operations.failures.get(key)
            if failure and failure[0] >= 2:
                strength = sum(u.hp for u in combatants_of(ctx.military)
                               if not self._should_retreat(u, self._get_unit_max_hp(u)))
                if strength <= failure[2] * 1.25 and obj.hp >= failure[3]:
                    return False
                self.operations.failures.pop(key)
            return True
        buildings = [b for b in ctx.enemy_buildings if available(b)]
        # Reinforcements finish the current opponent before opening another war.
        campaign = next((getattr(o.target, 'player', None) for o in self.operations.active.values()
                         if o.player == ctx.player.name and o.target.hp > 0), None)
        same_opponent = [b for b in buildings if getattr(b, 'player', None) is campaign]
        if campaign is not None and same_opponent:
            buildings = same_opponent

        castles = [b for b in buildings if b.name == "castle"]

        # §9: raid sizing counts FIGHTERS — healers don't make an army raid-proof
        if castles and len(combatants_of(ctx.military)) <= raid_army_limit(getattr(ctx.player, "ai_personality", "balanced")):
            econ = [b for b in buildings if b.name in self.ECONOMY_RAID_TARGETS]
            if econ:
                best_econ = min(econ, key=score)
                castle_threat = min(ctx.threat_at(c.x, c.y) for c in castles)
                if ctx.threat_at(best_econ.x, best_econ.y) < castle_threat * self.RAID_SOFTNESS:
                    return best_econ

        # Prefer the least-defended enemy castle
        if castles:
            return min(castles, key=score)

        # Then the least-defended / nearest enemy building
        if buildings:
            return min(buildings, key=score)

        # §8.17.2: then enemy foundations — a base reduced to construction
        # sites (or a foundation-spam wall) is still standing enemy presence
        sites = [s for s in getattr(ctx, "enemy_construction_sites", ()) if s.hp > 0 and available(s)]
        if sites:
            return min(sites, key=score)

        # Then nearest enemy unit
        enemies = [u for u in ctx.enemy_units if available(u)]
        if enemies:
            return min(enemies, key=score)
        return None

    def _command_attack(self, unit, target, ctx):
        """Send a military unit to attack a target."""
        pending = getattr(unit, "_pending_path_intent", None)
        if pending and not getattr(ctx, "castle_under_attack", False):
            # Keep an already queued attack while its target is alive.
            # Defense can still redirect a move; castle emergencies can
            # redirect any intent. Equivalent emergencies coalesce below.
            if pending[0] == "interact" and pending[2] == "attack" and getattr(pending[1], "hp", 0) > 0:
                return pending[1] is target
        if getattr(unit, '_kite_remaining', 0) > 0:
            return
        if getattr(unit, "building_only_attack", False) and not is_building_target(target):
            target = self._find_attack_target(ctx)
            if not target:
                return
        self.game.selection_manager._attack_target(unit, target, self.game.pathfinder)
        pending = getattr(unit, "_pending_path_intent", None)
        return (getattr(unit, "current_target", None) is target
                or bool(pending and pending[0] == "interact" and pending[1] is target))

    def _release_stalled_pursuits(self, ctx, combatants):
        """Abandon fruitless unit chases, leaving strategic target choice to
        the next muster. Track progress in game seconds; do not interrupt
        shots, successful approaches, flights, or emergency base defense.
        Navigation's own watchdog still owns physical obstacle recovery.
        """
        now = getattr(self.game, 'sim_time_elapsed', 0.0)
        released = 0
        for unit in combatants:
            target = unit.current_target
            if (unit.in_combat or not unit.is_engaging or target is None
                    or is_building_target(target) or getattr(unit, '_kite_remaining', 0) > 0):
                unit._pursuit_progress = None
                continue
            distance = math.hypot(target.x-unit.x, target.y-unit.y)
            old = getattr(unit, '_pursuit_progress', None)
            if old is None or old[0] is not target or distance < old[2]-20 or target.hp < old[3]:
                unit._pursuit_progress = (target, now, distance, target.hp)
            elif now-old[1] >= 20 and released < 3:
                unit.clear_all_movement_state()
                unit._pursuit_progress = None
                released += 1
                self.game.stats_stalled_pursuits = getattr(self.game, 'stats_stalled_pursuits', 0)+1
