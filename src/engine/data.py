from datetime import datetime, timezone, timedelta

import pandas as pd

from src.config import settings


def fetch_bars(symbol: str, limit: int = 100) -> pd.DataFrame:
    """Fetch the last `limit` 1-minute bars. Auto-detects stock vs crypto."""
    if settings.ASSET_CLASS == "crypto":
        return _fetch_crypto_bars(symbol, limit)
    return _fetch_stock_bars(symbol, limit)


def _fetch_stock_bars(symbol: str, limit: int) -> pd.DataFrame:
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    client = StockHistoricalDataClient(
        api_key=settings.ALPACA_API_KEY,
        secret_key=settings.ALPACA_SECRET_KEY,
    )
    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=limit * 2)

    req = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Minute,
        start=start,
        end=end,
        limit=limit,
        feed="iex",
    )
    bars = client.get_stock_bars(req)
    return _normalize(bars.df, symbol, limit)


def _fetch_crypto_bars(symbol: str, limit: int) -> pd.DataFrame:
    from alpaca.data.historical import CryptoHistoricalDataClient
    from alpaca.data.requests import CryptoBarsRequest
    from alpaca.data.timeframe import TimeFrame

    client = CryptoHistoricalDataClient(
        api_key=settings.ALPACA_API_KEY,
        secret_key=settings.ALPACA_SECRET_KEY,
    )
    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=limit + 10)  # crypto has no gaps

    req = CryptoBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Minute,
        start=start,
        end=end,
        limit=limit,
    )
    bars = client.get_crypto_bars(req)
    return _normalize(bars.df, symbol, limit)


def _normalize(df: pd.DataFrame, symbol: str, limit: int) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    if isinstance(df.index, pd.MultiIndex):
        df = df.xs(symbol, level=0)
    df = df.rename(columns=str.lower)
    available = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
    df = df[available].copy()
    df = df.sort_index()
    return df.tail(limit)
