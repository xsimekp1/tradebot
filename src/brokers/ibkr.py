"""
Interactive Brokers broker implementation using ib_insync.
Requires IB Gateway or TWS running locally.
"""
from datetime import datetime, timedelta
from typing import Optional
import asyncio
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


class IBKRBroker(BaseBroker):
    """Interactive Brokers implementation using ib_insync."""

    def __init__(self):
        self._ib = None
        self._connected = False

    @property
    def name(self) -> str:
        return "IBKR"

    def _get_ib(self):
        """Get or create IB connection."""
        if self._ib is None:
            from ib_insync import IB
            self._ib = IB()

        if not self._ib.isConnected():
            self._ib.connect(
                host=settings.IBKR_HOST,
                port=settings.IBKR_PORT,
                clientId=settings.IBKR_CLIENT_ID,
            )
            self._connected = True

        return self._ib

    def disconnect(self):
        """Disconnect from IB Gateway."""
        if self._ib and self._ib.isConnected():
            self._ib.disconnect()
            self._connected = False

    def normalize_symbol(self, symbol: str) -> str:
        """
        IBKR uses specific contract formats.
        For crypto: symbol like 'BTC' with exchange 'PAXOS'
        For stocks: symbol like 'AAPL' with exchange 'SMART'
        """
        # Remove /USD suffix for crypto if present
        if "/" in symbol:
            return symbol.split("/")[0]
        return symbol

    def _make_contract(self, symbol: str):
        """Create an IB contract for the symbol."""
        from ib_insync import Stock, Crypto, Forex

        base_symbol = self.normalize_symbol(symbol)

        # Detect asset type
        if "/" in symbol:
            parts = symbol.split("/")
            # Forex pair like EUR/USD
            if len(parts) == 2 and len(parts[0]) == 3 and len(parts[1]) == 3:
                # Check if it's crypto (BTC, ETH, etc.) or forex
                crypto_symbols = ["BTC", "ETH", "LTC", "BCH", "XRP", "SOL", "ADA", "DOT"]
                if parts[0] in crypto_symbols:
                    # Crypto contract
                    return Crypto(parts[0], "PAXOS", parts[1])
                else:
                    # Forex contract - IDEALPRO is the ECN for forex
                    return Forex(pair=symbol.replace("/", ""))
        elif base_symbol in ["BTC", "ETH", "LTC", "BCH", "XRP", "SOL"]:
            # Crypto without slash
            return Crypto(base_symbol, "PAXOS", "USD")
        else:
            # Stock contract
            return Stock(base_symbol, "SMART", "USD")

    async def get_account(self) -> AccountInfo:
        ib = self._get_ib()

        # Request account summary
        account_values = ib.accountSummary()

        equity = 0.0
        cash = 0.0
        buying_power = 0.0
        currency = "USD"

        for av in account_values:
            if av.tag == "NetLiquidation":
                equity = float(av.value)
                currency = av.currency
            elif av.tag == "TotalCashValue":
                cash = float(av.value)
            elif av.tag == "BuyingPower":
                buying_power = float(av.value)

        return AccountInfo(
            equity=equity,
            cash=cash,
            buying_power=buying_power,
            currency=currency,
        )

    async def get_position(self, symbol: str) -> Optional[Position]:
        ib = self._get_ib()
        positions = ib.positions()

        base_symbol = self.normalize_symbol(symbol)

        for pos in positions:
            if pos.contract.symbol == base_symbol:
                # Get current price
                contract = self._make_contract(symbol)
                ib.qualifyContracts(contract)
                ticker = ib.reqMktData(contract, "", False, False)
                await asyncio.sleep(0.5)  # Wait for data

                current_price = ticker.marketPrice()
                if current_price != current_price:  # NaN check
                    current_price = ticker.close or pos.avgCost

                ib.cancelMktData(contract)

                qty = float(pos.position)
                side = PositionSide.LONG if qty > 0 else PositionSide.SHORT
                entry_price = float(pos.avgCost)
                unrealized_pnl = (current_price - entry_price) * qty

                return Position(
                    symbol=symbol,
                    side=side,
                    quantity=abs(qty),
                    entry_price=entry_price,
                    current_price=current_price,
                    unrealized_pnl=unrealized_pnl,
                    market_value=abs(qty * current_price),
                )

        return None

    async def get_positions(self) -> list[Position]:
        ib = self._get_ib()
        positions = ib.positions()
        result = []

        for pos in positions:
            qty = float(pos.position)
            if qty == 0:
                continue

            side = PositionSide.LONG if qty > 0 else PositionSide.SHORT
            entry_price = float(pos.avgCost)
            symbol = pos.contract.symbol

            # For simplicity, use entry price as current price
            # (would need market data subscription for real-time)
            current_price = entry_price

            result.append(Position(
                symbol=symbol,
                side=side,
                quantity=abs(qty),
                entry_price=entry_price,
                current_price=current_price,
                unrealized_pnl=0.0,
                market_value=abs(qty * current_price),
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
        from ib_insync import MarketOrder, LimitOrder

        ib = self._get_ib()
        contract = self._make_contract(symbol)
        ib.qualifyContracts(contract)

        action = "BUY" if side == OrderSide.BUY else "SELL"

        if order_type == OrderType.MARKET:
            ib_order = MarketOrder(action, quantity)
        else:
            ib_order = LimitOrder(action, quantity, limit_price)

        trade = ib.placeOrder(contract, ib_order)

        # Wait a bit for order to be acknowledged
        await asyncio.sleep(0.5)

        return Order(
            id=str(trade.order.orderId),
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type=order_type,
            status=trade.orderStatus.status,
            filled_price=trade.orderStatus.avgFillPrice if trade.orderStatus.avgFillPrice else None,
            created_at=datetime.now(),
        )

    async def close_position(self, symbol: str) -> Optional[Order]:
        position = await self.get_position(symbol)
        if position is None:
            return None

        # Close by submitting opposite order
        close_side = OrderSide.SELL if position.side == PositionSide.LONG else OrderSide.BUY

        return await self.submit_order(
            symbol=symbol,
            side=close_side,
            quantity=position.quantity,
            order_type=OrderType.MARKET,
        )

    async def get_bars(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 100,
    ) -> pd.DataFrame:
        ib = self._get_ib()
        contract = self._make_contract(symbol)
        ib.qualifyContracts(contract)

        # Map timeframe to IB duration and bar size
        tf_map = {
            "1m": ("1 min", "1 D"),
            "5m": ("5 mins", "5 D"),
            "15m": ("15 mins", "10 D"),
            "30m": ("30 mins", "20 D"),
            "1h": ("1 hour", "30 D"),
            "4h": ("4 hours", "60 D"),
            "1d": ("1 day", "365 D"),
        }

        bar_size, duration = tf_map.get(timeframe, ("1 min", "1 D"))

        # Adjust duration based on limit
        if timeframe == "1m":
            # IB returns max ~1 day of 1-min bars per request
            # For 600 bars, we need about 10 hours of data
            duration = f"{max(1, limit // 60)} D"

        # Determine data type based on asset
        # MIDPOINT for forex, TRADES for stocks, AGGTRADES for crypto
        if any(fx in symbol.upper() for fx in ["EUR", "GBP", "JPY", "CHF", "AUD", "CAD", "NZD"]):
            what_to_show = "MIDPOINT"  # Forex uses midpoint
        elif any(c in symbol.upper() for c in ["BTC", "ETH", "LTC"]):
            what_to_show = "AGGTRADES"  # Crypto
        else:
            what_to_show = "TRADES"  # Stocks

        bars = ib.reqHistoricalData(
            contract,
            endDateTime="",
            durationStr=duration,
            barSizeSetting=bar_size,
            whatToShow=what_to_show,
            useRTH=False,
            formatDate=1,
        )

        if not bars:
            return pd.DataFrame()

        # Convert to DataFrame
        data = []
        for bar in bars:
            data.append({
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
            })

        df = pd.DataFrame(data)
        df.index = pd.DatetimeIndex([bar.date for bar in bars])
        df = df.sort_index().tail(limit)

        return df

    async def get_current_price(self, symbol: str) -> float:
        ib = self._get_ib()
        contract = self._make_contract(symbol)
        ib.qualifyContracts(contract)

        ticker = ib.reqMktData(contract, "", False, False)

        # Wait for data
        for _ in range(10):
            await asyncio.sleep(0.1)
            if ticker.marketPrice() == ticker.marketPrice():  # Not NaN
                break

        price = ticker.marketPrice()
        ib.cancelMktData(contract)

        # Fallback to last close if no live price
        if price != price:  # NaN check
            bars = await self.get_bars(symbol, "1m", limit=1)
            if not bars.empty:
                price = bars["close"].iloc[-1]
            else:
                price = 0.0

        return float(price)
