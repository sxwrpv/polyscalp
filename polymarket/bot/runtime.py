# bot/runtime.py
from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from bot.datafeed import MarketDataFeed, WSConfig
from bot.execution import PaperExecution
from bot.scalp_mode import ScalpMode, MarketSpec
from bot.strategy import EntryRules
from bot.risk import ScalpRisk
from bot.gamma import GammaClient, GammaCfg
from bot.scanner import scan_btc_15m_by_slug, GammaScanParams


def _load_yaml(path: str = "config.yaml") -> Dict[str, Any]:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}


class BotRuntime:
    """
    Runs bot loop in an asyncio Task and exposes live snapshots via wait_for_update().
    """

    def __init__(self, cfg_path: str = "config.yaml", log: Optional[logging.Logger] = None) -> None:
        self.cfg_path = cfg_path
        self.log = log or logging.getLogger("polyscalp")

        self._task: Optional[asyncio.Task] = None
        self._stop_evt = asyncio.Event()

        self._cond = asyncio.Condition()
        self._seq = 0
        self.snapshot: Dict[str, Any] = {"running": False, "status": "stopped", "ts": int(time.time())}

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop_evt.clear()
        self._task = asyncio.create_task(self._run(), name="bot-runtime")

    async def stop(self) -> None:
        self._stop_evt.set()
        if self._task:
            with contextlib.suppress(asyncio.CancelledError):
                self._task.cancel()
                await self._task
        self._task = None
        await self._publish({"running": False, "status": "stopped", "ts": int(time.time())})

    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def wait_for_update(self, last_seq: int) -> tuple[int, Dict[str, Any]]:
        async with self._cond:
            await self._cond.wait_for(lambda: self._seq != last_seq)
            return self._seq, dict(self.snapshot)

    async def _publish(self, snap: Dict[str, Any]) -> None:
        async with self._cond:
            self._seq += 1
            self.snapshot = snap
            self._cond.notify_all()

    async def _stop_feed(self, feed: MarketDataFeed, feed_task: asyncio.Task) -> None:
        feed.stop()
        feed_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await feed_task

    async def _run(self) -> None:
        try:
            cfg = _load_yaml(self.cfg_path)

            # --- hosts ---
            auth = cfg.get("auth", {}) or {}
            ws_host = auth.get("ws_host") or "wss://ws-subscriptions-clob.polymarket.com"
            ws_url = ws_host.rstrip("/") + "/ws/market"

            # --- gamma ---
            g = cfg.get("gamma", {}) or {}
            m = cfg.get("markets", {}) or {}

            cookie_env = g.get("cookie_env") or "POLY_GAMMA_COOKIE"
            gamma_cookie = os.getenv(cookie_env)

            gamma = GammaClient(
                GammaCfg(
                    base_url=str(g.get("base_url", "https://gamma-api.polymarket.com")),
                    user_agent=str(g.get("user_agent", "Mozilla/5.0")),
                    accept=str(g.get("accept", "application/json")),
                    cookie=gamma_cookie,
                )
            )        
    state_path = str(cfg.get("paper_state_path", "./logs/paper_state.json"))
    exec_ = PaperExecution(
       cfg=PaperExecCfg(start_cash_usd=start_cash),
        price_cache=price_cache,
        log=self.log,
        state_path=state_path,
        persist_orders=False,
   )

# AFTER
exec_ = PaperExecution(start_cash=start_cash, price_cache=price_cache)

            scan_params = GammaScanParams(
                slug_prefix=str(g.get("slug_prefix", "btc-updown-15m-")),
                interval_sec=int(g.get("interval_sec", 900)),
                lookahead_intervals=int(g.get("lookahead_intervals", 12)),
                fallback_search_query=str(g.get("fallback_search_query", "btc updown 15m")),
                fallback_limit=int(g.get("fallback_limit", 50)),
            )

            min_tte = int(m.get("min_time_to_expiry_sec", 120))
            max_tte = int(m.get("max_time_to_expiry_sec", 1200))
            rollover_grace_sec = int(cfg.get("rollover_grace_sec", 2))

            # --- execution (paper) ---
            start_cash = float(cfg.get("start_cash_usd", 500))

            # shared top-of-book cache for mark-to-mid
            price_cache: Dict[str, tuple[Optional[float], Optional[float]]] = {}

            state_path = str(cfg.get("paper_state_path", "./logs/paper_state.json"))
            exec_ = PaperExecution(
                cfg=PaperExecCfg(start_cash_usd=start_cash),
                price_cache=price_cache,
                log=self.log,
                state_path=state_path,
                persist_orders=False,
            )

            rules = EntryRules()
            risk = ScalpRisk()

            feed: Optional[MarketDataFeed] = None
            feed_task: Optional[asyncio.Task] = None
            scalp: Optional[ScalpMode] = None
            market: Optional[MarketSpec] = None
            current_slug: Optional[str] = None

            def on_book(asset_id: str, bid: Optional[float], ask: Optional[float]) -> None:
                price_cache[asset_id] = (bid, ask)
                if scalp is not None:
                    scalp.on_book_top(asset_id, bid, ask)

            async def start_new_market() -> None:
                nonlocal feed, feed_task, scalp, market, current_slug

                if feed is not None and feed_task is not None:
                    await self._stop_feed(feed, feed_task)
                    feed, feed_task = None, None

                found = scan_btc_15m_by_slug(
                    gamma,
                    params=scan_params,
                    min_tte_sec=min_tte,
                    max_tte_sec=max_tte,
                    debug=False,
                )

                yes_asset = str(found["yes_asset"])
                no_asset = str(found["no_asset"])
                end_ts = int(found["end_ts"])
                current_slug = str(found.get("slug", ""))

                self.log.info(f"[SCAN] slug={current_slug} tte={found.get('tte')} end_ts={end_ts}")

                market = MarketSpec(yes_asset=yes_asset, no_asset=no_asset, end_ts=end_ts)

                # keep exec state; reset only the live price cache for current assets
                price_cache.clear()
                price_cache[market.yes_asset] = (None, None)
                price_cache[market.no_asset] = (None, None)

                scalp = ScalpMode(exec=exec_, market=market, rules=rules, risk=risk, log=self.log)

                feed = MarketDataFeed(
                    cfg=WSConfig(ws_url=ws_url),
                    asset_ids=[market.yes_asset, market.no_asset],
                    on_book_top=on_book,
                    log=self.log,
                )
                feed_task = asyncio.create_task(feed.run())

            await self._publish({"running": True, "status": "starting", "ts": int(time.time())})
            await start_new_market()

            while not self._stop_evt.is_set():
                assert market and scalp and feed and feed_task

                now = int(time.time())
                tte = market.end_ts - now

                yes_bid, yes_ask = price_cache.get(market.yes_asset, (None, None))
                no_bid, no_ask = price_cache.get(market.no_asset, (None, None))

                # optional bet fraction if your ScalpMode has a sizer
                bet_frac = None
                try:
                    sizer = getattr(scalp, "sizer", None)
                    if sizer and hasattr(sizer, "current_fraction"):
                        bet_frac = float(sizer.current_fraction())
                except Exception:
                    pass

                exs = exec_.snapshot()

                await self._publish(
                    {
                        "running": True,
                        "status": "running",
                        "ts": int(time.time()),
                        "slug": current_slug,
                        "end_ts": market.end_ts,
                        "tte": tte,
                        "yes_asset": market.yes_asset,
                        "no_asset": market.no_asset,
                        "yes_bid": yes_bid,
                        "yes_ask": yes_ask,
                        "no_bid": no_bid,
                        "no_ask": no_ask,
                        "bet_frac": bet_frac,
                        "balance": exs.get("equity_usd"),
                        "pnl": exs.get("pnl"),
                        "stats": exs.get("stats"),
                        "positions": exs.get("positions"),
                        "open_orders": exs.get("open_orders"),
                    }
                )

                if now >= (market.end_ts + rollover_grace_sec):
                    self.log.info(f"[ROLLOVER] market ended slug={current_slug} -> scanning next")
                    await start_new_market()
                    await asyncio.sleep(0.25)
                    continue

                await scalp.step()
                await asyncio.sleep(0.2)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.log.exception("BotRuntime crashed")
            await self._publish(
                {
                    "running": False,
                    "status": "error",
                    "error": repr(e),
                    "ts": int(time.time()),
                }
            )
        finally:

            await self._publish({"running": False, "status": "stopped", "ts": int(time.time())})

