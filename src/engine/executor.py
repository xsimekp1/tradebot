"""
Trade executor - handles position management through broker abstraction.
Supports Alpaca, OANDA, and IBKR brokers.
"""
import asyncio
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
    """Run async coroutine from sync context."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Create a new task if we're already in an async context
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


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
        current_price = _run_async(broker.get_current_price(symbol))

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
        current_price = _run_async(broker.get_current_price(symbol))

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
