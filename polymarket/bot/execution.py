# bot/execution.py
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class PaperExecCfg:
    start_cash_usd: float = 500.0
    fill_delay_sec: float = 1.0
    tick: float = 0.01


@dataclass
class Order:
    order_id: str
    asset_id: str
    side: str              # "buy" or "sell"
    price: float
    size: float
    post_only: bool
    status: str            # "open" | "filled" | "canceled"
    created_ts: float
    filled_ts: Optional[float] = None
    avg_fill_price: Optional[float] = None


class PaperExecution:
    """
    Paper execution with persistence (state_path) so balance doesn't reset between stop/start.
    """

    def __init__(
        self,
        *,
        cfg: PaperExecCfg,
        price_cache: Dict[str, Tuple[Optional[float], Optional[float]]],
        log: Any = None,
        state_path: Optional[str] = None,
        persist_orders: bool = False,
    ):
        self.cfg = cfg
        self.log = log
        self.price_cache = price_cache

        self.state_path = state_path
        self.persist_orders = bool(persist_orders)

        self.cash = float(cfg.start_cash_usd)
        self.inv: Dict[str, float] = {}         # asset_id -> shares
        self.avg_cost: Dict[str, float] = {}    # asset_id -> avg cost per share

        self.realized_pnl: float = 0.0
        self.wins: int = 0
        self.losses: int = 0

        self.orders: Dict[str, Order] = {}
        self._last_save_ts: float = 0.0

        self._load_state_if_present()

    # ---------- Interface used by ScalpMode ----------

    async def get_balance_usd(self) -> float:
        self._maybe_fill_all()
        return float(self._equity_usd())

    async def place_post_only_limit_buy(self, asset_id: str, price: float, size: float) -> str:
        return self._place(asset_id, "buy", price, size, post_only=True)

    async def place_post_only_limit_sell(self, asset_id: str, price: float, size: float) -> str:
        return self._place(asset_id, "sell", price, size, post_only=True)

    async def place_limit_sell(self, asset_id: str, price: float, size: float) -> str:
        return self._place(asset_id, "sell", price, size, post_only=False)

    async def cancel_order(self, order_id: str) -> None:
        o = self.orders.get(order_id)
        if not o:
            return
        if o.status == "open":
            o.status = "canceled"
            self._maybe_save(force=False)

    async def get_order(self, order_id: str) -> Dict[str, Any]:
        self._maybe_fill_all()
        o = self.orders.get(order_id)
        if not o:
            return {"status": "unknown"}
        return {
            "order_id": o.order_id,
            "asset_id": o.asset_id,
            "side": o.side,
            "price": o.price,
            "size": o.size,
            "post_only": o.post_only,
            "status": o.status,
            "avg_fill_price": o.avg_fill_price,
            "created_ts": o.created_ts,
            "filled_ts": o.filled_ts,
        }

    # ---------- UI snapshot helpers ----------

    def snapshot(self) -> Dict[str, Any]:
        self._maybe_fill_all()
        eq = self._equity_usd()
        unreal = self._unrealized_pnl()
        total = self.realized_pnl + unreal
        return {
            "cash_usd": float(self.cash),
            "equity_usd": float(eq),
            "pnl": {"realized": float(self.realized_pnl), "unrealized": float(unreal), "total": float(total)},
            "stats": {
                "wins": int(self.wins),
                "losses": int(self.losses),
                "winrate": (self.wins / (self.wins + self.losses)) if (self.wins + self.losses) else None,
            },
            "positions": self._positions_list(),
            "open_orders": self._open_orders_list(),
        }

    # ---------- Internal ----------

    def _place(self, asset_id: str, side: str, price: float, size: float, post_only: bool) -> str:
        oid = uuid.uuid4().hex[:16]
        o = Order(
            order_id=oid,
            asset_id=str(asset_id),
            side=str(side),
            price=float(price),
            size=float(size),
            post_only=bool(post_only),
            status="open",
            created_ts=time.time(),
        )
        self.orders[oid] = o
        self._maybe_save(force=False)
        return oid

    def _equity_usd(self) -> float:
        eq = float(self.cash)
        for asset_id, qty in self.inv.items():
            bid, ask = self.price_cache.get(asset_id, (None, None))
            if bid is None or ask is None:
                continue
            mid = (float(bid) + float(ask)) / 2.0
            eq += float(qty) * mid
        return float(eq)

    def _unrealized_pnl(self) -> float:
        upnl = 0.0
        for asset_id, qty in self.inv.items():
            if float(qty) <= 0:
                continue
            bid, ask = self.price_cache.get(asset_id, (None, None))
            if bid is None or ask is None:
                continue
            mid = (float(bid) + float(ask)) / 2.0
            c = float(self.avg_cost.get(asset_id, 0.0))
            upnl += float(qty) * (mid - c)
        return float(upnl)

    def _maybe_fill_all(self) -> None:
        now = time.time()
        changed = False

        for o in list(self.orders.values()):
            if o.status != "open":
                continue
            if (now - o.created_ts) < float(self.cfg.fill_delay_sec):
                continue

            bid, ask = self.price_cache.get(o.asset_id, (None, None))
            if bid is None or ask is None:
                continue

            bid = float(bid)
            ask = float(ask)

            if o.side == "buy":
                if abs(o.price - bid) <= (float(self.cfg.tick) / 2.0):
                    cost = o.price * o.size
                    if cost <= self.cash + 1e-9:
                        self.cash -= cost
                        prev_qty = float(self.inv.get(o.asset_id, 0.0))
                        prev_cost = float(self.avg_cost.get(o.asset_id, 0.0))
                        new_qty = prev_qty + float(o.size)
                        new_avg = (prev_qty * prev_cost + float(o.size) * float(o.price)) / new_qty
                        self.inv[o.asset_id] = new_qty
                        self.avg_cost[o.asset_id] = float(new_avg)
                        self._mark_filled(o, o.price)
                        changed = True

            elif o.side == "sell":
                if bid >= o.price - 1e-9:
                    have = float(self.inv.get(o.asset_id, 0.0))
                    sell_sz = min(have, float(o.size))
                    if sell_sz > 0:
                        c = float(self.avg_cost.get(o.asset_id, 0.0))
                        rpnl = sell_sz * (float(o.price) - c)
                        self.realized_pnl += rpnl
                        if rpnl > 1e-9:
                            self.wins += 1
                        elif rpnl < -1e-9:
                            self.losses += 1

                        self.inv[o.asset_id] = have - sell_sz
                        self.cash += float(o.price) * sell_sz

                        if self.inv[o.asset_id] <= 1e-12:
                            self.inv[o.asset_id] = 0.0
                            self.avg_cost[o.asset_id] = 0.0

                        self._mark_filled(o, o.price)
                        changed = True

        if changed:
            self._maybe_save(force=False)

    def _mark_filled(self, o: Order, fill_price: float) -> None:
        o.status = "filled"
        o.filled_ts = time.time()
        o.avg_fill_price = float(fill_price)

    def _positions_list(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for asset_id, qty in self.inv.items():
            if float(qty) == 0.0:
                continue
            out.append({"asset_id": asset_id, "shares": float(qty), "avg_px": float(self.avg_cost.get(asset_id, 0.0))})
        return out

    def _open_orders_list(self) -> List[Dict[str, Any]]:
        now = time.time()
        out: List[Dict[str, Any]] = []
        for o in self.orders.values():
            if o.status != "open":
                continue
            out.append(
                {
                    "id": o.order_id,
                    "asset_id": o.asset_id,
                    "side": o.side,
                    "price": float(o.price),
                    "shares": float(o.size),
                    "age_sec": int(now - float(o.created_ts)),
                }
            )
        out.sort(key=lambda x: x["age_sec"], reverse=True)
        return out

    # ---------- Persistence ----------

    def _load_state_if_present(self) -> None:
        if not self.state_path:
            return
        p = Path(self.state_path)
        if not p.exists():
            return
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            self.cash = float(data.get("cash_usd", self.cash))
            self.inv = {str(k): float(v) for k, v in (data.get("inv", {}) or {}).items()}
            self.avg_cost = {str(k): float(v) for k, v in (data.get("avg_cost", {}) or {}).items()}
            self.realized_pnl = float(data.get("realized_pnl", self.realized_pnl))
            st = data.get("stats", {}) or {}
            self.wins = int(st.get("wins", self.wins))
            self.losses = int(st.get("losses", self.losses))
        except Exception as e:
            if self.log:
                self.log.warning(f"[PAPER] state load failed: {e!r}")

    def _maybe_save(self, force: bool) -> None:
        if not self.state_path:
            return
        now = time.time()
        if (not force) and (now - self._last_save_ts) < 0.5:
            return

        p = Path(self.state_path)
        p.parent.mkdir(parents=True, exist_ok=True)

        data: Dict[str, Any] = {
            "cash_usd": float(self.cash),
            "inv": {k: float(v) for k, v in self.inv.items()},
            "avg_cost": {k: float(v) for k, v in self.avg_cost.items()},
            "realized_pnl": float(self.realized_pnl),
            "stats": {"wins": int(self.wins), "losses": int(self.losses)},
        }

        tmp = p.with_suffix(p.suffix + ".tmp")
        try:
            tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, p)
            self._last_save_ts = now
        except Exception as e:
            if self.log:
                self.log.warning(f"[PAPER] state save failed: {e!r}")