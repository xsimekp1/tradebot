"""
Market data fetching - uses Yahoo Finance for free historical data.
Trading execution still goes through the configured broker (IBKR/Alpaca).
"""
import asyncio
from datetime import datetime, timezone, timedelta

import pandas as pd
import httpx

from src.config import settings


def fetch_bars(symbol: str, limit: int = 100) -> pd.DataFrame:
    """Fetch the last `limit` 1-minute bars using Yahoo Finance (free)."""
    # For stocks, use Yahoo Finance
    if settings.ASSET_CLASS == "stock":
        df = _fetch_yahoo(symbol, limit)
        if not df.empty:
            return df

    # Fallback to broker for crypto/forex
    from src.engine.executor import _get_broker, _run_async
    broker = _get_broker()
    df = _run_async(broker.get_bars(symbol, "1m", limit))
    return _normalize(df, symbol, limit)


def _fetch_yahoo(symbol: str, limit: int) -> pd.DataFrame:
    """Fetch bars from Yahoo Finance (free, no API key needed)."""
    try:
        # Calculate time range - need more data for 1-min bars
        # Yahoo gives 1-day max for 1m interval, or 5-day for 5m
        # For limit=600 (10 hours), we need to use 5m bars or fetch multiple days

        if limit <= 390:  # ~6.5 hours, 1 trading day
            interval = "1m"
            range_str = "1d"
        else:
            # For more bars, use 2m interval and fetch more days
            interval = "2m"
            range_str = "5d"

        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        params = {
            "interval": interval,
            "range": range_str,
        }

        with httpx.Client(timeout=10) as client:
            resp = client.get(url, params=params, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            data = resp.json()

        result = data.get("chart", {}).get("result", [])
        if not result:
            return pd.DataFrame()

        quote = result[0].get("indicators", {}).get("quote", [{}])[0]
        timestamps = result[0].get("timestamp", [])

        if not timestamps:
            return pd.DataFrame()

        df = pd.DataFrame({
            "open": quote.get("open", []),
            "high": quote.get("high", []),
            "low": quote.get("low", []),
            "close": quote.get("close", []),
            "volume": quote.get("volume", []),
        }, index=pd.to_datetime(timestamps, unit="s", utc=True))

        # Remove NaN rows
        df = df.dropna()

        return df.tail(limit)

    except Exception as e:
        print(f"[data] Yahoo fetch error: {e}")
        return pd.DataFrame()


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
