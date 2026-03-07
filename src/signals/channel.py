"""
Channel-based signals using optimized support/resistance line detection.
"""
import numpy as np
import pandas as pd
from typing import Tuple, Optional

from src.signals.base import BaseSignal


def find_optimal_resistance_line(
    prices: np.ndarray,
    penalty: float = 20.0
) -> Tuple[float, float, float]:
    """
    Find optimal resistance line above price data using grid search.

    Returns: (slope, intercept, avg_distance)
    - slope: price change per bar
    - intercept: price at bar 0
    - avg_distance: average distance from line to prices
    """
    n = len(prices)
    if n < 20:
        return 0.0, prices[-1] if n > 0 else 0.0, 0.0

    max_idx = int(np.argmax(prices))
    max_price = prices[max_idx]
    price_range = max_price - np.min(prices)

    if price_range < 1e-8:
        return 0.0, max_price, 0.0

    # Grid search parameters
    slope_steps = 15
    offset_steps = 15
    slope_range = price_range / n * 0.5  # Max slope: 50% of range over period

    best_score = float('inf')
    best_slope = 0.0
    best_intercept = max_price
    best_avg_dist = 0.0

    indices = np.arange(n)

    for slope_i in range(slope_steps):
        slope = -slope_range + (2 * slope_range * slope_i / (slope_steps - 1))
        base_intercept = max_price - slope * max_idx

        for offset_i in range(offset_steps):
            offset = -price_range * 0.1 + (price_range * 0.3 * offset_i / (offset_steps - 1))
            intercept = base_intercept + offset

            # Calculate line values
            line_values = intercept + slope * indices
            diffs = line_values - prices

            # Score: normal distance if below line, penalty if above
            positive = diffs >= 0
            score = np.sum(diffs[positive]) + np.sum(np.abs(diffs[~positive]) * penalty)
            avg_dist = np.mean(np.abs(diffs))

            if score < best_score:
                best_score = score
                best_slope = slope
                best_intercept = intercept
                best_avg_dist = avg_dist

    return best_slope, best_intercept, best_avg_dist


def find_optimal_support_line(
    prices: np.ndarray,
    penalty: float = 20.0
) -> Tuple[float, float, float]:
    """
    Find optimal support line below price data using grid search.

    Returns: (slope, intercept, avg_distance)
    """
    n = len(prices)
    if n < 20:
        return 0.0, prices[-1] if n > 0 else 0.0, 0.0

    min_idx = int(np.argmin(prices))
    min_price = prices[min_idx]
    price_range = np.max(prices) - min_price

    if price_range < 1e-8:
        return 0.0, min_price, 0.0

    slope_steps = 15
    offset_steps = 15
    slope_range = price_range / n * 0.5

    best_score = float('inf')
    best_slope = 0.0
    best_intercept = min_price
    best_avg_dist = 0.0

    indices = np.arange(n)

    for slope_i in range(slope_steps):
        slope = -slope_range + (2 * slope_range * slope_i / (slope_steps - 1))
        base_intercept = min_price - slope * min_idx

        for offset_i in range(offset_steps):
            offset = -price_range * 0.3 + (price_range * 0.1 * offset_i / (offset_steps - 1))
            intercept = base_intercept + offset

            line_values = intercept + slope * indices
            diffs = prices - line_values  # Inverted: price above line is good

            positive = diffs >= 0
            score = np.sum(diffs[positive]) + np.sum(np.abs(diffs[~positive]) * penalty)
            avg_dist = np.mean(np.abs(diffs))

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

    def __init__(self, lookback: int = 120):
        """
        Args:
            lookback: Number of bars to use for line detection (default: 120 = 10 hours at 5min)
        """
        self.lookback = lookback

    def compute(self, bars: pd.DataFrame) -> float:
        if len(bars) < 30:
            return 0.0

        # Use last N bars for channel detection
        prices = bars["close"].values[-self.lookback:] if len(bars) > self.lookback else bars["close"].values
        current_price = prices[-1]

        # Find support and resistance lines
        r_slope, r_intercept, _ = find_optimal_resistance_line(prices)
        s_slope, s_intercept, _ = find_optimal_support_line(prices)

        # Current line values
        n = len(prices) - 1
        resistance_price = r_intercept + r_slope * n
        support_price = s_intercept + s_slope * n

        # Channel width
        channel_width = resistance_price - support_price
        if channel_width <= 0:
            return 0.0

        # Position in channel: 0 = at support, 1 = at resistance
        position = (current_price - support_price) / channel_width
        position = max(0.0, min(1.0, position))  # Clamp

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

    def __init__(self, lookback: int = 120):
        self.lookback = lookback

    def compute(self, bars: pd.DataFrame) -> float:
        if len(bars) < 30:
            return 0.0

        prices = bars["close"].values[-self.lookback:] if len(bars) > self.lookback else bars["close"].values
        current_price = prices[-1]

        r_slope, _, _ = find_optimal_resistance_line(prices)
        s_slope, _, _ = find_optimal_support_line(prices)

        # Average slope of channel (price change per bar)
        avg_slope = (r_slope + s_slope) / 2

        # Normalize by current price level
        # Typical significant move: 0.1% per bar = 0.001 * price
        # Scale so that 0.1% per bar = signal of 1.0
        normalized_slope = avg_slope / (current_price * 0.001) if current_price > 0 else 0.0

        return max(-1.0, min(1.0, normalized_slope))
