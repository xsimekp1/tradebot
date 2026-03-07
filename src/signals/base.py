from abc import ABC, abstractmethod

import pandas as pd


class BaseSignal(ABC):
    name: str

    @abstractmethod
    def compute(self, bars: pd.DataFrame) -> float:
        """Returns a signal value in [-1, 1].
        Positive = bullish, Negative = bearish, 0 = neutral.
        """

    def safe_compute(self, bars: pd.DataFrame) -> float:
        """Wraps compute() with error handling; returns 0.0 on failure."""
        try:
            if bars is None or bars.empty or len(bars) < 5:
                return 0.0
            result = self.compute(bars)
            if result is None or not isinstance(result, (int, float)):
                return 0.0
            return float(max(-1.0, min(1.0, result)))
        except Exception:
            return 0.0
