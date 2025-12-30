class SignalEngine:
    def __init__(self, cfg, log):
        self.cfg = cfg
        self.log = log

    def fair_value(self, market_id: str, book_top) -> float:
        # Placeholder “fair value” = mid
        if book_top is None or book_top.bid is None or book_top.ask is None:
            return 0.5
        return (book_top.bid + book_top.ask) / 2.0

    def should_pause(self, market_id: str) -> bool:
        # Placeholder for volatility/news pause logic
        return False