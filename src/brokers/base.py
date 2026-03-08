"""
Abstract base class for broker implementations.
Allows the trading bot to work with multiple brokers (Alpaca, OANDA, etc.)
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional
import pandas as pd


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"


class PositionSide(Enum):
    LONG = "long"
    SHORT = "short"


@dataclass
class Position:
    symbol: str
    side: PositionSide
    quantity: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    market_value: float


@dataclass
class Order:
    id: str
    symbol: str
    side: OrderSide
    quantity: float
    order_type: OrderType
    status: str
    filled_price: Optional[float] = None
    created_at: Optional[datetime] = None


@dataclass
class AccountInfo:
    equity: float
    cash: float
    buying_power: float
    currency: str


class BaseBroker(ABC):
    """Abstract base class for broker implementations."""

    @abstractmethod
    async def get_account(self) -> AccountInfo:
        """Get account information (equity, cash, buying power)."""
        pass

    @abstractmethod
    async def get_position(self, symbol: str) -> Optional[Position]:
        """Get current position for a symbol, or None if no position."""
        pass

    @abstractmethod
    async def get_positions(self) -> list[Position]:
        """Get all open positions."""
        pass

    @abstractmethod
    async def submit_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        order_type: OrderType = OrderType.MARKET,
        limit_price: Optional[float] = None,
    ) -> Order:
        """Submit an order. Returns the order object."""
        pass

    @abstractmethod
    async def close_position(self, symbol: str) -> Optional[Order]:
        """Close entire position for a symbol. Returns the closing order."""
        pass

    @abstractmethod
    async def get_bars(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 100,
    ) -> pd.DataFrame:
        """
        Get historical OHLCV bars.

        Args:
            symbol: The instrument symbol
            timeframe: Bar timeframe (e.g., "1m", "5m", "1h", "1d")
            limit: Number of bars to fetch

        Returns:
            DataFrame with columns: open, high, low, close, volume
            Index is datetime
        """
        pass

    @abstractmethod
    async def get_current_price(self, symbol: str) -> float:
        """Get current bid/ask midpoint price for a symbol."""
        pass

    @abstractmethod
    def normalize_symbol(self, symbol: str) -> str:
        """
        Normalize symbol to broker's format.
        E.g., "EUR/USD" -> "EUR_USD" for OANDA
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Broker name for logging."""
        pass
