import pandas as pd
import ta

from src.signals.base import BaseSignal


class ATRSignal(BaseSignal):
    """ATR volatility expansion: rising ATR → increased signal strength.
    Returns positive when volatility is expanding (more signal confidence).
    This is typically used as a weight modifier, not a directional signal.
    """

    name = "atr"

    def __init__(self, period: int = 14):
        self.period = period

    def compute(self, bars: pd.DataFrame) -> float:
        if len(bars) < self.period + 1:
            return 0.0

        atr_series = ta.volatility.AverageTrueRange(
            high=bars["high"], low=bars["low"], close=bars["close"], window=self.period
        ).average_true_range()

        if len(atr_series.dropna()) < 2:
            return 0.0

        atr_now = atr_series.iloc[-1]
        atr_prev = atr_series.iloc[-self.period]

        if pd.isna(atr_now) or pd.isna(atr_prev) or atr_prev == 0:
            return 0.0

        # ATR expanding → positive (more movement = opportunities)
        change = (atr_now - atr_prev) / atr_prev
        score = change / 0.5  # 50% ATR expansion → ±1
        return max(-1.0, min(1.0, score))
