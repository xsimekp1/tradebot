from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

from src.config import settings


def _tif() -> TimeInForce:
    # Crypto requires GTC; stocks use DAY
    return TimeInForce.GTC if settings.ASSET_CLASS == "crypto" else TimeInForce.DAY


def get_trading_client() -> TradingClient:
    return TradingClient(
        api_key=settings.ALPACA_API_KEY,
        secret_key=settings.ALPACA_SECRET_KEY,
        paper=True,
    )


def get_current_position(symbol: str) -> dict | None:
    """Returns position dict with keys: side, qty, avg_entry_price. None if no position."""
    client = get_trading_client()
    try:
        pos = client.get_open_position(symbol)
        return {
            "side": "long" if float(pos.qty) > 0 else "short",
            "qty": abs(float(pos.qty)),
            "avg_entry_price": float(pos.avg_entry_price),
        }
    except Exception as e:
        if "position does not exist" not in str(e).lower() and "no position" not in str(e).lower():
            print(f"[executor] get_current_position({symbol}) error: {e}")
        return None


def close_position(symbol: str) -> str | None:
    """Close any existing position for symbol. Returns order ID or None."""
    client = get_trading_client()
    try:
        response = client.close_position(symbol)
        return str(response.id)
    except Exception:
        return None


def open_long(symbol: str, score: float) -> str | None:
    """Open a long (buy) position sized by POSITION_SIZE_USD. Returns order ID or None."""
    client = get_trading_client()
    try:
        request = MarketOrderRequest(
            symbol=symbol,
            notional=settings.POSITION_SIZE_USD,
            side=OrderSide.BUY,
            time_in_force=_tif(),
        )
        order = client.submit_order(request)
        return str(order.id)
    except Exception as e:
        print(f"[executor] open_long failed: {e}")
        return None


def open_short(symbol: str, score: float) -> str | None:
    """Open a short (sell) position sized by POSITION_SIZE_USD. Returns order ID or None."""
    client = get_trading_client()
    try:
        request = MarketOrderRequest(
            symbol=symbol,
            notional=settings.POSITION_SIZE_USD,
            side=OrderSide.SELL,
            time_in_force=_tif(),
        )
        order = client.submit_order(request)
        return str(order.id)
    except Exception as e:
        print(f"[executor] open_short failed: {e}")
        return None


def get_account() -> dict:
    """Returns account equity, cash, portfolio value."""
    client = get_trading_client()
    account = client.get_account()
    return {
        "equity": float(account.equity),
        "cash": float(account.cash),
        "portfolio_value": float(account.portfolio_value),
        "last_equity": float(account.last_equity),
    }
