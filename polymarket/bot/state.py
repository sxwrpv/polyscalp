from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from bot.models import BookTop, Position

@dataclass
class BotState:
    active_markets: List[str] = field(default_factory=list)
    books: Dict[str, BookTop] = field(default_factory=dict)
    positions: Dict[str, Position] = field(default_factory=dict)
    open_orders: Dict[str, dict] = field(default_factory=dict)  # order_id -> details
    connected: bool = False

    def set_active_markets(self, markets: List[str]) -> None:
        self.active_markets = markets

    def update_book_top(self, market_id: str, bid: Optional[float], ask: Optional[float], tick: float = 0.01) -> None:
        self.books[market_id] = BookTop(bid=bid, ask=ask, tick_size=tick)

    def get_book_top(self, market_id: str) -> Optional[BookTop]:
        return self.books.get(market_id)