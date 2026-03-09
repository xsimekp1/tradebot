import pandas as pd

from src.signals.base import BaseSignal


class MomentumSignal(BaseSignal):
    """Price momentum over short and long windows, averaged."""

    name = "momentum"

    def __init__(self, short_period: int = 15, long_period: int = 60):
        """
        Args:
            short_period: Short-term momentum window (default 15 = 15 min with 1-min bars)
            long_period: Long-term momentum window (default 60 = 1 hour with 1-min bars)
        """
        self.short_period = short_period
        self.long_period = long_period

    def compute(self, bars: pd.DataFrame) -> float:
        close = bars["close"]
        if len(close) < self.long_period + 1:
            return 0.0

        # Short-term return
        ret_short = (close.iloc[-1] - close.iloc[-self.short_period - 1]) / close.iloc[-self.short_period - 1]
        # Long-term return
        ret_long = (close.iloc[-1] - close.iloc[-self.long_period - 1]) / close.iloc[-self.long_period - 1]

        # Normalize: expect ~1-2% moves over an hour, clip at ±5%
        norm_short = ret_short / 0.03
        norm_long = ret_long / 0.05
        score = (norm_short + norm_long) / 2
        return max(-1.0, min(1.0, score))
