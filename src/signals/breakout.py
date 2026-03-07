import pandas as pd

from src.signals.base import BaseSignal


class BreakoutSignal(BaseSignal):
    """Breakout signal: price breaking above/below N-bar high/low."""

    name = "breakout"

    def __init__(self, lookback: int = 20):
        self.lookback = lookback

    def compute(self, bars: pd.DataFrame) -> float:
        if len(bars) < self.lookback + 1:
            return 0.0

        window = bars.iloc[-self.lookback - 1:-1]  # exclude current bar
        high_n = window["high"].max()
        low_n = window["low"].min()

        price = bars["close"].iloc[-1]

        if high_n == low_n:
            return 0.0

        mid = (high_n + low_n) / 2
        range_ = (high_n - low_n) / 2

        # Breakout above high → +1, below low → -1
        score = (price - mid) / range_
        return max(-1.0, min(1.0, score))
