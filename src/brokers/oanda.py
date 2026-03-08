"""
OANDA broker implementation using REST API v20.
"""
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional
import pandas as pd
import httpx

from src.brokers.base import (
    BaseBroker,
    AccountInfo,
    Position,
    PositionSide,
    Order,
    OrderSide,
    OrderType,
)


class OandaBroker(BaseBroker):
    """OANDA REST API v20 broker implementation."""

    # Timeframe mapping: our format -> OANDA granularity
    TIMEFRAME_MAP = {
        "1m": "M1",
        "5m": "M5",
        "15m": "M15",
        "30m": "M30",
        "1h": "H1",
        "4h": "H4",
        "1d": "D",
    }

    def __init__(
        self,
        api_key: str,
        account_id: str,
        practice: bool = True,
    ):
        self.api_key = api_key
        self.account_id = account_id
        self.practice = practice

        # Base URLs
        if practice:
            self.base_url = "https://api-fxpractice.oanda.com"
            self.stream_url = "https://stream-fxpractice.oanda.com"
        else:
            self.base_url = "https://api-fxtrade.oanda.com"
            self.stream_url = "https://stream-fxtrade.oanda.com"

        self._client: Optional[httpx.AsyncClient] = None

    @property
    def name(self) -> str:
        return "OANDA"

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def normalize_symbol(self, symbol: str) -> str:
        """Convert EUR/USD -> EUR_USD for OANDA."""
        return symbol.replace("/", "_")

    def _denormalize_symbol(self, symbol: str) -> str:
        """Convert EUR_USD -> EUR/USD for display."""
        return symbol.replace("_", "/")

    async def get_account(self) -> AccountInfo:
        client = await self._get_client()
        resp = await client.get(f"/v3/accounts/{self.account_id}/summary")
        resp.raise_for_status()
        data = resp.json()["account"]

        return AccountInfo(
            equity=float(data["NAV"]),
            cash=float(data["balance"]),
            buying_power=float(data["marginAvailable"]),
            currency=data["currency"],
        )

    async def get_position(self, symbol: str) -> Optional[Position]:
        instrument = self.normalize_symbol(symbol)
        client = await self._get_client()

        try:
            resp = await client.get(
                f"/v3/accounts/{self.account_id}/positions/{instrument}"
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
        except httpx.HTTPStatusError:
            return None

        data = resp.json()["position"]
        long_units = float(data["long"]["units"])
        short_units = float(data["short"]["units"])

        if long_units == 0 and short_units == 0:
            return None

        if long_units > 0:
            side = PositionSide.LONG
            quantity = long_units
            entry_price = float(data["long"]["averagePrice"])
            unrealized_pnl = float(data["long"]["unrealizedPL"])
        else:
            side = PositionSide.SHORT
            quantity = abs(short_units)
            entry_price = float(data["short"]["averagePrice"])
            unrealized_pnl = float(data["short"]["unrealizedPL"])

        current_price = await self.get_current_price(symbol)

        return Position(
            symbol=self._denormalize_symbol(instrument),
            side=side,
            quantity=quantity,
            entry_price=entry_price,
            current_price=current_price,
            unrealized_pnl=unrealized_pnl,
            market_value=quantity * current_price,
        )

    async def get_positions(self) -> list[Position]:
        client = await self._get_client()
        resp = await client.get(f"/v3/accounts/{self.account_id}/openPositions")
        resp.raise_for_status()

        positions = []
        for pos_data in resp.json()["positions"]:
            instrument = pos_data["instrument"]
            long_units = float(pos_data["long"]["units"])
            short_units = float(pos_data["short"]["units"])

            if long_units > 0:
                current_price = await self.get_current_price(instrument)
                positions.append(Position(
                    symbol=self._denormalize_symbol(instrument),
                    side=PositionSide.LONG,
                    quantity=long_units,
                    entry_price=float(pos_data["long"]["averagePrice"]),
                    current_price=current_price,
                    unrealized_pnl=float(pos_data["long"]["unrealizedPL"]),
                    market_value=long_units * current_price,
                ))
            if short_units < 0:
                current_price = await self.get_current_price(instrument)
                positions.append(Position(
                    symbol=self._denormalize_symbol(instrument),
                    side=PositionSide.SHORT,
                    quantity=abs(short_units),
                    entry_price=float(pos_data["short"]["averagePrice"]),
                    current_price=current_price,
                    unrealized_pnl=float(pos_data["short"]["unrealizedPL"]),
                    market_value=abs(short_units) * current_price,
                ))

        return positions

    async def submit_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        order_type: OrderType = OrderType.MARKET,
        limit_price: Optional[float] = None,
    ) -> Order:
        client = await self._get_client()
        instrument = self.normalize_symbol(symbol)

        # OANDA uses positive for buy, negative for sell
        units = quantity if side == OrderSide.BUY else -quantity

        order_data = {
            "order": {
                "instrument": instrument,
                "units": str(int(units)),  # OANDA wants string
                "type": "MARKET" if order_type == OrderType.MARKET else "LIMIT",
                "timeInForce": "FOK" if order_type == OrderType.MARKET else "GTC",
                "positionFill": "DEFAULT",
            }
        }

        if order_type == OrderType.LIMIT and limit_price:
            order_data["order"]["price"] = str(limit_price)

        resp = await client.post(
            f"/v3/accounts/{self.account_id}/orders",
            json=order_data,
        )
        resp.raise_for_status()
        data = resp.json()

        # Check if order was filled immediately (market order)
        if "orderFillTransaction" in data:
            fill = data["orderFillTransaction"]
            return Order(
                id=fill["id"],
                symbol=self._denormalize_symbol(instrument),
                side=side,
                quantity=abs(float(fill["units"])),
                order_type=order_type,
                status="filled",
                filled_price=float(fill["price"]),
                created_at=datetime.fromisoformat(fill["time"].replace("Z", "+00:00")),
            )
        elif "orderCreateTransaction" in data:
            create = data["orderCreateTransaction"]
            return Order(
                id=create["id"],
                symbol=self._denormalize_symbol(instrument),
                side=side,
                quantity=quantity,
                order_type=order_type,
                status="pending",
                created_at=datetime.fromisoformat(create["time"].replace("Z", "+00:00")),
            )
        else:
            raise RuntimeError(f"Unexpected order response: {data}")

    async def close_position(self, symbol: str) -> Optional[Order]:
        instrument = self.normalize_symbol(symbol)
        client = await self._get_client()

        # Close all units
        resp = await client.put(
            f"/v3/accounts/{self.account_id}/positions/{instrument}/close",
            json={"longUnits": "ALL", "shortUnits": "ALL"},
        )

        if resp.status_code == 404:
            return None

        resp.raise_for_status()
        data = resp.json()

        # Get the close transaction
        if "longOrderFillTransaction" in data:
            fill = data["longOrderFillTransaction"]
        elif "shortOrderFillTransaction" in data:
            fill = data["shortOrderFillTransaction"]
        else:
            return None

        units = float(fill["units"])
        return Order(
            id=fill["id"],
            symbol=self._denormalize_symbol(instrument),
            side=OrderSide.SELL if units < 0 else OrderSide.BUY,
            quantity=abs(units),
            order_type=OrderType.MARKET,
            status="filled",
            filled_price=float(fill["price"]),
            created_at=datetime.fromisoformat(fill["time"].replace("Z", "+00:00")),
        )

    async def get_bars(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 100,
    ) -> pd.DataFrame:
        client = await self._get_client()
        instrument = self.normalize_symbol(symbol)
        granularity = self.TIMEFRAME_MAP.get(timeframe, "M1")

        resp = await client.get(
            f"/v3/instruments/{instrument}/candles",
            params={
                "granularity": granularity,
                "count": limit,
                "price": "M",  # Midpoint prices
            },
        )
        resp.raise_for_status()
        data = resp.json()

        rows = []
        for candle in data["candles"]:
            if candle["complete"]:
                mid = candle["mid"]
                rows.append({
                    "timestamp": datetime.fromisoformat(candle["time"].replace("Z", "+00:00")),
                    "open": float(mid["o"]),
                    "high": float(mid["h"]),
                    "low": float(mid["l"]),
                    "close": float(mid["c"]),
                    "volume": int(candle["volume"]),
                })

        df = pd.DataFrame(rows)
        if not df.empty:
            df.set_index("timestamp", inplace=True)
        return df

    async def get_current_price(self, symbol: str) -> float:
        client = await self._get_client()
        instrument = self.normalize_symbol(symbol)

        resp = await client.get(
            f"/v3/accounts/{self.account_id}/pricing",
            params={"instruments": instrument},
        )
        resp.raise_for_status()
        data = resp.json()

        if not data["prices"]:
            raise RuntimeError(f"No price data for {symbol}")

        price_data = data["prices"][0]
        bid = float(price_data["bids"][0]["price"])
        ask = float(price_data["asks"][0]["price"])
        return (bid + ask) / 2
