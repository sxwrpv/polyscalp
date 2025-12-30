# bot/scalp_mode.py
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Optional, Protocol, Dict, Any, Tuple

from .risk import ScalpRisk, DynamicSizer, bracket_prices, round_to_tick
from .strategy import EntryRules, pick_entry_side_price_only


class ExecutionIF(Protocol):
    """
    You will map these to your existing execution.py functions.
    Keep names if you can; otherwise adapt inside a thin wrapper.
    """

    async def place_post_only_limit_buy(self, asset_id: str, price: float, size: float) -> str: ...
    async def place_post_only_limit_sell(self, asset_id: str, price: float, size: float) -> str: ...
    async def place_limit_sell(self, asset_id: str, price: float, size: float) -> str: ...
    async def cancel_order(self, order_id: str) -> None: ...
    async def get_order(self, order_id: str) -> Dict[str, Any]: ...
    async def get_balance_usd(self) -> float: ...


@dataclass
class MarketSpec:
    """
    One Polymarket event/market => 2 assets: YES + NO token ids.
    Provide these from your scanner/state.
    """
    yes_asset: str
    no_asset: str
    # Unix timestamp when market resolves (end of window)
    end_ts: int


@dataclass
class OpenPosition:
    side: str                 # "YES" or "NO"
    asset_id: str
    qty: float
    entry_order_id: str
    entry_post_price: float
    entry_ts: float

    fill_price: Optional[float] = None
    tp_price: Optional[float] = None
    sl_price: Optional[float] = None
    tp_order_id: Optional[str] = None


class ScalpMode:
    """
    Price-only scalper:
      - posts maker entry at bid (post-only)
      - once filled => places TP (post-only) and monitors SL trigger
      - SL exits via limit sell at current bid (marketable limit, still a limit order)
    """
    def __init__(
        self,
        *,
        exec: ExecutionIF,
        market: MarketSpec,
        rules: EntryRules | None = None,
        risk: ScalpRisk | None = None,
        log=None,
    ):
        self.exec = exec
        self.market = market
        self.rules = rules or EntryRules()
        self.risk = risk or ScalpRisk()
        self.sizer = DynamicSizer(self.risk)
        self.log = log

        # top of book cache: asset_id -> (bid, ask)
        self.book: Dict[str, Tuple[Optional[float], Optional[float]]] = {
            market.yes_asset: (None, None),
            market.no_asset: (None, None),
        }

        self.pos: Optional[OpenPosition] = None

    def _tte_seconds(self) -> int:
        return max(0, int(self.market.end_ts - time.time()))

    def on_book_top(self, asset_id: str, bid: Optional[float], ask: Optional[float]) -> None:
        # store rounded prices
        if bid is not None:
            bid = round_to_tick(float(bid), self.risk.tick)
        if ask is not None:
            ask = round_to_tick(float(ask), self.risk.tick)
        self.book[asset_id] = (bid, ask)

    def _get_yes_no_top(self) -> tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
        yes_bid, yes_ask = self.book[self.market.yes_asset]
        no_bid,  no_ask  = self.book[self.market.no_asset]
        return yes_bid, yes_ask, no_bid, no_ask

    async def step(self) -> None:
        """
        Call this periodically (e.g., every 100–250ms) after books are updated.
        """        
        tte = self._tte_seconds()
        yes_bid, yes_ask, no_bid, no_ask = self._get_yes_no_top()

        # DEBUG every ~5 seconds
        if self.log and (int(time.time()) % 5 == 0):
            if all(v is not None for v in [yes_bid, yes_ask, no_bid, no_ask]):
                self.log.debug(f"[DBG] tte=... YES ... NO ... bet_frac=...")
            else:
                self.log.info(f"[DBG] tte={tte} waiting for book...")
        # Need books first
        if any(v is None for v in [yes_bid, yes_ask, no_bid, no_ask]):
            return

        # ---------------- ENTER ----------------
        if self.pos is None:
            choice = pick_entry_side_price_only(
                tte_seconds=tte,
                yes_bid=yes_bid, yes_ask=yes_ask,
                no_bid=no_bid,   no_ask=no_ask,
                rules=self.rules,
            )
            if choice is None:
                return

            side, limit_px = choice
            balance = await self.exec.get_balance_usd()
            stake = self.sizer.stake_usd(balance)

            # Choose asset id
            asset_id = self.market.yes_asset if side == "YES" else self.market.no_asset

            # Size in shares
            qty = stake / float(limit_px)
            qty = float(max(0.0001, qty))

            oid = await self.exec.place_post_only_limit_buy(asset_id=asset_id, price=float(limit_px), size=qty)

            self.pos = OpenPosition(
                side=side,
                asset_id=asset_id,
                qty=qty,
                entry_order_id=oid,
                entry_post_price=float(limit_px),
                entry_ts=time.time(),
            )
            if self.log:
                self.log.info(f"[SCALP] entry posted side={side} asset={asset_id} px={limit_px:.2f} qty={qty:.4f} "
                              f"stake≈${stake:.2f} bet_frac={self.sizer.current_fraction():.2f}")
            return

        # ---------------- MANAGE ----------------
        pos = self.pos

        # 1) entry TTL cancel
        if pos.fill_price is None:
            if (time.time() - pos.entry_ts) > self.rules.entry_ttl_seconds:
                await self.exec.cancel_order(pos.entry_order_id)
                if self.log:
                    self.log.info(f"[SCALP] entry canceled TTL side={pos.side} asset={pos.asset_id}")
                self.pos = None
                return

            st = await self.exec.get_order(pos.entry_order_id)
            if st.get("status") == "filled":
                fill_px = float(st.get("avg_fill_price") or st.get("price") or pos.entry_post_price)
                pos.fill_price = fill_px

                tp, sl = bracket_prices(fill_px, self.risk)
                pos.tp_price, pos.sl_price = tp, sl

                tp_oid = await self.exec.place_post_only_limit_sell(asset_id=pos.asset_id, price=tp, size=pos.qty)
                pos.tp_order_id = tp_oid

                if self.log:
                    self.log.info(f"[SCALP] filled side={pos.side} fill={fill_px:.2f} TP={tp:.2f} SL={sl:.2f} "
                                  f"tp_oid={tp_oid}")
            return

        # 2) TP filled?
        if pos.tp_order_id:
            tp_st = await self.exec.get_order(pos.tp_order_id)
            if tp_st.get("status") == "filled":
                self.sizer.on_trade_closed(won=True)
                if self.log:
                    self.log.info(f"[SCALP] TP hit side={pos.side} new_bet_frac={self.sizer.current_fraction():.2f}")
                self.pos = None
                return

        # 3) SL trigger: if bid <= SL => exit via limit sell at bid (marketable limit)
        bid, ask = self.book[pos.asset_id]
        if bid is None:
            return

        if bid <= float(pos.sl_price):
            # cancel TP to avoid double-sell
            if pos.tp_order_id:
                await self.exec.cancel_order(pos.tp_order_id)

            exit_oid = await self.exec.place_limit_sell(asset_id=pos.asset_id, price=float(bid), size=pos.qty)

            # wait a short time for fill; re-price once if needed
            filled = False
            for _ in range(10):
                st = await self.exec.get_order(exit_oid)
                if st.get("status") == "filled":
                    filled = True
                    break
                await asyncio.sleep(0.2)

            if not filled:
                # reprice once to latest bid (still limit-only)
                bid2, _ = self.book[pos.asset_id]
                if bid2 is not None:
                    exit_oid2 = await self.exec.place_limit_sell(asset_id=pos.asset_id, price=float(bid2), size=pos.qty)
                    for _ in range(10):
                        st2 = await self.exec.get_order(exit_oid2)
                        if st2.get("status") == "filled":
                            break
                        await asyncio.sleep(0.2)

            self.sizer.on_trade_closed(won=False)
            if self.log:
                self.log.info(f"[SCALP] SL hit side={pos.side} new_bet_frac={self.sizer.current_fraction():.2f}")
            self.pos = None
            return
        