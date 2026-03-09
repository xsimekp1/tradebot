"""
Broker abstraction layer.
Supports multiple brokers: Alpaca (stocks/crypto), OANDA (forex), IBKR (all).
"""
from src.brokers.base import (
    BaseBroker,
    AccountInfo,
    Position,
    PositionSide,
    Order,
    OrderSide,
    OrderType,
)
from src.brokers.alpaca import AlpacaBroker
from src.brokers.oanda import OandaBroker
from src.brokers.ibkr import IBKRBroker


def get_broker(broker_name: str = "alpaca", **kwargs) -> BaseBroker:
    """
    Factory function to create a broker instance.

    Args:
        broker_name: "alpaca", "oanda", or "ibkr"
        **kwargs: Broker-specific arguments

    For IBKR:
        - Requires IB Gateway or TWS running locally
        - Uses settings from src.config.settings (IBKR_HOST, IBKR_PORT, IBKR_CLIENT_ID)

    For OANDA:
        - api_key: OANDA API token
        - account_id: OANDA account ID
        - practice: True for demo, False for live (default: True)

    For Alpaca:
        - Uses settings from src.config.settings
    """
    if broker_name.lower() == "alpaca":
        return AlpacaBroker()
    elif broker_name.lower() == "oanda":
        return OandaBroker(**kwargs)
    elif broker_name.lower() == "ibkr":
        return IBKRBroker()
    else:
        raise ValueError(f"Unknown broker: {broker_name}")


__all__ = [
    "BaseBroker",
    "AccountInfo",
    "Position",
    "PositionSide",
    "Order",
    "OrderSide",
    "OrderType",
    "AlpacaBroker",
    "OandaBroker",
    "IBKRBroker",
    "get_broker",
]
