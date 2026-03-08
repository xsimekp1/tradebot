"""
Broker abstraction layer.
Supports multiple brokers: Alpaca (stocks/crypto), OANDA (forex).
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


def get_broker(broker_name: str = "alpaca", **kwargs) -> BaseBroker:
    """
    Factory function to create a broker instance.

    Args:
        broker_name: "alpaca" or "oanda"
        **kwargs: Broker-specific arguments

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
    "get_broker",
]
