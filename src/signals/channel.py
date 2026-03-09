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
    debug: bool = False,  # Enable to see optimization iterations
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
    # Time weights: 0.3 at start (old data) → 1 at end (recent data)
    # Old data still matters (30% weight) but recent data matters more
    time_weights = np.linspace(0.3, 1.0, n)

    def evaluate(slope: float, intercept: float) -> Tuple[float, float]:
        """Returns (score, avg_dist) for a given line. Time-weighted: recent bars matter more."""
        line_values = intercept + slope * indices
        diffs = line_values - prices
        positive = diffs >= 0
        # Apply time weights to distances
        weighted_above = diffs[positive] * time_weights[positive]
        weighted_below = np.abs(diffs[~positive]) * penalty * time_weights[~positive]
        score = np.sum(weighted_above) + np.sum(weighted_below)
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

        # Rotate around pivot at 1/3 from current bar (2/3 from start of window)
        # This avoids rotating around bar 0 (600 bars ago) where slope changes
        # cause huge shifts at the current bar.
        pivot_idx = n - n // 3
        pivot_val = adjusted_intercept + prev_slope * pivot_idx

        local_iterations = 0
        for slope_i in range(5):
            slope = prev_slope - local_slope_range + (2 * local_slope_range * slope_i / 4)
            for offset_i in range(5):
                offset = -local_offset_range + (2 * local_offset_range * offset_i / 4)
                # Anchor line at pivot point — different slopes pass through same region
                intercept = (pivot_val + offset) - slope * pivot_idx

                score, avg_dist = evaluate(slope, intercept)
                local_iterations += 1
                if score < best_score:
                    best_score = score
                    best_slope = slope
                    best_intercept = intercept
                    best_avg_dist = avg_dist

        # Sanity check: if resistance line is too far from price range, force full search
        best_line_at_end = best_intercept + best_slope * (n - 1)
        if best_score < float('inf') and abs(best_line_at_end - max_price) < price_range * 0.5:
            print(f"[channel-R] warm-start OK: {local_iterations} iters, line@end={best_line_at_end:.2f}, score={best_score:.1f}")
            return best_slope, best_intercept, best_avg_dist
        # Otherwise fall through to full grid search
        print(f"[channel-R] warm-start FAILED (line too far): {local_iterations} iters, line@end={best_line_at_end:.2f}, max_price={max_price:.2f}, falling back to full search")

    # Full grid search (15x15) - either first call or local search failed or drifted too far
    slope_range = price_range / n * 0.5

    if prev_slope is None:
        print(f"[channel-R] no warm-start (first call), running full 15x15 grid search")
    # else: fallback case already logged above

    if debug:
        print(f"[R-DEBUG] Grid search: price_range={price_range:.2f}, slope_range={slope_range:.6f}")
        print(f"[R-DEBUG] max_price={max_price:.2f} at idx={max_idx}, min_price={min_price:.2f}")

    for slope_i in range(15):
        slope = -slope_range + (2 * slope_range * slope_i / 14)
        base_intercept = max_price - slope * max_idx

        for offset_i in range(15):
            # Search from 0% to +10% around max price (resistance should be AT or slightly above highs)
            offset = price_range * 0.10 * offset_i / 14
            intercept = base_intercept + offset

            score, avg_dist = evaluate(slope, intercept)
            line_at_end = intercept + slope * (n - 1)

            if debug and offset_i == 7:  # Middle offset, show for each slope
                print(f"[R-DEBUG] slope[{slope_i}]={slope:.6f} offset={offset:.2f} line@end={line_at_end:.2f} score={score:.1f} avg_dist={avg_dist:.2f}")

            if score < best_score:
                best_score = score
                best_slope = slope
                best_intercept = intercept
                best_avg_dist = avg_dist
                if debug:
                    print(f"[R-DEBUG] >>> NEW BEST: score={score:.1f} line@end={line_at_end:.2f}")

    if debug:
        final_line = best_intercept + best_slope * (n - 1)
        print(f"[R-DEBUG] FINAL: slope={best_slope:.6f} intercept={best_intercept:.2f} line@end={final_line:.2f} score={best_score:.1f}")

    final_line = best_intercept + best_slope * (n - 1)
    print(f"[channel-R] full grid done: 225 iters, line@end={final_line:.2f}, score={best_score:.1f}")

    return best_slope, best_intercept, best_avg_dist


def find_optimal_support_line(
    prices: np.ndarray,
    penalty: float = 20.0,
    debug: bool = False,  # Enable to see optimization iterations
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
    # Time weights: 0.3 at start (old data) → 1 at end (recent data)
    # Old data still matters (30% weight) but recent data matters more
    time_weights = np.linspace(0.3, 1.0, n)

    def evaluate(slope: float, intercept: float) -> Tuple[float, float]:
        """Returns (score, avg_dist) for a given line. Time-weighted: recent bars matter more."""
        line_values = intercept + slope * indices
        diffs = prices - line_values  # Inverted: price above line is good
        positive = diffs >= 0
        # Apply time weights to distances
        weighted_above = diffs[positive] * time_weights[positive]
        weighted_below = np.abs(diffs[~positive]) * penalty * time_weights[~positive]
        score = np.sum(weighted_above) + np.sum(weighted_below)
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

        # Rotate around pivot at 1/3 from current bar (2/3 from start of window)
        pivot_idx = n - n // 3
        pivot_val = adjusted_intercept + prev_slope * pivot_idx

        local_iterations = 0
        for slope_i in range(5):
            slope = prev_slope - local_slope_range + (2 * local_slope_range * slope_i / 4)
            for offset_i in range(5):
                offset = -local_offset_range + (2 * local_offset_range * offset_i / 4)
                intercept = (pivot_val + offset) - slope * pivot_idx

                score, avg_dist = evaluate(slope, intercept)
                local_iterations += 1
                if score < best_score:
                    best_score = score
                    best_slope = slope
                    best_intercept = intercept
                    best_avg_dist = avg_dist

        # Sanity check: if support line is too far from price range, force full search
        best_line_at_end = best_intercept + best_slope * (n - 1)
        if best_score < float('inf') and abs(best_line_at_end - min_price) < price_range * 0.5:
            print(f"[channel-S] warm-start OK: {local_iterations} iters, line@end={best_line_at_end:.2f}, score={best_score:.1f}")
            return best_slope, best_intercept, best_avg_dist
        # Otherwise fall through to full grid search
        print(f"[channel-S] warm-start FAILED (line too far): {local_iterations} iters, line@end={best_line_at_end:.2f}, min_price={min_price:.2f}, falling back to full search")

    # Full grid search (15x15) - either first call or local search failed or drifted too far
    slope_range = price_range / n * 0.5

    if prev_slope is None:
        print(f"[channel-S] no warm-start (first call), running full 15x15 grid search")
    # else: fallback case already logged above

    if debug:
        print(f"[S-DEBUG] Grid search: price_range={price_range:.2f}, slope_range={slope_range:.6f}")
        print(f"[S-DEBUG] min_price={min_price:.2f} at idx={min_idx}, max_price={max_price:.2f}")

    for slope_i in range(15):
        slope = -slope_range + (2 * slope_range * slope_i / 14)
        base_intercept = min_price - slope * min_idx

        for offset_i in range(15):
            # Search from -10% to 0% around min price (support should be AT or slightly below lows)
            offset = -price_range * 0.10 + (price_range * 0.10 * offset_i / 14)
            intercept = base_intercept + offset

            score, avg_dist = evaluate(slope, intercept)
            line_at_end = intercept + slope * (n - 1)

            if debug and offset_i == 7:  # Middle offset, show for each slope
                print(f"[S-DEBUG] slope[{slope_i}]={slope:.6f} offset={offset:.2f} line@end={line_at_end:.2f} score={score:.1f} avg_dist={avg_dist:.2f}")

            if score < best_score:
                best_score = score
                best_slope = slope
                best_intercept = intercept
                best_avg_dist = avg_dist
                if debug:
                    print(f"[S-DEBUG] >>> NEW BEST: score={score:.1f} line@end={line_at_end:.2f}")

    if debug:
        final_line = best_intercept + best_slope * (n - 1)
        print(f"[S-DEBUG] FINAL: slope={best_slope:.6f} intercept={best_intercept:.2f} line@end={final_line:.2f} score={best_score:.1f}")

    final_line = best_intercept + best_slope * (n - 1)
    print(f"[channel-S] full grid done: 225 iters, line@end={final_line:.2f}, score={best_score:.1f}")

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
            # Reset cache - something went wrong
            print(f"[channel] SANITY FAIL: r_sane={r_sane}, s_sane={s_sane}, R={resistance_price:.2f} vs max={price_max:.2f}, S={support_price:.2f} vs min={price_min:.2f}")
            self._prev_r_slope = None
            self._prev_r_intercept = None
            self._prev_s_slope = None
            self._prev_s_intercept = None
            # Recompute with no warm-start
            if not r_sane:
                print(f"[channel] Recomputing resistance (full search due to sanity fail)")
                r_slope, r_intercept, _ = find_optimal_resistance_line(prices)
                resistance_price = r_intercept + r_slope * n
            if not s_sane:
                print(f"[channel] Recomputing support (full search due to sanity fail)")
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

        # If price is outside channel bounds, signal is unreliable — return neutral
        if position < 0.0 or position > 1.0:
            self.last_channel_info = None
            return 0.0

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
