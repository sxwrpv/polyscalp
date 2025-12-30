# bot/gamma.py
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class GammaCfg:
    base_url: str = "https://gamma-api.polymarket.com"
    timeout_sec: float = 15.0
    user_agent: str = "Mozilla/5.0"
    accept: str = "application/json"
    # Optional: some environments require a cookie header (your earlier 401 showed this sometimes)
    cookie: Optional[str] = None


class GammaClient:
    def __init__(self, cfg: GammaCfg):
        self.cfg = cfg

    def _headers(self) -> Dict[str, str]:
        h = {
            "User-Agent": self.cfg.user_agent,
            "Accept": self.cfg.accept,
        }
        cookie = self.cfg.cookie or os.getenv("GAMMA_COOKIE")
        if cookie:
            h["Cookie"] = cookie
        return h

    def get_json(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        params = params or {}
        qs = urllib.parse.urlencode(params, doseq=True)
        url = self.cfg.base_url.rstrip("/") + path
        if qs:
            url = url + "?" + qs

        req = urllib.request.Request(url=url, headers=self._headers(), method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self.cfg.timeout_sec) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                # Gamma sometimes returns plain text errors
                return json.loads(body)
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Gamma HTTP {e.code}: {raw[:200]}") from e
        except json.JSONDecodeError as e:
            raise RuntimeError("Gamma returned non-JSON response") from e

    def search(self, query: str, limit_per_type: int = 50) -> Dict[str, Any]:
        # Works if Gamma /search is available to you (often does with UA+Accept headers).
        return self.get_json("/search", {"q": query, "limit_per_type": limit_per_type})

    def event_by_slug(self, slug: str) -> Dict[str, Any]:
        # This endpoint worked for you with UA+Accept headers.
        return self.get_json(f"/events/slug/{urllib.parse.quote(slug)}")