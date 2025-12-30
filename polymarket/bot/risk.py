# bot/risk.py
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ScalpRisk:
    # Brackets (on fill price)
    tp_pct: float = 0.10
    sl_pct: float = 0.10

    # Dynamic bet sizing (% of balance)
    bet_frac_start: float = 0.50
    bet_frac_step: float = 0.01
    bet_frac_min: float = 0.01
    bet_frac_max: float = 0.50

    # Cap stake in USD
    stake_cap_usd: float = 1000.0

    # Price tick (Polymarket is usually 1c)
    tick: float = 0.01


def round_to_tick(x: float, tick: float = 0.01) -> float:
    # round to nearest tick, then clamp into (0,1)
    if tick <= 0:
        return float(x)
    v = round(x / tick) * tick
    # keep inside [0.01, 0.99] just to avoid weird edges
    v = max(tick, min(1.0 - tick, v))
    # normalize tiny float noise
    return float(round(v, 6))


def bracket_prices(fill_price: float, risk: ScalpRisk) -> tuple[float, float]:
    tp = fill_price * (1.0 + risk.tp_pct)
    sl = fill_price * (1.0 - risk.sl_pct)
    tp = round_to_tick(tp, risk.tick)
    sl = round_to_tick(sl, risk.tick)
    return tp, sl


class DynamicSizer:
    """
    Your rule:
      start at 50%
      win  -> bet% decreases by 1pp (0.50 -> 0.49 -> 0.48 ...)
      loss -> bet% increases by 1pp (0.48 -> 0.49 -> 0.50 ...)
    stake_usd = min(balance * bet%, 1000)
    """
    def __init__(self, risk: ScalpRisk):
        self.risk = risk
        self.bet_frac = float(risk.bet_frac_start)

    def stake_usd(self, balance_usd: float) -> float:
        stake = balance_usd * self.bet_frac
        return float(min(stake, self.risk.stake_cap_usd))

    def on_trade_closed(self, won: bool) -> None:
        if won:
            self.bet_frac = max(self.risk.bet_frac_min, self.bet_frac - self.risk.bet_frac_step)
        else:
            self.bet_frac = min(self.risk.bet_frac_max, self.bet_frac + self.risk.bet_frac_step)

    def current_fraction(self) -> float:
        return float(self.bet_frac)