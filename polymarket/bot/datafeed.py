# bot/datafeed.py
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Callable, Optional, Sequence

import websockets


@dataclass
class WSConfig:
    ws_url: str = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
    ping_interval: int = 20
    reconnect_delay_sec: float = 1.0


def _level_price(level) -> Optional[float]:
    """
    Handles common shapes:
      {"price": "0.48", "size": "..."}
      ["0.48", "123"]
      ("0.48", "123")
    """
    try:
        if isinstance(level, dict):
            return float(level.get("price"))
        if isinstance(level, (list, tuple)) and len(level) >= 1:
            return float(level[0])
    except Exception:
        return None
    return None


def _best_bid(bids) -> Optional[float]:
    best = None
    for lv in bids or []:
        p = _level_price(lv)
        if p is None:
            continue
        best = p if best is None else max(best, p)
    return best


def _best_ask(asks) -> Optional[float]:
    best = None
    for lv in asks or []:
        p = _level_price(lv)
        if p is None:
            continue
        best = p if best is None else min(best, p)
    return best


class MarketDataFeed:
    """
    Subscribes to Polymarket CLOB WS and emits top-of-book updates.

    Calls:
        on_book_top(asset_id: str, bid: Optional[float], ask: Optional[float])
    """

    def __init__(
        self,
        *,
        cfg: WSConfig,
        asset_ids: Sequence[str],
        on_book_top: Callable[[str, Optional[float], Optional[float]], None],
        log=None,
    ):
        self.cfg = cfg
        self.asset_ids = list(asset_ids)
        self.on_book_top = on_book_top
        self.log = log
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    async def run(self) -> None:
        while not self._stop:
            try:
                async with websockets.connect(
                    self.cfg.ws_url,
                    ping_interval=self.cfg.ping_interval,
                ) as ws:
                    if self.log:
                        self.log.info(f"WS connected: {self.cfg.ws_url}")

                    sub = {"type": "market", "assets_ids": self.asset_ids}
                    await ws.send(json.dumps(sub))

                    if self.log:
                        self.log.info(f"Subscribed assets={len(self.asset_ids)}")

                    while not self._stop:
                        raw = await ws.recv()
                        self._handle_raw(raw)

            except Exception as e:
                if self._stop:
                    break
                if self.log:
                    self.log.warning(f"WS disconnected: {e!r}")
                await asyncio.sleep(self.cfg.reconnect_delay_sec)

    def _handle_raw(self, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except Exception:
            return

        msgs = msg if isinstance(msg, list) else [msg]

        for m in msgs:
            if not isinstance(m, dict):
                continue

            et = m.get("event_type") or m.get("type")
            if et != "book":
                continue

            asset_id = m.get("asset_id") or m.get("assetId")
            if not asset_id:
                continue

            bids = m.get("bids") or []
            asks = m.get("asks") or []

            bid = _best_bid(bids)
            ask = _best_ask(asks)

            self.on_book_top(str(asset_id), bid, ask)