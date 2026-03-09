"""
Trade executor - handles position management through broker abstraction.
Supports Alpaca, OANDA, and IBKR brokers.
"""
import asyncio

# Apply nest_asyncio early to allow nested event loops (needed for ib_insync)
import nest_asyncio
nest_asyncio.apply()

from src.config import settings
from src.brokers import get_broker, OrderSide, OrderType

# Global broker instance (lazy initialized)
_broker = None


def _get_broker():
    """Get or create broker instance based on settings."""
    global _broker
    if _broker is None:
        _broker = get_broker(settings.BROKER)
        print(f"[executor] Using broker: {_broker.name}")
    return _broker


def _run_async(coro):
    """Run async coroutine - works both inside and outside async context."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None:
        # Already in an async context - use nest_asyncio to run nested
        return asyncio.get_event_loop().run_until_complete(coro)
    else:
        # No running loop - create one
        return asyncio.run(coro)


def _get_price_yahoo(symbol: str) -> float:
    """Get current price from Yahoo Finance (fallback when broker fails)."""
    import httpx
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        with httpx.Client(timeout=5) as client:
            resp = client.get(url, params={"interval": "1m", "range": "1d"},
                            headers={"User-Agent": "Mozilla/5.0"})
            data = resp.json()
        result = data.get("chart", {}).get("result", [])
        if result:
            meta = result[0].get("meta", {})
            return float(meta.get("regularMarketPrice", 0))
    except Exception as e:
        print(f"[executor] Yahoo price fallback failed: {e}")
    return 0.0


def _get_current_price(symbol: str) -> float:
    """Get current price - tries broker first, falls back to Yahoo."""
    broker = _get_broker()
    try:
        price = _run_async(broker.get_current_price(symbol))
        if price > 0:
            return price
    except Exception:
        pass
    # Fallback to Yahoo for stocks
    if settings.ASSET_CLASS == "stock":
        return _get_price_yahoo(symbol)
    return 0.0


def get_current_position(symbol: str) -> dict | None:
    """Returns position dict with keys: side, qty, avg_entry_price. None if no position."""
    broker = _get_broker()
    position = _run_async(broker.get_position(symbol))

    if position is None:
        return None

    return {
        "side": position.side.value,
        "qty": position.quantity,
        "avg_entry_price": position.entry_price,
    }


def close_position(symbol: str) -> str | None:
    """Close any existing position for symbol. Returns order ID or None."""
    broker = _get_broker()
    order = _run_async(broker.close_position(symbol))

    if order is None:
        return None

    print(f"[executor] close_position({symbol}) ok")
    return order.id


def open_long(symbol: str, score: float, notional: float | None = None) -> str | None:
    """Open a long (buy) position. Returns order ID or None."""
    broker = _get_broker()

    try:
        # Calculate quantity from notional
        notional_value = notional or settings.POSITION_SIZE_USD
        current_price = _get_current_price(symbol)

        if current_price <= 0:
            print(f"[executor] open_long failed: invalid price {current_price}")
            return None

        quantity = notional_value / current_price

        # For crypto, allow fractional; for stocks, round to whole shares
        if settings.ASSET_CLASS != "crypto":
            quantity = int(quantity)
            if quantity < 1:
                print(f"[executor] open_long failed: notional ${notional_value} < 1 share at ${current_price}")
                return None

        order = _run_async(broker.submit_order(
            symbol=symbol,
            side=OrderSide.BUY,
            quantity=quantity,
            order_type=OrderType.MARKET,
        ))

        print(f"[executor] open_long({symbol}, qty={quantity}) ok")
        return order.id

    except Exception as e:
        print(f"[executor] open_long failed: {e}")
        return None


def open_short(symbol: str, score: float, notional: float | None = None) -> str | None:
    """Open a short (sell) position. Returns order ID or None."""
    broker = _get_broker()

    try:
        # Calculate quantity from notional
        notional_value = notional or settings.POSITION_SIZE_USD
        current_price = _get_current_price(symbol)

        if current_price <= 0:
            print(f"[executor] open_short failed: invalid price {current_price}")
            return None

        quantity = notional_value / current_price

        # For crypto, allow fractional; for stocks, round to whole shares
        if settings.ASSET_CLASS != "crypto":
            quantity = int(quantity)
            if quantity < 1:
                print(f"[executor] open_short failed: notional ${notional_value} < 1 share at ${current_price}")
                return None

        order = _run_async(broker.submit_order(
            symbol=symbol,
            side=OrderSide.SELL,
            quantity=quantity,
            order_type=OrderType.MARKET,
        ))

        print(f"[executor] open_short({symbol}, qty={quantity}) ok")
        return order.id

    except Exception as e:
        print(f"[executor] open_short failed: {e}")
        return None


def get_account() -> dict:
    """Returns account equity, cash, buying power."""
    broker = _get_broker()
    account = _run_async(broker.get_account())

    return {
        "equity": account.equity,
        "cash": account.cash,
        "portfolio_value": account.equity,  # For compatibility
        "last_equity": account.equity,  # For compatibility
        "buying_power": account.buying_power,
        "currency": account.currency,
    }


def submit_stop_loss(symbol: str, side: str, quantity: int, stop_price: float) -> str | None:
    """
    Submit a stop loss order.
    side: 'long' or 'short' - the position we're protecting
    For long position: submits SELL stop below current price
    For short position: submits BUY stop above current price
    """
    from ib_insync import Stock, Order

    broker = _get_broker()

    try:
        # Get IB connection
        ib = broker._get_ib()

        contract = Stock(symbol, 'SMART', 'USD')
        ib.qualifyContracts(contract)

        # For long position: SELL stop (exit if price drops)
        # For short position: BUY stop (exit if price rises)
        action = 'SELL' if side == 'long' else 'BUY'

        stop_order = Order(
            action=action,
            totalQuantity=quantity,
            orderType='STP',
            auxPrice=round(stop_price, 2),
            tif='GTC',  # Good Till Cancelled
        )

        trade = ib.placeOrder(contract, stop_order)
        ib.sleep(1)  # Wait for order to be acknowledged

        print(f"[executor] stop_loss({symbol}, {side}, qty={quantity}, stop=${stop_price:.2f}) -> {trade.orderStatus.status}")
        return str(trade.order.orderId)

    except Exception as e:
        print(f"[executor] stop_loss failed: {e}")
        return None
