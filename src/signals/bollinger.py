import pandas as pd
import ta

from src.signals.base import BaseSignal


class BollingerSignal(BaseSignal):
    """Bollinger Band distance: price near lower band → long, upper → short."""

    name = "bollinger"

    def __init__(self, period: int = 60, std_dev: float = 2.0):
        """period: Bollinger lookback (default 60 = 1 hour with 1-min bars)"""
        self.period = period
        self.std_dev = std_dev

    def compute(self, bars: pd.DataFrame) -> float:
        if len(bars) < self.period:
            return 0.0
        bb = ta.volatility.BollingerBands(
            close=bars["close"], window=self.period, window_dev=self.std_dev
        )
        upper = bb.bollinger_hband().iloc[-1]
        lower = bb.bollinger_lband().iloc[-1]
        mid = bb.bollinger_mavg().iloc[-1]
        price = bars["close"].iloc[-1]

        if pd.isna(upper) or pd.isna(lower) or upper == lower:
            return 0.0

        # %B: 0=lower, 0.5=mid, 1=upper → map to [-1, +1] inverted
        pct_b = (price - lower) / (upper - lower)
        score = 1.0 - 2.0 * pct_b  # lower band → +1, upper band → -1
        return max(-1.0, min(1.0, score))
