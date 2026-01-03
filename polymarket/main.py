#!/usr/bin/env python3
"""
Polyscalp:  Paper trading bot for Polymarket BTC 15m markets. 
"""
import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional

import yaml

from bot.datafeed import MarketDataFeed, WSConfig
from bot.execution import PaperExecution
from bot. gamma import GammaClient
from bot.risk import ScalpRisk
from bot.scalp_mode import ScalpMode, MarketSpec
from bot.scanner import scan_btc_15m_by_slug, GammaScanParams
from bot. strategy import EntryRules

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("polyscalp")


def load_config(path: str = "config.yaml") -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}


async def main():
    cfg = load_config("config.yaml")
    
    # Setup
    start_cash = float(cfg. get("start_cash_usd", 500))
    ws_url = cfg["auth"]["ws_host"]. rstrip("/") + "/ws/market"
    
    gamma = GammaClient(cfg["gamma"]["base_url"])
    scan_params = GammaScanParams(
        slug_prefix=cfg["gamma"]["slug_prefix"],
        interval_sec=cfg["gamma"]["interval_sec"],
        lookahead_intervals=cfg["gamma"]["lookahead_intervals"],
    )
    
    min_tte = cfg["markets"]["min_time_to_expiry_sec"]
    max_tte = cfg["markets"]["max_time_to_expiry_sec"]
    
    # Shared state
    price_cache = {}
    exec_ = PaperExecution(start_cash=start_cash, price_cache=price_cache)
    rules = EntryRules(
        price_min=cfg["strategy"]["entry_price_min"],
        price_max=cfg["strategy"]["entry_price_max"],
        tte_max_seconds=cfg["strategy"]["tte_max_seconds"],
    )
    risk = ScalpRisk(
        tp_pct=cfg["risk"]["tp_pct"],
        sl_pct=cfg["risk"]["sl_pct"],
    )
    
    feed:  Optional[MarketDataFeed] = None
    scalp:  Optional[ScalpMode] = None
    market:  Optional[MarketSpec] = None
    
    def on_book(asset_id: str, bid, ask):
        price_cache[asset_id] = (bid, ask)
        if scalp:
            scalp.on_book_top(asset_id, bid, ask)
    
    async def start_new_market():
        nonlocal feed, scalp, market
        
        if feed: 
            feed.stop()
        
        found = scan_btc_15m_by_slug(
            gamma, params=scan_params,
            min_tte_sec=min_tte, max_tte_sec=max_tte
        )
        
        yes_asset = found["yes_asset"]
        no_asset = found["no_asset"]
        end_ts = found["end_ts"]
        slug = found. get("slug", "? ")
        
        log.info(f"Market:  {slug} | TTE: {found['tte']}s")
        
        market = MarketSpec(yes_asset=yes_asset, no_asset=no_asset, end_ts=end_ts)
        price_cache.clear()
        price_cache[yes_asset] = (None, None)
        price_cache[no_asset] = (None, None)
        
        scalp = ScalpMode(exec=exec_, market=market, rules=rules, risk=risk, log=log)
        
        feed = MarketDataFeed(
            cfg=WSConfig(ws_url=ws_url),
            asset_ids=[yes_asset, no_asset],
            on_book_top=on_book,
            log=log,
        )
        asyncio.create_task(feed. run())
    
    await start_new_market()
    
    try:
        while True:
            assert market and scalp and feed
            
            snap = exec_.snapshot()
            yes_bid, yes_ask = price_cache. get(market.yes_asset, (None, None))
            no_bid, no_ask = price_cache. get(market.no_asset, (None, None))
            
            # Print status
            tte = max(0, market.end_ts - asyncio.get_event_loop().time())
            status = (
                f"TTE: {int(tte):>4}s | "
                f"Balance: ${snap['equity_usd']:.2f} | "
                f"PnL: ${snap['pnl']['total']:.2f} | "
                f"W/L: {snap['stats']['wins']}/{snap['stats']['losses']}"
            )
            print(f"\r{status}", end="", flush=True)
            
            # Check market expiry
            import time
            if int(time.time()) >= (market.end_ts + 2):
                print("\n[ROLLOVER]")
                await start_new_market()
                await asyncio.sleep(0.5)
                continue
            
            await scalp.step()
            await asyncio.sleep(0.2)
    
    except KeyboardInterrupt: 
        print("\n[STOP]")
        if feed:
            feed.stop()


if __name__ == "__main__":
    asyncio.run(main())
