def compute_score(signals: dict[str, float], weights: dict[str, float]) -> float:
    """Compute weighted sum of signals, normalized by sum of absolute weights."""
    total = sum(signals.get(k, 0.0) * w for k, w in weights.items())
    weight_sum = sum(abs(w) for w in weights.values())
    return total / weight_sum if weight_sum > 0 else 0.0


DEFAULT_WEIGHTS: dict[str, float] = {
    "momentum": 0.10,
    "rsi": 0.08,
    "bollinger": 0.08,
    "vwap": 0.06,
    "atr": 0.03,
    "volume": 0.05,
    "breakout": 0.05,
    "channel_position": 0.45,  # DOMINANT - buy near support, sell near resistance
    "channel_slope": 0.10,
}
