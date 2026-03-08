"""
Alpaca broker implementation.
Wraps existing Alpaca functionality into the BaseBroker interface.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional
import pandas as pd

from src.brokers.base import (
    BaseBroker,
    AccountInfo,
    Position,
    PositionSide,
    Order,
    OrderSide,
    OrderType,
)
from src.config import settings


class AlpacaBroker(BaseBroker):
    """Alpaca broker implementation."""

    def __init__(self):
        self._trading_client = None
        self._data_client = None
        self._is_crypto = settings.ASSET_CLASS == "crypto"

    @property
    def name(self) -> str:
        return "Alpaca"

    def _get_trading_client(self):
        if self._trading_client is None:
            from alpaca.trading.client import TradingClient
            self._trading_client = TradingClient(
                api_key=settings.ALPACA_API_KEY,
                secret_key=settings.ALPACA_SECRET_KEY,
                paper=settings.ALPACA_PAPER,
            )
        return self._trading_client

    def _get_data_client(self):
        if self._data_client is None:
            if self._is_crypto:
                from alpaca.data.historical import CryptoHistoricalDataClient
                self._data_client = CryptoHistoricalDataClient(
                    api_key=settings.ALPACA_API_KEY,
                    secret_key=settings.ALPACA_SECRET_KEY,
                )
            else:
                from alpaca.data.historical import StockHistoricalDataClient
                self._data_client = StockHistoricalDataClient(
                    api_key=settings.ALPACA_API_KEY,
                    secret_key=settings.ALPACA_SECRET_KEY,
                )
        return self._data_client

    def normalize_symbol(self, symbol: str) -> str:
        """Alpaca uses symbols as-is (BTC/USD, AAPL, etc.)."""
        return symbol

    async def get_account(self) -> AccountInfo:
        client = self._get_trading_client()
        account = client.get_account()

        return AccountInfo(
            equity=float(account.equity),
            cash=float(account.cash),
            buying_power=float(account.buying_power),
            currency="USD",
        )

    async def get_position(self, symbol: str) -> Optional[Position]:
        client = self._get_trading_client()

        try:
            pos = client.get_open_position(symbol)
        except Exception:
            return None

        side = PositionSide.LONG if float(pos.qty) > 0 else PositionSide.SHORT

        return Position(
            symbol=pos.symbol,
            side=side,
            quantity=abs(float(pos.qty)),
            entry_price=float(pos.avg_entry_price),
            current_price=float(pos.current_price),
            unrealized_pnl=float(pos.unrealized_pl),
            market_value=abs(float(pos.market_value)),
        )

    async def get_positions(self) -> list[Position]:
        client = self._get_trading_client()
        positions = client.get_all_positions()

        result = []
        for pos in positions:
            side = PositionSide.LONG if float(pos.qty) > 0 else PositionSide.SHORT
            result.append(Position(
                symbol=pos.symbol,
                side=side,
                quantity=abs(float(pos.qty)),
                entry_price=float(pos.avg_entry_price),
                current_price=float(pos.current_price),
                unrealized_pnl=float(pos.unrealized_pl),
                market_value=abs(float(pos.market_value)),
            ))

        return result

    async def submit_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        order_type: OrderType = OrderType.MARKET,
        limit_price: Optional[float] = None,
    ) -> Order:
        from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest
        from alpaca.trading.enums import OrderSide as AlpacaSide, TimeInForce

        client = self._get_trading_client()

        alpaca_side = AlpacaSide.BUY if side == OrderSide.BUY else AlpacaSide.SELL

        if order_type == OrderType.MARKET:
            request = MarketOrderRequest(
                symbol=symbol,
                qty=quantity,
                side=alpaca_side,
                time_in_force=TimeInForce.GTC,
            )
        else:
            request = LimitOrderRequest(
                symbol=symbol,
                qty=quantity,
                side=alpaca_side,
                time_in_force=TimeInForce.GTC,
                limit_price=limit_price,
            )

        order = client.submit_order(request)

        return Order(
            id=str(order.id),
            symbol=order.symbol,
            side=side,
            quantity=float(order.qty) if order.qty else quantity,
            order_type=order_type,
            status=order.status.value,
            filled_price=float(order.filled_avg_price) if order.filled_avg_price else None,
            created_at=order.created_at,
        )

    async def close_position(self, symbol: str) -> Optional[Order]:
        client = self._get_trading_client()

        try:
            order = client.close_position(symbol)
        except Exception:
            return None

        return Order(
            id=str(order.id),
            symbol=order.symbol,
            side=OrderSide.SELL if order.side.value == "sell" else OrderSide.BUY,
            quantity=float(order.qty) if order.qty else 0,
            order_type=OrderType.MARKET,
            status=order.status.value,
            filled_price=float(order.filled_avg_price) if order.filled_avg_price else None,
            created_at=order.created_at,
        )

    async def get_bars(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 100,
    ) -> pd.DataFrame:
        from alpaca.data.timeframe import TimeFrame

        # Map timeframe string to Alpaca TimeFrame
        tf_map = {
            "1m": TimeFrame.Minute,
            "5m": TimeFrame(5, "Min"),
            "15m": TimeFrame(15, "Min"),
            "30m": TimeFrame(30, "Min"),
            "1h": TimeFrame.Hour,
            "4h": TimeFrame(4, "Hour"),
            "1d": TimeFrame.Day,
        }
        tf = tf_map.get(timeframe, TimeFrame.Minute)

        end = datetime.now(timezone.utc)
        # Estimate start time based on limit and timeframe
        if "m" in timeframe:
            minutes = int(timeframe.replace("m", ""))
            start = end - timedelta(minutes=minutes * limit * 2)
        elif "h" in timeframe:
            hours = int(timeframe.replace("h", ""))
            start = end - timedelta(hours=hours * limit * 2)
        else:
            start = end - timedelta(days=limit * 2)

        client = self._get_data_client()

        if self._is_crypto:
            from alpaca.data.requests import CryptoBarsRequest
            request = CryptoBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=tf,
                start=start,
                end=end,
            )
            bars = client.get_crypto_bars(request)
        else:
            from alpaca.data.requests import StockBarsRequest
            request = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=tf,
                start=start,
                end=end,
            )
            bars = client.get_stock_bars(request)

        df = bars.df
        if df.empty:
            return df

        if isinstance(df.index, pd.MultiIndex):
            df = df.xs(symbol, level=0)

        df = df.rename(columns=str.lower)
        cols = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
        df = df[cols].sort_index().tail(limit)

        return df

    async def get_current_price(self, symbol: str) -> float:
        client = self._get_data_client()

        if self._is_crypto:
            from alpaca.data.requests import CryptoLatestQuoteRequest
            request = CryptoLatestQuoteRequest(symbol_or_symbols=symbol)
            quotes = client.get_crypto_latest_quote(request)
        else:
            from alpaca.data.requests import StockLatestQuoteRequest
            request = StockLatestQuoteRequest(symbol_or_symbols=symbol)
            quotes = client.get_stock_latest_quote(request)

        quote = quotes[symbol]
        return (float(quote.bid_price) + float(quote.ask_price)) / 2
