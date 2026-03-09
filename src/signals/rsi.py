import pandas as pd
import ta

from src.signals.base import BaseSignal


class RSISignal(BaseSignal):
    """RSI-based signal: overbought → short, oversold → long."""

    name = "rsi"

    def __init__(self, period: int = 60):
        """period: RSI lookback (default 60 = 1 hour with 1-min bars)"""
        self.period = period

    def compute(self, bars: pd.DataFrame) -> float:
        if len(bars) < self.period + 1:
            return 0.0
        rsi = ta.momentum.RSIIndicator(close=bars["close"], window=self.period).rsi().iloc[-1]
        if pd.isna(rsi):
            return 0.0
        # RSI 30 → +1 (oversold, buy), RSI 70 → -1 (overbought, sell)
        # Linear mapping: 50 → 0
        score = (50 - rsi) / 50
        return max(-1.0, min(1.0, score))
