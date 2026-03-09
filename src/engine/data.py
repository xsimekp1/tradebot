"""
Market data fetching through broker abstraction.
Supports Alpaca, OANDA, and IBKR brokers.
"""
import asyncio
from datetime import datetime, timezone, timedelta

import pandas as pd

from src.config import settings
from src.brokers import get_broker

# Global broker instance for data (lazy initialized)
_broker = None


def _get_broker():
    """Get or create broker instance based on settings."""
    global _broker
    if _broker is None:
        _broker = get_broker(settings.BROKER)
    return _broker


def _run_async(coro):
    """Run async coroutine from sync context."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


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
