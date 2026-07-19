"""§8.9 market: trade math, command-card tiles, AI trade goal."""
import os
import random
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

from core.config import MARKET_TRADE_LOT, MARKET_SELL_GOLD, MARKET_BUY_GOLD
from systems import market


def player_with(**resources):
    base = {"gold": 0, "wood": 0, "food": 0}
    base.update(resources)
    return SimpleNamespace(resources=base)


def test_sell_and_buy_math():
    p = player_with(wood=250, gold=0)
    assert market.sell(p, "wood")
    assert p.resources["wood"] == 250 - MARKET_TRADE_LOT
    assert p.resources["gold"] == MARKET_SELL_GOLD

    p = player_with(gold=200, food=0)
    assert market.buy(p, "food")
    assert p.resources["gold"] == 200 - MARKET_BUY_GOLD
    assert p.resources["food"] == MARKET_TRADE_LOT


def test_trades_reject_when_unaffordable():
    p = player_with(wood=99, gold=149)
    assert not market.sell(p, "wood")
    assert not market.buy(p, "food")
    assert not market.sell(p, "gold")  # gold itself is not tradeable
    assert p.resources == player_with(wood=99, gold=149).resources


def test_round_trip_always_loses():
    p = player_with(wood=MARKET_TRADE_LOT, gold=MARKET_BUY_GOLD - MARKET_SELL_GOLD)
    market.sell(p, "wood")          # wood -> 50g (total gold = buy price)
    assert market.buy(p, "wood")    # buy back at 150g
    assert p.resources["wood"] == MARKET_TRADE_LOT
    assert p.resources["gold"] == 0
    # net: paid 100 gold of value for a break-even loop - the spread wins


def test_ai_trade_goal_sells_surplus_and_buys_shortages():
    from systems.ai.utility.goals.economy import MarketTradeGoal

    goal = MarketTradeGoal()

    times = {"now": 100.0}

    def ctx_with(gold, wood=0, food=0, has_market=True):
        times["now"] += 60.0  # each scenario is past the trade cooldown
        player = player_with(gold=gold, wood=wood, food=food)
        player.name = "AI 1"
        return SimpleNamespace(
            buildings={"market": [object()]} if has_market else {},
            resources={"gold": gold, "wood": wood, "food": food},
            player=player,
            game=SimpleNamespace(sim_time_elapsed=times["now"]),
        )

    # rotting wood + gold-starved -> sell
    ctx = ctx_with(gold=50, wood=600, food=100)
    assert goal.score(ctx) > 0
    assert goal.execute(ctx) is True
    assert ctx.player.resources["gold"] == 50 + MARKET_SELL_GOLD

    # banked gold + food shortage -> buy
    ctx = ctx_with(gold=800, wood=200, food=10)
    assert goal.score(ctx) > 0
    assert goal.execute(ctx) is True
    assert ctx.player.resources["food"] == 10 + MARKET_TRADE_LOT

    # balanced stockpiles -> no trade
    assert goal.score(ctx_with(gold=250, wood=200, food=200)) == 0
    # no market -> nothing
    assert goal.score(ctx_with(gold=50, wood=600, has_market=False)) == 0


def test_spawn_never_inside_the_building():
    """User-reported: a crowded barracks spawned units INSIDE itself (the
    old fallback returned the building center when one ring of 8 points was
    blocked). Spawns must always land outside the building footprint."""
    import math
    random.seed(77)
    from core.game import Game
    from entities.building import Building
    from entities.unit import Unit

    game = Game(mode="human_1v1", player_count=2)
    human = game.players[0]
    template = game.game_data["buildings"]["barracks"]
    barracks = Building(
        name="barracks", size=template.size, hp=template.hp, sprite=template.sprite,
        build_duration=template.build_duration, x=800, y=800,
        radius=template.radius, player=human,
    )
    game.buildings.append(barracks)

    # Ring the barracks with units so every close-in strict slot is blocked
    blockers = []
    for i in range(24):
        angle = i * math.pi / 12
        for ring in (40, 72, 104, 136):
            u = Unit(name="warrior", size=[1, 1], hp=250, movement_speed=50,
                     attack=10, animations={},
                     x=barracks.x + math.cos(angle) * (barracks.radius + ring),
                     y=barracks.y + math.sin(angle) * (barracks.radius + ring),
                     radius=16, player=human)
            game.units.append(u)
            blockers.append(u)
    try:
        pos = game.production_manager._find_spawn_position(barracks)
        dist = math.hypot(pos[0] - barracks.x, pos[1] - barracks.y)
        assert dist >= barracks.radius, \
            f"spawn at {dist:.0f}px is inside the {barracks.radius:.0f}px building"
    finally:
        for u in blockers:
            game.units.remove(u)
        game.buildings.remove(barracks)


def test_market_card_tiles():
    random.seed(90210)
    from core.game import Game
    from entities.building import Building

    game = Game(mode="human_1v1", player_count=2)
    human = game.players[0]
    template = game.game_data["buildings"]["market"]
    stall = Building(
        name="market", size=template.size, hp=template.hp, sprite=template.sprite,
        build_duration=template.build_duration, x=600, y=600,
        radius=template.radius, player=human,
    )
    game.buildings.append(stall)
    game.selection_manager.selected_objects = [stall]
    stall.selected = True

    card = game.ui_manager.command_card
    content = card.refresh()
    assert content['context'] == 'market'
    kinds = [(s['direction'], s['resource']) for s in content['slots'] if s]
    assert ('sell', 'wood') in kinds and ('buy', 'food') in kinds
    # one sell + one buy tile per tradeable resource (wood, food)
    assert len(kinds) == 4

    # press a sell tile with enough wood
    human.resources['wood'] = 300
    human.resources['gold'] = 0
    sell_wood = next(s for s in content['slots'] if s and s['direction'] == 'sell'
                     and s['resource'] == 'wood')
    from systems import market as market_rules
    assert market_rules.sell(human, 'wood')
    assert human.resources['gold'] == MARKET_SELL_GOLD
