# bot/execution.py
import time
import uuid
from typing import Any, Dict, Optional


class PaperExecution: 
    """Paper trading with in-memory state only.  No persistence."""
    
    def __init__(self, start_cash: float = 500.0, price_cache: Optional[Dict] = None):
        self.cash = float(start_cash)
        self.inv:  Dict[str, float] = {}
        self.avg_cost: Dict[str, float] = {}
        self.realized_pnl: float = 0.0
        self.wins: int = 0
        self.losses: int = 0
        self.orders: Dict[str, Dict[str, Any]] = {}
        self.price_cache = price_cache or {}

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
        if order_id in self.orders:
            self.orders[order_id]["status"] = "canceled"

    async def get_order(self, order_id: str) -> Dict[str, Any]:
        self._maybe_fill_all()
        if order_id not in self.orders:
            return {"status": "unknown"}
        o = self.orders[order_id]
        return {
            "status": o["status"],
            "avg_fill_price": o. get("fill_price"),
            "price": o["price"],
        }

    def snapshot(self) -> Dict[str, Any]:
        """Return current state for UI/monitoring."""
        self._maybe_fill_all()
        eq = self._equity_usd()
        unreal = self._unrealized_pnl()
        return {
            "cash_usd": float(self.cash),
            "equity_usd": float(eq),
            "pnl": {
                "realized": float(self.realized_pnl),
                "unrealized": float(unreal),
                "total": float(self.realized_pnl + unreal),
            },
            "stats": {
                "wins": int(self.wins),
                "losses": int(self.losses),
                "winrate": (self.wins / (self.wins + self.losses)) 
                           if (self.wins + self. losses) else None,
            },
            "positions": self._positions_list(),
            "open_orders": self._open_orders_list(),
        }

    # --- Internal ---

    def _place(self, asset_id: str, side: str, price: float, size: float, post_only: bool) -> str:
        oid = uuid.uuid4().hex[:16]
        self.orders[oid] = {
            "asset_id": str(asset_id),
            "side": side,
            "price": float(price),
            "size": float(size),
            "post_only": post_only,
            "status": "open",
            "created_ts": time.time(),
            "fill_price": None,
        }
        return oid

    def _equity_usd(self) -> float:
        eq = float(self.cash)
        for asset_id, qty in self.inv.items():
            bid, ask = self. price_cache.get(asset_id, (None, None))
            if bid and ask:
                mid = (float(bid) + float(ask)) / 2.0
                eq += float(qty) * mid
        return float(eq)

    def _unrealized_pnl(self) -> float:
        upnl = 0.0
        for asset_id, qty in self.inv. items():
            if float(qty) <= 0:
                continue
            bid, ask = self.price_cache.get(asset_id, (None, None))
            if not bid or not ask:
                continue
            mid = (float(bid) + float(ask)) / 2.0
            c = float(self.avg_cost.get(asset_id, 0.0))
            upnl += float(qty) * (mid - c)
        return float(upnl)

    def _maybe_fill_all(self) -> None:
        now = time.time()
        for oid, o in list(self.orders.items()):
            if o["status"] != "open":
                continue
            if (now - o["created_ts"]) < 1.0:
                continue

            asset_id = o["asset_id"]
            bid, ask = self.price_cache.get(asset_id, (None, None))
            if not bid or not ask:
                continue

            bid, ask = float(bid), float(ask)
            price, size = float(o["price"]), float(o["size"])

            if o["side"] == "buy" and abs(price - bid) <= 0.005:
                cost = price * size
                if cost <= self.cash:
                    self. cash -= cost
                    prev_qty = float(self.inv.get(asset_id, 0.0))
                    prev_cost = float(self.avg_cost.get(asset_id, 0.0))
                    new_qty = prev_qty + size
                    self.inv[asset_id] = new_qty
                    self.avg_cost[asset_id] = (prev_qty * prev_cost + size * price) / new_qty
                    o["status"] = "filled"
                    o["fill_price"] = price

            elif o["side"] == "sell" and bid >= price - 1e-9:
                have = float(self.inv.get(asset_id, 0.0))
                sell_sz = min(have, size)
                if sell_sz > 0:
                    cost = float(self.avg_cost.get(asset_id, 0.0))
                    rpnl = sell_sz * (price - cost)
                    self.realized_pnl += rpnl
                    if rpnl > 1e-9:
                        self.wins += 1
                    elif rpnl < -1e-9:
                        self.losses += 1
                    self. inv[asset_id] = have - sell_sz
                    self.cash += price * sell_sz
                    o["status"] = "filled"
                    o["fill_price"] = price

    def _positions_list(self) -> list:
        return [
            {"asset_id": aid, "shares": float(qty), "avg_px": float(self.avg_cost.get(aid, 0))}
            for aid, qty in self.inv.items() if float(qty) > 0
        ]

    def _open_orders_list(self) -> list:
        now = time.time()
        return [
            {
                "id": oid,
                "asset_id": o["asset_id"],
                "side": o["side"],
                "price": float(o["price"]),
                "shares": float(o["size"]),
                "age_sec": int(now - o["created_ts"]),
            }
            for oid, o in self.orders.items() if o["status"] == "open"
        ]
