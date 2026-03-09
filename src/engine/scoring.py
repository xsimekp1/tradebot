def compute_score(signals: dict[str, float], weights: dict[str, float]) -> float:
    """Compute weighted sum of signals, normalized by sum of absolute weights."""
    total = sum(signals.get(k, 0.0) * w for k, w in weights.items())
    weight_sum = sum(abs(w) for w in weights.values())
    return total / weight_sum if weight_sum > 0 else 0.0


DEFAULT_WEIGHTS: dict[str, float] = {
    "momentum": 0.08,
    "rsi": 0.06,
    "bollinger": 0.06,
    "vwap": 0.04,
    "atr": 0.02,
    "volume": 0.04,
    "breakout": 0.04,
    "channel_position": 0.40,  # DOMINANT - buy near support, sell near resistance
    "channel_slope": 0.06,
    "channel_trend": 0.20,    # STRONG - both lines rising = bullish, both falling = bearish
}
