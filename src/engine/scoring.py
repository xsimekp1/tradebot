def compute_score(signals: dict[str, float], weights: dict[str, float]) -> float:
    """Compute weighted sum of signals, normalized by sum of absolute weights."""
    total = sum(signals.get(k, 0.0) * w for k, w in weights.items())
    weight_sum = sum(abs(w) for w in weights.values())
    return total / weight_sum if weight_sum > 0 else 0.0


DEFAULT_WEIGHTS: dict[str, float] = {
    "momentum": 0.20,
    "rsi": 0.15,
    "bollinger": 0.12,
    "vwap": 0.12,
    "atr": 0.05,
    "volume": 0.08,
    "breakout": 0.08,
    "channel_position": 0.12,
    "channel_slope": 0.08,
}
