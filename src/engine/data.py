from datetime import datetime, timezone, timedelta

import pandas as pd
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

from src.config import settings


def get_data_client() -> StockHistoricalDataClient:
    return StockHistoricalDataClient(
        api_key=settings.ALPACA_API_KEY,
        secret_key=settings.ALPACA_SECRET_KEY,
    )


def fetch_bars(symbol: str, limit: int = 100) -> pd.DataFrame:
    """Fetch the last `limit` 1-minute bars for a symbol."""
    client = get_data_client()

    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=limit * 2)  # extra buffer for market hours

    request = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Minute,
        start=start,
        end=end,
        limit=limit,
        feed="iex",  # use IEX for paper trading (no SIP subscription required)
    )

    bars = client.get_stock_bars(request)
    df = bars.df

    if df.empty:
        return pd.DataFrame()

    # Flatten multi-index if needed
    if isinstance(df.index, pd.MultiIndex):
        df = df.xs(symbol, level=0)

    df = df.rename(columns=str.lower)
    df = df[["open", "high", "low", "close", "volume"]].copy()
    df = df.sort_index()
    return df.tail(limit)
