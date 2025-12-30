from dataclasses import dataclass
from typing import Optional

@dataclass
class BookTop:
    bid: Optional[float]
    ask: Optional[float]
    tick_size: float = 0.01

@dataclass
class Position:
    market_id: str
    shares: float = 0.0
    avg_price: float = 0.0

@dataclass
class Quote:
    market_id: str
    bid_price: Optional[float]
    ask_price: Optional[float]
    size: float

@dataclass
class OrderIntent:
    action: str  # "place" | "cancel" | "replace"
    market_id: str
    side: Optional[str] = None  # "buy" | "sell"
    price: Optional[float] = None
    size: Optional[float] = None
    order_id: Optional[str] = None