"""Market trades (§8.9): everything routes through gold, always at a loss.

Sell a lot of wood/food for MARKET_SELL_GOLD; buy a lot for MARKET_BUY_GOLD.
The buy price is 3x the sell price, so a round trip keeps ~33% of the
original resource — a release valve, never a money machine. Direct barter
(wood->food) is two hops through gold, paying the spread twice; that emerges
without any extra UI.
"""
from core.config import (MARKET_TRADE_LOT, MARKET_SELL_GOLD, MARKET_BUY_GOLD,
                         MARKET_TRADEABLE)


def can_sell(player, resource: str) -> bool:
    return (resource in MARKET_TRADEABLE
            and player.resources.get(resource, 0) >= MARKET_TRADE_LOT)


def can_buy(player, resource: str) -> bool:
    return (resource in MARKET_TRADEABLE
            and player.resources.get("gold", 0) >= MARKET_BUY_GOLD)


def sell(player, resource: str) -> bool:
    """Trade one lot of `resource` for gold. False when unaffordable."""
    if not can_sell(player, resource):
        return False
    player.resources[resource] -= MARKET_TRADE_LOT
    player.resources["gold"] = player.resources.get("gold", 0) + MARKET_SELL_GOLD
    return True


def buy(player, resource: str) -> bool:
    """Trade gold for one lot of `resource`. False when unaffordable."""
    if not can_buy(player, resource):
        return False
    player.resources["gold"] -= MARKET_BUY_GOLD
    player.resources[resource] = player.resources.get(resource, 0) + MARKET_TRADE_LOT
    return True
