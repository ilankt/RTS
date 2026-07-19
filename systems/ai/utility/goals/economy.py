"""Economy goals: train workers, build resource buildings, expand pop cap."""
from systems.ai.utility.goal import Goal
from systems.ai.utility.actions import start_construction, queue_unit


class RebuildCastleGoal(Goal):
    """§8.12: losing the castle is no longer game over — with surviving
    workers and a saved-up stockpile the AI rebuilds. Outranks everything
    (there is no plan B without a town center)."""
    name = "rebuild_castle"
    category = "economy"

    def score(self, ctx):
        if ctx.castle is not None:
            return 0
        if ctx.has_construction_in_progress("castle"):
            return 0
        if not ctx.workers:
            return 0
        if not ctx.can_afford("castle"):
            return 0
        return 300

    def execute(self, ctx):
        return start_construction(ctx, "castle", ctx.game.ai_system.building_placer)


class ExpandCastleGoal(Goal):
    """§7 P5 expansion: a second castle on a rich distant cluster once the
    bank comfortably covers it (battery: 0/30 players ever expanded — no
    goal existed). The castle is a universal dropoff, so the expansion pays
    immediately; boomer's economy weight makes it the natural expander, and
    §7.3 raid targeting finally gets a real target to punish."""
    name = "expand_castle"
    category = "economy"

    CASTLE_CAP = 2
    MIN_WORKERS = 6
    BANK_MARGIN = 1.2  # bank must cover the castle cost with headroom —
    # an expansion should never bankrupt army production outright.
    # NOTE (2026-07-18 battery): AI-vs-AI gold banks rarely exceed ~100 in
    # the post-P2 aggressive meta, so this fires mostly in slow games (vs
    # passive humans, big maps, walls). Making the AI expand *proactively*
    # needs an income-reservation mechanism, not a lower threshold — see
    # MASTER_PLAN §7 watch-items before tuning this number.

    def score(self, ctx):
        if ctx.castle is None:
            return 0  # the rebuild goal owns the no-castle case
        if ctx.has_construction_in_progress("castle"):
            return 0
        if len(ctx.buildings.get("castle", [])) >= self.CASTLE_CAP:
            return 0
        if len(ctx.workers) < self.MIN_WORKERS:
            return 0
        costs = ctx.cost_data.get("castle", {})
        if not costs:
            return 0
        for resource, amount in costs.items():
            if ctx.resources.get(resource, 0) < amount * self.BANK_MARGIN:
                return 0
        if ctx.game.ai_system.building_placer.find_expansion_anchor(ctx) is None:
            return 0
        return 65

    def execute(self, ctx):
        placer = ctx.game.ai_system.building_placer
        position = placer.find_expansion_position(ctx)
        if position is None:
            return False
        return start_construction(ctx, "castle", placer, position=position)


class BuildMarketGoal(Goal):
    """§8.9 market: build one when the stockpiles are lopsided — a big
    non-gold surplus rotting (sell it) or gold banked with a resource
    missing (buy it)."""
    name = "build_market"
    category = "economy"

    def score(self, ctx):
        if ctx.has_construction_in_progress("market") or ctx.buildings.get("market"):
            return 0
        if len(ctx.workers) < 4:
            return 0
        if not ctx.can_afford("market"):
            return 0
        # Read the tradeable set rather than listing resources here — this
        # silently kept scoring on stone after it left MARKET_TRADEABLE.
        from core.config import MARKET_TRADEABLE

        res = ctx.resources
        gold = res.get("gold", 0)
        surplus = max(res.get(r, 0) for r in MARKET_TRADEABLE)
        shortage = min(res.get(r, 0) for r in MARKET_TRADEABLE)
        if surplus >= 400 or (gold >= 400 and shortage < 60):
            return 55
        return 0

    def execute(self, ctx):
        return start_construction(ctx, "market", ctx.game.ai_system.building_placer)


class MarketTradeGoal(Goal):
    """§8.9: use the market. Sell the biggest rotting surplus when gold is
    the constraint; buy a missing resource when gold is banked. Conditions
    recomputed in execute (goal instances are shared across players)."""
    name = "market_trade"
    category = "economy"

    SELL_SURPLUS = 400   # a stockpile this big is doing nothing
    SELL_GOLD_CAP = 200  # only sell while gold is actually short
    BUY_GOLD_MIN = 400   # only buy from a comfortable bank
    BUY_SHORTAGE = 60    # a stockpile this low is blocking something
    TRADE_COOLDOWN_S = 10.0  # one trade per cooldown — a permanently-valid
    # trade goal would otherwise win the tick every tick and starve
    # AttackGoal (only one goal executes per tick): armies never left home
    # and matches timed out in the first smoke run.

    def __init__(self):
        self._last_trade = {}  # player name -> sim time

    def _off_cooldown(self, ctx):
        now = getattr(ctx.game, "sim_time_elapsed", 0.0)
        return now - self._last_trade.get(ctx.player.name, -1e9) >= self.TRADE_COOLDOWN_S

    def _pick_trade(self, ctx):
        from core.config import MARKET_TRADEABLE

        res = ctx.resources
        gold = res.get("gold", 0)
        if gold >= self.BUY_GOLD_MIN:
            for resource in MARKET_TRADEABLE:
                if res.get(resource, 0) < self.BUY_SHORTAGE:
                    return ("buy", resource)
        if gold < self.SELL_GOLD_CAP:
            biggest = max(MARKET_TRADEABLE, key=lambda r: res.get(r, 0))
            if res.get(biggest, 0) >= self.SELL_SURPLUS:
                return ("sell", biggest)
        return None

    def score(self, ctx):
        if not ctx.buildings.get("market"):
            return 0
        if not self._off_cooldown(ctx):
            return 0
        return 60 if self._pick_trade(ctx) else 0

    def execute(self, ctx):
        from systems import market

        trade = self._pick_trade(ctx)
        if trade is None:
            return False
        direction, resource = trade
        action = market.buy if direction == "buy" else market.sell
        traded = action(ctx.player, resource)
        if traded:
            self._last_trade[ctx.player.name] = getattr(ctx.game, "sim_time_elapsed", 0.0)
        return traded


class TrainWorkerGoal(Goal):
    name = "train_worker"
    category = "economy"

    def score(self, ctx):
        if not ctx.castle:
            return 0
        if not ctx.has_pop_space():
            return 0
        # §7 P5: any idle castle may train (an expansion castle works too);
        # max_queue=1 keeps the old semantics of no worker queueing.
        if not ctx.find_idle_production_building("castle", max_queue=1):
            return 0
        if not ctx.can_afford("worker"):
            return 0
        # Signature build orders (§7.2): rushers cut the worker line short to
        # field an army sooner; boomers over-invest in economy.
        from systems.ai.utility.personality import worker_target

        target = worker_target(getattr(ctx.player, "ai_personality", "balanced"))
        in_play = ctx.count_units("worker")
        if in_play >= target:
            return 0
        # 30 base + 20 per missing worker → first worker scores high, last scores 50
        return 30 + (target - in_play) * 20

    def execute(self, ctx):
        castle = ctx.find_idle_production_building("castle", max_queue=1)
        return queue_unit(ctx, castle, "worker")


class BuildFarmGoal(Goal):
    name = "build_farm"
    category = "economy"

    def score(self, ctx):
        if ctx.has_construction_in_progress("farm"):
            return 0
        if not ctx.workers:
            return 0  # §7: nobody to build it — silence beats topping the
            # action lane every tick of a workerless endgame (measured 2886
            # wasted top slots in one match)
        if not ctx.can_afford("farm"):
            return 0
        farms = len(ctx.buildings.get("farm", []))
        if farms == 0:
            return 80
        # §8.12 re-tune: a food CRISIS gates all unit production (every unit
        # costs food) — at the old flat 40, low-economy-weight personalities
        # (rusher ×0.7 = 28) starved with gold banked and no way to spend it.
        if ctx.resources.get("food", 0) < 50 and farms < 5:
            return 70
        if farms < 3 and ctx.resources.get("food", 0) < 100:
            return 40
        return 0

    def execute(self, ctx):
        return start_construction(ctx, "farm", ctx.game.ai_system.building_placer)


class BuildHouseGoal(Goal):
    name = "build_house"
    category = "economy"

    def score(self, ctx):
        if ctx.has_construction_in_progress("house"):
            return 0
        if not ctx.workers:
            return 0  # §7: see BuildFarmGoal — no builder, no goal
        if not ctx.can_afford("house"):
            return 0
        slack = ctx.pop_max - ctx.pop_current
        if slack <= 1:
            return 90  # urgent — about to hit cap
        if slack <= 3:
            return 50
        return 0

    def execute(self, ctx):
        return start_construction(ctx, "house", ctx.game.ai_system.building_placer)


class BuildLumbermillGoal(Goal):
    name = "build_lumbermill"
    category = "economy"

    def score(self, ctx):
        if ctx.has_construction_in_progress("lumbermill"):
            return 0
        if not ctx.can_afford("lumbermill"):
            return 0
        if len(ctx.workers) < 2:
            return 0
        return ctx.score_dropoff_need("lumbermill")

    def execute(self, ctx):
        return start_construction(ctx, "lumbermill", ctx.game.ai_system.building_placer)


class BuildMineGoal(Goal):
    name = "build_mine"
    category = "economy"

    def score(self, ctx):
        if ctx.has_construction_in_progress("mine"):
            return 0
        if not ctx.can_afford("mine"):
            return 0
        if len(ctx.workers) < 2:
            return 0
        return ctx.score_dropoff_need("mine")

    def execute(self, ctx):
        return start_construction(ctx, "mine", ctx.game.ai_system.building_placer)


# (BuildQuarryGoal removed 2026-07-19 with the stone resource. Gold is the
# only mineral now; BuildMineGoal covers every mineral drop-off.)
