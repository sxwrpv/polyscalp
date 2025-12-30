# bot/scanner.py
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .gamma import GammaClient


def _parse_iso_to_unix(ts: str) -> int:
    s = ts.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def _extract_tokens_and_end(event_obj: Dict[str, Any]) -> Tuple[List[str], int]:
    markets = event_obj.get("markets") or []
    if not markets:
        raise RuntimeError("No markets in event response")

    m0 = markets[0]

    clob = m0.get("clobTokenIds")
    if isinstance(clob, str):
        token_ids = json.loads(clob)
    elif isinstance(clob, list):
        token_ids = clob
    else:
        raise RuntimeError(f"Unexpected clobTokenIds format: {type(clob)}")

    if not isinstance(token_ids, list) or len(token_ids) < 2:
        raise RuntimeError("Need 2 token ids")

    end_date = m0.get("endDate") or event_obj.get("endDate")
    if not end_date:
        raise RuntimeError("Missing endDate")

    end_ts = _parse_iso_to_unix(str(end_date))
    return [str(token_ids[0]), str(token_ids[1])], end_ts


@dataclass
class GammaScanParams:
    slug_prefix: str
    interval_sec: int = 900
    lookahead_intervals: int = 12
    fallback_search_query: str = "btc updown 15m"
    fallback_limit: int = 50


def _pick_best(now: int, candidates: List[Tuple[int, str, str, str, int]]):
    # candidates: (tte, slug, yes, no, end_ts)
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])  # smallest tte first
    tte, slug, yes, no, end_ts = candidates[0]
    return {
        "slug": slug,
        "yes_asset": yes,
        "no_asset": no,
        "end_ts": int(end_ts),
        "tte": int(tte),
    }


def scan_btc_15m_by_slug(
    gamma: GammaClient,
    *,
    params: GammaScanParams,
    min_tte_sec: int,
    max_tte_sec: int,
    debug: bool = True,
) -> Dict[str, Any]:
    now = int(time.time())

    start_ts0 = (now // params.interval_sec) * params.interval_sec

    ok: List[Tuple[int, str, str, str, int]] = []
    rejects = 0

    for i in range(params.lookahead_intervals):
        start_ts = start_ts0 + i * params.interval_sec
        slug = f"{params.slug_prefix}{start_ts}"

        try:
            event = gamma.event_by_slug(slug)
            token_ids, end_ts = _extract_tokens_and_end(event)
            tte = end_ts - now

            if tte <= min_tte_sec:
                rejects += 1
                if debug:
                    print(f"[SCANDBG] reject slug={slug} tte={tte} <= min({min_tte_sec})")
                continue
            if tte > max_tte_sec:
                rejects += 1
                if debug:
                    print(f"[SCANDBG] reject slug={slug} tte={tte} > max({max_tte_sec})")
                continue

            yes_asset, no_asset = token_ids[0], token_ids[1]
            ok.append((tte, slug, yes_asset, no_asset, end_ts))

        except Exception as e:
            rejects += 1
            if debug:
                print(f"[SCANDBG] reject slug={slug} err={e}")
            continue

    best = _pick_best(now, ok)
    if best:
        return best

    # ---- Fallback to /search if slug scan failed ----
    if debug:
        print(f"[SCANDBG] slug scan found none. rejects={rejects}. falling back to /search")

    search = gamma.search(params.fallback_search_query, limit_per_type=params.fallback_limit)
    events = search.get("events") or []

    ok2: List[Tuple[int, str, str, str, int]] = []

    for e in events:
        slug = (e or {}).get("slug")
        if not slug:
            continue
        try:
            event = gamma.event_by_slug(str(slug))
            token_ids, end_ts = _extract_tokens_and_end(event)
            tte = end_ts - now
            if tte <= min_tte_sec or tte > max_tte_sec:
                continue
            yes_asset, no_asset = token_ids[0], token_ids[1]
            ok2.append((tte, str(slug), yes_asset, no_asset, end_ts))
        except Exception:
            continue

    best2 = _pick_best(now, ok2)
    if best2:
        return best2

    raise RuntimeError("No valid BTC 15m market found in lookahead window (slug + search fallback)")