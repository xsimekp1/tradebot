from src.signals.momentum import MomentumSignal
from src.signals.rsi import RSISignal
from src.signals.bollinger import BollingerSignal
from src.signals.vwap import VWAPSignal
from src.signals.atr import ATRSignal
from src.signals.volume import VolumeSignal
from src.signals.breakout import BreakoutSignal
from src.signals.channel import ChannelPositionSignal, ChannelSlopeSignal

ALL_SIGNALS = [
    MomentumSignal(),
    RSISignal(),
    BollingerSignal(),
    VWAPSignal(),
    ATRSignal(),
    VolumeSignal(),
    BreakoutSignal(),
    ChannelPositionSignal(lookback=500),
    ChannelSlopeSignal(lookback=500),
]

__all__ = [
    "MomentumSignal", "RSISignal", "BollingerSignal", "VWAPSignal",
    "ATRSignal", "VolumeSignal", "BreakoutSignal",
    "ChannelPositionSignal", "ChannelSlopeSignal", "ALL_SIGNALS",
]
