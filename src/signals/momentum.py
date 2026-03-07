import pandas as pd

from src.signals.base import BaseSignal


class MomentumSignal(BaseSignal):
    """Price momentum over 1-bar and 5-bar windows, averaged."""

    name = "momentum"

    def compute(self, bars: pd.DataFrame) -> float:
        close = bars["close"]
        # 1-bar return
        ret1 = (close.iloc[-1] - close.iloc[-2]) / close.iloc[-2]
        # 5-bar return
        if len(close) >= 6:
            ret5 = (close.iloc[-1] - close.iloc[-6]) / close.iloc[-6]
        else:
            ret5 = ret1

        # Normalize: typical intraday move is ~0.5%, clip at ±2%
        norm1 = ret1 / 0.02
        norm5 = ret5 / 0.02
        score = (norm1 + norm5) / 2
        return max(-1.0, min(1.0, score))
