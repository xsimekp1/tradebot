"""
Market data fetching through broker abstraction.
Supports Alpaca, OANDA, and IBKR brokers.
"""
import asyncio
from datetime import datetime, timezone, timedelta

import pandas as pd

from src.config import settings
# Use shared broker instance from executor to avoid multiple connections
from src.engine.executor import _get_broker, _run_async


def fetch_bars(symbol: str, limit: int = 100) -> pd.DataFrame:
    """Fetch the last `limit` 1-minute bars using configured broker."""
    broker = _get_broker()
    df = _run_async(broker.get_bars(symbol, "1m", limit))
    return _normalize(df, symbol, limit)


def _normalize(df: pd.DataFrame, symbol: str, limit: int) -> pd.DataFrame:
    """Normalize DataFrame to standard format."""
    if df is None or df.empty:
        return pd.DataFrame()
    if isinstance(df.index, pd.MultiIndex):
        df = df.xs(symbol, level=0)
    df = df.rename(columns=str.lower)
    available = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
    df = df[available].copy()
    df = df.sort_index()
    return df.tail(limit)
