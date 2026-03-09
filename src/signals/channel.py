"""
Channel-based signals using optimized support/resistance line detection.

Algorithm: Shift-Rotate Coordinate Descent
1. Start from initial line (max/min price horizontal, or previous solution)
2. Alternate between:
   - SHIFT: move line up/down by step (% of price range)
   - ROTATE: rotate around pivot at 1/3 from current bar (~200 bars back)
3. Decrease step sizes each iteration for finer refinement
4. Repeat for N iterations

This is more intuitive and stable than grid search:
- Pivot at 1/3 from end keeps recent data stable during rotations
- Alternating shift/rotate is coordinate descent optimization
- Decreasing steps ensure convergence
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
    iterations: int = 6,
) -> Tuple[float, float, float]:
    """
    Find optimal resistance line above price data using shift-rotate optimization.

    Returns: (slope, intercept, avg_distance)
    """
    n = len(prices)
    if n < 20:
        return 0.0, prices[-1] if n > 0 else 0.0, 0.0

    max_price = float(np.max(prices))
    min_price = float(np.min(prices))
    price_range = max_price - min_price

    if price_range < 1e-8:
        return 0.0, max_price, 0.0

    indices = np.arange(n)
    # Time weights: recent data matters more (0.3 → 1.0)
    time_weights = np.linspace(0.3, 1.0, n)

    def evaluate(slope: float, intercept: float) -> Tuple[float, float]:
        """Score a line. Lower is better. Penalizes breakthroughs 20x."""
        line_values = intercept + slope * indices
        diffs = line_values - prices
        above = diffs >= 0
        # Time-weighted scoring
        score = (
            np.sum(diffs[above] * time_weights[above]) +
            np.sum(np.abs(diffs[~above]) * penalty * time_weights[~above])
        )
        avg_dist = float(np.mean(np.abs(diffs)))
        return score, avg_dist

    # Initialize from previous solution or horizontal line at max price
    if prev_slope is not None and prev_intercept is not None:
        # Adjust for 1-bar window shift
        current_slope = prev_slope
        current_intercept = prev_intercept + prev_slope
    else:
        current_slope = 0.0
        current_intercept = max_price

    best_score, best_avg_dist = evaluate(current_slope, current_intercept)
    best_slope = current_slope
    best_intercept = current_intercept

    # Pivot point: 1/3 from current bar (keeps recent data stable during rotation)
    pivot_idx = n - n // 3  # e.g., bar 400 out of 600

    # Initial step sizes
    shift_step = price_range * 0.02  # 2% of price range
    rotate_step = price_range / n * 0.2  # Slope change per bar

    for _ in range(iterations):
        improved = False

        # === SHIFT PHASE: try moving line up/down ===
        for direction in [-1, 1]:
            test_intercept = current_intercept + direction * shift_step
            score, avg_dist = evaluate(current_slope, test_intercept)
            if score < best_score:
                best_score = score
                best_slope = current_slope
                best_intercept = test_intercept
                best_avg_dist = avg_dist
                improved = True

        current_slope = best_slope
        current_intercept = best_intercept

        # === ROTATE PHASE: rotate around pivot point ===
        pivot_value = current_intercept + current_slope * pivot_idx

        for direction in [-1, 1]:
            test_slope = current_slope + direction * rotate_step
            # Line must pass through pivot point
            test_intercept = pivot_value - test_slope * pivot_idx
            score, avg_dist = evaluate(test_slope, test_intercept)
            if score < best_score:
                best_score = score
                best_slope = test_slope
                best_intercept = test_intercept
                best_avg_dist = avg_dist
                improved = True

        current_slope = best_slope
        current_intercept = best_intercept

        # Reduce step sizes for finer refinement
        shift_step *= 0.6
        rotate_step *= 0.6

        # Early exit if no improvement (converged)
        if not improved and _ > 2:
            break

    return best_slope, best_intercept, best_avg_dist


def find_optimal_support_line(
    prices: np.ndarray,
    penalty: float = 20.0,
    prev_slope: Optional[float] = None,
    prev_intercept: Optional[float] = None,
    iterations: int = 6,
) -> Tuple[float, float, float]:
    """
    Find optimal support line below price data using shift-rotate optimization.

    Returns: (slope, intercept, avg_distance)
    """
    n = len(prices)
    if n < 20:
        return 0.0, prices[-1] if n > 0 else 0.0, 0.0

    max_price = float(np.max(prices))
    min_price = float(np.min(prices))
    price_range = max_price - min_price

    if price_range < 1e-8:
        return 0.0, min_price, 0.0

    indices = np.arange(n)
    time_weights = np.linspace(0.3, 1.0, n)

    def evaluate(slope: float, intercept: float) -> Tuple[float, float]:
        """Score a line. Lower is better. Penalizes breakthroughs 20x."""
        line_values = intercept + slope * indices
        diffs = prices - line_values  # Inverted: price should be ABOVE support
        above = diffs >= 0
        score = (
            np.sum(diffs[above] * time_weights[above]) +
            np.sum(np.abs(diffs[~above]) * penalty * time_weights[~above])
        )
        avg_dist = float(np.mean(np.abs(diffs)))
        return score, avg_dist

    # Initialize
    if prev_slope is not None and prev_intercept is not None:
        current_slope = prev_slope
        current_intercept = prev_intercept + prev_slope
    else:
        current_slope = 0.0
        current_intercept = min_price

    best_score, best_avg_dist = evaluate(current_slope, current_intercept)
    best_slope = current_slope
    best_intercept = current_intercept

    pivot_idx = n - n // 3

    shift_step = price_range * 0.02
    rotate_step = price_range / n * 0.2

    for _ in range(iterations):
        improved = False

        # === SHIFT PHASE ===
        for direction in [-1, 1]:
            test_intercept = current_intercept + direction * shift_step
            score, avg_dist = evaluate(current_slope, test_intercept)
            if score < best_score:
                best_score = score
                best_slope = current_slope
                best_intercept = test_intercept
                best_avg_dist = avg_dist
                improved = True

        current_slope = best_slope
        current_intercept = best_intercept

        # === ROTATE PHASE ===
        pivot_value = current_intercept + current_slope * pivot_idx

        for direction in [-1, 1]:
            test_slope = current_slope + direction * rotate_step
            test_intercept = pivot_value - test_slope * pivot_idx
            score, avg_dist = evaluate(test_slope, test_intercept)
            if score < best_score:
                best_score = score
                best_slope = test_slope
                best_intercept = test_intercept
                best_avg_dist = avg_dist
                improved = True

        current_slope = best_slope
        current_intercept = best_intercept

        shift_step *= 0.6
        rotate_step *= 0.6

        if not improved and _ > 2:
            break

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
        price_min, price_max = prices.min(), prices.max()
        price_range = price_max - price_min

        # Find lines with warm-start
        r_slope, r_intercept, _ = find_optimal_resistance_line(
            prices, prev_slope=self._prev_r_slope, prev_intercept=self._prev_r_intercept
        )
        s_slope, s_intercept, _ = find_optimal_support_line(
            prices, prev_slope=self._prev_s_slope, prev_intercept=self._prev_s_intercept
        )

        # Extrapolate lines to current bar (last index in window)
        n = len(prices) - 1
        resistance_price = r_intercept + r_slope * n
        support_price = s_intercept + s_slope * n

        # SANITY CHECK: lines must be within reasonable bounds of price data
        # If not, clear cache and use simple fallbacks
        max_deviation = price_range * 2.0  # Allow up to 2x price range deviation
        r_sane = abs(resistance_price - price_max) < max_deviation
        s_sane = abs(support_price - price_min) < max_deviation

        if not r_sane or not s_sane:
            # Reset cache - warm-start drifted too far
            self._prev_r_slope = None
            self._prev_r_intercept = None
            self._prev_s_slope = None
            self._prev_s_intercept = None
            # Recompute with no warm-start
            if not r_sane:
                r_slope, r_intercept, _ = find_optimal_resistance_line(prices)
                resistance_price = r_intercept + r_slope * n
            if not s_sane:
                s_slope, s_intercept, _ = find_optimal_support_line(prices)
                support_price = s_intercept + s_slope * n

        # Cache for next call (only if sane)
        self._prev_r_slope = r_slope
        self._prev_r_intercept = r_intercept
        self._prev_s_slope = s_slope
        self._prev_s_intercept = s_intercept

        # Channel width
        channel_width = resistance_price - support_price
        if channel_width <= 0:
            self.last_channel_info = None
            return 0.0

        # Position in channel: 0 = at support, 1 = at resistance
        position = (current_price - support_price) / channel_width

        # Support line diagnostics
        support_line_vals = s_intercept + s_slope * np.arange(len(prices))
        s_breaks = int(np.sum(prices < support_line_vals))
        s_break_pct = s_breaks / len(prices) * 100

        # Resistance line diagnostics
        resistance_line_vals = r_intercept + r_slope * np.arange(len(prices))
        r_breaks = int(np.sum(prices > resistance_line_vals))
        r_break_pct = r_breaks / len(prices) * 100

        # Get timestamp of the last bar (for frontend line extrapolation)
        try:
            last_bar_time = int(bars.index[-1].timestamp() * 1000)  # ms since epoch
        except Exception:
            last_bar_time = None

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
            "resistance_breaks": r_breaks,
            "resistance_breaks_pct": round(r_break_pct, 1),
            "resistance_slope": round(r_slope, 6),
            "ref_timestamp": last_bar_time,  # When these values were computed
        }

        # Handle price outside channel bounds:
        # Below support (position < 0) → strong buy (+1)
        # Above resistance (position > 1) → strong sell (-1)
        if position < 0.0:
            return 1.0  # Below support = oversold = strong buy
        if position > 1.0:
            return -1.0  # Above resistance = overbought = strong sell

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
        price_min, price_max = prices.min(), prices.max()
        price_range = price_max - price_min

        r_slope, r_intercept, _ = find_optimal_resistance_line(
            prices, prev_slope=self._prev_r_slope, prev_intercept=self._prev_r_intercept
        )
        s_slope, s_intercept, _ = find_optimal_support_line(
            prices, prev_slope=self._prev_s_slope, prev_intercept=self._prev_s_intercept
        )

        # Extrapolate lines to current bar for sanity check
        n = len(prices) - 1
        resistance_price = r_intercept + r_slope * n
        support_price = s_intercept + s_slope * n

        # SANITY CHECK: lines must be within reasonable bounds
        max_deviation = price_range * 2.0
        r_sane = abs(resistance_price - price_max) < max_deviation
        s_sane = abs(support_price - price_min) < max_deviation

        if not r_sane or not s_sane:
            # Reset cache and recompute
            self._prev_r_slope = None
            self._prev_r_intercept = None
            self._prev_s_slope = None
            self._prev_s_intercept = None
            if not r_sane:
                r_slope, r_intercept, _ = find_optimal_resistance_line(prices)
            if not s_sane:
                s_slope, s_intercept, _ = find_optimal_support_line(prices)

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


class ChannelTrendSignal(BaseSignal):
    """
    Strong binary signal based on channel direction.

    Both support AND resistance rising → +1 (strong bullish)
    Both support AND resistance falling → -1 (strong bearish)
    Mixed directions → 0 (no clear trend)
    """

    name = "channel_trend"

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
        price_min, price_max = prices.min(), prices.max()
        price_range = price_max - price_min

        r_slope, r_intercept, _ = find_optimal_resistance_line(
            prices, prev_slope=self._prev_r_slope, prev_intercept=self._prev_r_intercept
        )
        s_slope, s_intercept, _ = find_optimal_support_line(
            prices, prev_slope=self._prev_s_slope, prev_intercept=self._prev_s_intercept
        )

        # Extrapolate lines to current bar for sanity check
        n = len(prices) - 1
        resistance_price = r_intercept + r_slope * n
        support_price = s_intercept + s_slope * n

        # SANITY CHECK: lines must be within reasonable bounds
        max_deviation = price_range * 2.0
        r_sane = abs(resistance_price - price_max) < max_deviation
        s_sane = abs(support_price - price_min) < max_deviation

        if not r_sane or not s_sane:
            self._prev_r_slope = None
            self._prev_r_intercept = None
            self._prev_s_slope = None
            self._prev_s_intercept = None
            if not r_sane:
                r_slope, r_intercept, _ = find_optimal_resistance_line(prices)
            if not s_sane:
                s_slope, s_intercept, _ = find_optimal_support_line(prices)

        # Cache for next call
        self._prev_r_slope = r_slope
        self._prev_r_intercept = r_intercept
        self._prev_s_slope = s_slope
        self._prev_s_intercept = s_intercept

        # Binary trend signal: both rising = +1, both falling = -1, mixed = 0
        if r_slope > 0 and s_slope > 0:
            return 1.0  # Strong bullish - rising channel
        elif r_slope < 0 and s_slope < 0:
            return -1.0  # Strong bearish - falling channel
        else:
            return 0.0  # Mixed - no clear trend
