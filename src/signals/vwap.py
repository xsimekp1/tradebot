import pandas as pd

from src.signals.base import BaseSignal


class VWAPSignal(BaseSignal):
    """VWAP deviation: price below VWAP → bullish, above → bearish."""

    name = "vwap"

    def compute(self, bars: pd.DataFrame) -> float:
        if "volume" not in bars.columns or bars["volume"].sum() == 0:
            return 0.0

        typical_price = (bars["high"] + bars["low"] + bars["close"]) / 3
        vwap = (typical_price * bars["volume"]).sum() / bars["volume"].sum()

        price = bars["close"].iloc[-1]
        if vwap == 0:
            return 0.0

        # Deviation as a fraction of VWAP
        deviation = (vwap - price) / vwap  # positive = price below VWAP → bullish
        # Normalize: 1% deviation → ±1
        score = deviation / 0.01
        return max(-1.0, min(1.0, score))
