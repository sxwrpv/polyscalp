# bot/strategy.py
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EntryRules:
    price_min: float = 0.81
    price_max: float = 0.85
    max_spread: float = 0.01          # 1c
    tte_max_seconds: int = 7 * 60
    entry_ttl_seconds: int = 20       # cancel entry if not filled within this time
    tick: float = 0.01


def in_band(x: float, lo: float, hi: float) -> bool:
    return lo <= x <= hi


def spread_ok(bid: float, ask: float, max_spread: float) -> bool:
    if bid is None or ask is None:
        return False
    if ask < bid:
        return False
    return (ask - bid) <= max_spread


def pick_entry_side_price_only(
    *,
    tte_seconds: int,
    yes_bid: float,
    yes_ask: float,
    no_bid: float,
    no_ask: float,
    rules: EntryRules,
) -> tuple[str, float] | None:
    """
    Returns:
      ("YES", limit_price_to_post) or ("NO", limit_price_to_post) or None

    Maker-only entry => we post at best bid (post-only).
    """
    if tte_seconds > rules.tte_max_seconds:
        return None

    # Only enter if spread <= 1c
    yes_ok = spread_ok(yes_bid, yes_ask, rules.max_spread) and in_band(yes_bid, rules.price_min, rules.price_max)
    no_ok  = spread_ok(no_bid,  no_ask,  rules.max_spread) and in_band(no_bid,  rules.price_min, rules.price_max)

    # If both happen (rare), choose the one closer to the middle of the band
    if yes_ok and no_ok:
        mid = (rules.price_min + rules.price_max) / 2.0
        if abs(yes_bid - mid) <= abs(no_bid - mid):
            return ("YES", yes_bid)
        return ("NO", no_bid)

    if yes_ok:
        return ("YES", yes_bid)
    if no_ok:
        return ("NO", no_bid)

    return None