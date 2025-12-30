# main.py
from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

import sys
import shutil
import yaml

from bot.datafeed import MarketDataFeed, WSConfig
from bot.execution import PaperExecution, PaperExecCfg
from bot.scalp_mode import ScalpMode, MarketSpec
from bot.strategy import EntryRules
from bot.risk import ScalpRisk

from bot.gamma import GammaClient, GammaCfg
from bot.scanner import scan_btc_15m_by_slug, GammaScanParams


def load_yaml(path: str = "config.yaml") -> Dict[str, Any]:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}


def status_line(text: str) -> None:
    """Rewrite one terminal line (no newline)."""
    width = shutil.get_terminal_size((120, 20)).columns
    sys.stdout.write("\r" + text[: width - 1].ljust(width - 1))
    sys.stdout.flush()


async def _stop_feed(feed: MarketDataFeed, feed_task: asyncio.Task, log: logging.Logger) -> None:
    feed.stop()
    feed_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await feed_task


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log = logging.getLogger("polyscalp")

    cfg = load_yaml("config.yaml")
    start_cash = float(cfg.get("start_cash_usd", 500))

    # --- hosts ---
    auth = cfg.get("auth", {}) or {}
    ws_host = auth.get("ws_host") or "wss://ws-subscriptions-clob.polymarket.com"
    ws_url = ws_host.rstrip("/") + "/ws/market"

    # --- gamma scanner config ---
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

    # Shared top-of-book cache used by execution marking
    price_cache: Dict[str, tuple[Optional[float], Optional[float]]] = {}

    # Execution persists across markets (keeps balance)
    exec_ = PaperExecution(
        cfg=PaperExecCfg(start_cash_usd=start_cash),
        price_cache=price_cache,
        log=log,
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

        # stop previous feed if running
        if feed is not None and feed_task is not None:
            await _stop_feed(feed, feed_task, log)
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

        log.info(f"[SCAN] slug={current_slug} tte={found.get('tte')} end_ts={end_ts}")

        market = MarketSpec(yes_asset=yes_asset, no_asset=no_asset, end_ts=end_ts)

        # Reset cache for the two new assets
        price_cache.clear()
        price_cache[market.yes_asset] = (None, None)
        price_cache[market.no_asset] = (None, None)

        scalp = ScalpMode(exec=exec_, market=market, rules=rules, risk=risk, log=log)

        feed = MarketDataFeed(
            cfg=WSConfig(ws_url=ws_url),
            asset_ids=[market.yes_asset, market.no_asset],
            on_book_top=on_book,
            log=log,
        )
        feed_task = asyncio.create_task(feed.run())

    # start first market
    await start_new_market()

    try:
        while True:
            assert market is not None and scalp is not None and feed is not None and feed_task is not None

            now = int(time.time())
            tte = market.end_ts - now

            # single-line status (updates constantly)
            yes_bid, yes_ask = price_cache.get(market.yes_asset, (None, None))
            no_bid, no_ask = price_cache.get(market.no_asset, (None, None))

            def fmt(x: Optional[float]) -> str:
                return "--" if x is None else f"{x:.2f}"

            status_line(
                f"slug={current_slug} | tte={tte:>4}s | "
                f"YES {fmt(yes_bid)}/{fmt(yes_ask)} | "
                f"NO {fmt(no_bid)}/{fmt(no_ask)}"
            )

            if now >= (market.end_ts + rollover_grace_sec):
                # print a newline so the log doesn't overwrite the status line
                sys.stdout.write("\n")
                sys.stdout.flush()

                log.info(f"[ROLLOVER] market ended slug={current_slug} -> scanning next")
                await start_new_market()
                await asyncio.sleep(0.25)
                continue

            await scalp.step()
            await asyncio.sleep(0.2)

    finally:
        # ensure we end the status line cleanly
        sys.stdout.write("\n")
        sys.stdout.flush()

        if feed is not None and feed_task is not None:
            await _stop_feed(feed, feed_task, log)


if __name__ == "__main__":
    asyncio.run(main())