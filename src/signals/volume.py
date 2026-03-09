import pandas as pd

from src.signals.base import BaseSignal


class VolumeSignal(BaseSignal):
    """Volume spike detection: above-average volume confirms current direction."""

    name = "volume"

    def __init__(self, lookback: int = 60):
        """lookback: Volume average period (default 60 = 1 hour with 1-min bars)"""
        self.lookback = lookback

    def compute(self, bars: pd.DataFrame) -> float:
        if "volume" not in bars.columns or len(bars) < self.lookback:
            return 0.0

        vol_now = bars["volume"].iloc[-1]
        vol_avg = bars["volume"].iloc[-self.lookback:-1].mean()

        if vol_avg == 0 or pd.isna(vol_avg):
            return 0.0

        ratio = vol_now / vol_avg  # >1 means spike

        # Determine direction of current bar
        close = bars["close"].iloc[-1]
        open_ = bars["open"].iloc[-1] if "open" in bars.columns else bars["close"].iloc[-2]
        direction = 1.0 if close >= open_ else -1.0

        # Volume spike amplifies direction
        spike_score = (ratio - 1.0) / 2.0  # ratio=3 → score=1
        return max(-1.0, min(1.0, direction * spike_score))
