"""
Channel-based signals using optimized support/resistance line detection.
Uses warm-start optimization: subsequent calls use previous solution as starting point.
"""
import numpy as np
import pandas as pd
from typing import Tuple, Optional

from src.signals.base import BaseSignal


def find_optimal_resistance_line(
    prices: np.ndarray,
    penalty: float = 20.0,
    prev_slope: Optional[float] = None,
    prev_intercept: Optional[float] = None,
) -> Tuple[float, float, float]:
    """
    Find optimal resistance line above price data.

    If prev_slope/prev_intercept provided, does a local search around that point first.
    Falls back to full grid search if no previous solution or local search fails.

    Returns: (slope, intercept, avg_distance)
    """
    n = len(prices)
    if n < 20:
        return 0.0, prices[-1] if n > 0 else 0.0, 0.0

    max_idx = int(np.argmax(prices))
    max_price = prices[max_idx]
    min_price = np.min(prices)
    price_range = max_price - min_price

    if price_range < 1e-8:
        return 0.0, max_price, 0.0

    indices = np.arange(n)

    def evaluate(slope: float, intercept: float) -> Tuple[float, float]:
        """Returns (score, avg_dist) for a given line."""
        line_values = intercept + slope * indices
        diffs = line_values - prices
        positive = diffs >= 0
        score = np.sum(diffs[positive]) + np.sum(np.abs(diffs[~positive]) * penalty)
        avg_dist = np.mean(np.abs(diffs))
        return score, avg_dist

    best_score = float('inf')
    best_slope = 0.0
    best_intercept = max_price
    best_avg_dist = 0.0

    # If we have a previous solution, try local search first (5x5 grid around it)
    if prev_slope is not None and prev_intercept is not None:
        # Adjust intercept for the 1-bar shift (window moved forward by 1)
        adjusted_intercept = prev_intercept + prev_slope

        local_slope_range = price_range / n * 0.1  # Smaller range for local search
        local_offset_range = price_range * 0.05

        for slope_i in range(5):
            slope = prev_slope - local_slope_range + (2 * local_slope_range * slope_i / 4)
            for offset_i in range(5):
                offset = -local_offset_range + (2 * local_offset_range * offset_i / 4)
                intercept = adjusted_intercept + offset

                score, avg_dist = evaluate(slope, intercept)
                if score < best_score:
                    best_score = score
                    best_slope = slope
                    best_intercept = intercept
                    best_avg_dist = avg_dist

        # If local search found something reasonable, return it
        if best_score < float('inf'):
            return best_slope, best_intercept, best_avg_dist

    # Full grid search (15x15) - either first call or local search failed
    slope_range = price_range / n * 0.5

    for slope_i in range(15):
        slope = -slope_range + (2 * slope_range * slope_i / 14)
        base_intercept = max_price - slope * max_idx

        for offset_i in range(15):
            offset = -price_range * 0.1 + (price_range * 0.3 * offset_i / 14)
            intercept = base_intercept + offset

            score, avg_dist = evaluate(slope, intercept)
            if score < best_score:
                best_score = score
                best_slope = slope
                best_intercept = intercept
                best_avg_dist = avg_dist

    return best_slope, best_intercept, best_avg_dist


def find_optimal_support_line(
    prices: np.ndarray,
    penalty: float = 20.0,
    prev_slope: Optional[float] = None,
    prev_intercept: Optional[float] = None,
) -> Tuple[float, float, float]:
    """
    Find optimal support line below price data.

    Uses warm-start optimization if previous solution provided.

    Returns: (slope, intercept, avg_distance)
    """
    n = len(prices)
    if n < 20:
        return 0.0, prices[-1] if n > 0 else 0.0, 0.0

    min_idx = int(np.argmin(prices))
    min_price = prices[min_idx]
    max_price = np.max(prices)
    price_range = max_price - min_price

    if price_range < 1e-8:
        return 0.0, min_price, 0.0

    indices = np.arange(n)

    def evaluate(slope: float, intercept: float) -> Tuple[float, float]:
        """Returns (score, avg_dist) for a given line."""
        line_values = intercept + slope * indices
        diffs = prices - line_values  # Inverted: price above line is good
        positive = diffs >= 0
        score = np.sum(diffs[positive]) + np.sum(np.abs(diffs[~positive]) * penalty)
        avg_dist = np.mean(np.abs(diffs))
        return score, avg_dist

    best_score = float('inf')
    best_slope = 0.0
    best_intercept = min_price
    best_avg_dist = 0.0

    # If we have a previous solution, try local search first (5x5 grid)
    if prev_slope is not None and prev_intercept is not None:
        adjusted_intercept = prev_intercept + prev_slope

        local_slope_range = price_range / n * 0.1
        local_offset_range = price_range * 0.05

        for slope_i in range(5):
            slope = prev_slope - local_slope_range + (2 * local_slope_range * slope_i / 4)
            for offset_i in range(5):
                offset = -local_offset_range + (2 * local_offset_range * offset_i / 4)
                intercept = adjusted_intercept + offset

                score, avg_dist = evaluate(slope, intercept)
                if score < best_score:
                    best_score = score
                    best_slope = slope
                    best_intercept = intercept
                    best_avg_dist = avg_dist

        if best_score < float('inf'):
            return best_slope, best_intercept, best_avg_dist

    # Full grid search (15x15)
    slope_range = price_range / n * 0.5

    for slope_i in range(15):
        slope = -slope_range + (2 * slope_range * slope_i / 14)
        base_intercept = min_price - slope * min_idx

        for offset_i in range(15):
            offset = -price_range * 0.3 + (price_range * 0.1 * offset_i / 14)
            intercept = base_intercept + offset

            score, avg_dist = evaluate(slope, intercept)
            if score < best_score:
                best_score = score
                best_slope = slope
                best_intercept = intercept
                best_avg_dist = avg_dist

    return best_slope, best_intercept, best_avg_dist


class ChannelPositionSignal(BaseSignal):
    """
    Signal based on price position within support/resistance channel.

    Near support (bottom) → positive (buy signal)
    Near resistance (top) → negative (sell signal)
    Uses non-linear scaling (power 1.5) for stronger signals at edges.
    """

    name = "channel_position"

    def __init__(self, lookback: int = 600):
        self.lookback = lookback
        # Cache for warm-start optimization
        self._prev_r_slope: Optional[float] = None
        self._prev_r_intercept: Optional[float] = None
        self._prev_s_slope: Optional[float] = None
        self._prev_s_intercept: Optional[float] = None
        # Last computed channel info (for external access)
        self.last_channel_info: Optional[dict] = None

    def compute(self, bars: pd.DataFrame) -> float:
        if len(bars) < 30:
            self.last_channel_info = None
            return 0.0

        prices = bars["close"].values[-self.lookback:] if len(bars) > self.lookback else bars["close"].values
        current_price = prices[-1]

        # Find lines with warm-start
        r_slope, r_intercept, _ = find_optimal_resistance_line(
            prices, prev_slope=self._prev_r_slope, prev_intercept=self._prev_r_intercept
        )
        s_slope, s_intercept, _ = find_optimal_support_line(
            prices, prev_slope=self._prev_s_slope, prev_intercept=self._prev_s_intercept
        )

        # Cache for next call
        self._prev_r_slope = r_slope
        self._prev_r_intercept = r_intercept
        self._prev_s_slope = s_slope
        self._prev_s_intercept = s_intercept

        # Extrapolate lines to current bar (last index in window)
        n = len(prices) - 1
        resistance_price = r_intercept + r_slope * n
        support_price = s_intercept + s_slope * n

        # Channel width
        channel_width = resistance_price - support_price
        if channel_width <= 0:
            self.last_channel_info = None
            return 0.0

        # Position in channel: 0 = at support, 1 = at resistance
        position = (current_price - support_price) / channel_width
        # If price is outside channel bounds, signal is unreliable — return neutral
        if position < 0.0 or position > 1.0:
            self.last_channel_info = None
            return 0.0

        # Support line diagnostics
        support_line_vals = s_intercept + s_slope * np.arange(len(prices))
        s_breaks = int(np.sum(prices < support_line_vals))
        s_break_pct = s_breaks / len(prices) * 100
        local_slope_range = (max(prices) - min(prices)) / len(prices) * 0.1
        local_offset_range = (max(prices) - min(prices)) * 0.05

        # Store channel info for external access
        self.last_channel_info = {
            "support_price": round(support_price, 2),
            "resistance_price": round(resistance_price, 2),
            "channel_width": round(channel_width, 2),
            "position_pct": round(position * 100, 1),
            "current_price": round(current_price, 2),
            "support_breaks": s_breaks,
            "support_breaks_pct": round(s_break_pct, 1),
            "support_slope": round(s_slope, 6),
            "support_search_range": round(local_offset_range, 2),
        }

        # Linear signal: +1 at support, -1 at resistance
        linear_signal = 1.0 - 2.0 * position

        # Non-linear scaling (power 1.5) - stronger at edges
        if linear_signal >= 0:
            signal = linear_signal ** 1.5
        else:
            signal = -((-linear_signal) ** 1.5)

        return max(-1.0, min(1.0, signal))


class ChannelSlopeSignal(BaseSignal):
    """
    Signal based on the slope of the channel (average of support and resistance slopes).

    Rising channel → positive (bullish)
    Falling channel → negative (bearish)
    """

    name = "channel_slope"

    def __init__(self, lookback: int = 600):
        self.lookback = lookback
        self._prev_r_slope: Optional[float] = None
        self._prev_r_intercept: Optional[float] = None
        self._prev_s_slope: Optional[float] = None
        self._prev_s_intercept: Optional[float] = None

    def compute(self, bars: pd.DataFrame) -> float:
        if len(bars) < 30:
            return 0.0

        prices = bars["close"].values[-self.lookback:] if len(bars) > self.lookback else bars["close"].values
        current_price = prices[-1]

        r_slope, r_intercept, _ = find_optimal_resistance_line(
            prices, prev_slope=self._prev_r_slope, prev_intercept=self._prev_r_intercept
        )
        s_slope, s_intercept, _ = find_optimal_support_line(
            prices, prev_slope=self._prev_s_slope, prev_intercept=self._prev_s_intercept
        )

        # Cache for next call
        self._prev_r_slope = r_slope
        self._prev_r_intercept = r_intercept
        self._prev_s_slope = s_slope
        self._prev_s_intercept = s_intercept

        # Average slope of channel
        avg_slope = (r_slope + s_slope) / 2

        # Normalize by current price level
        normalized_slope = avg_slope / (current_price * 0.001) if current_price > 0 else 0.0

        return max(-1.0, min(1.0, normalized_slope))
