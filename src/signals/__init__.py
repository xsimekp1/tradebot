from src.signals.momentum import MomentumSignal
from src.signals.rsi import RSISignal
from src.signals.bollinger import BollingerSignal
from src.signals.vwap import VWAPSignal
from src.signals.atr import ATRSignal
from src.signals.volume import VolumeSignal
from src.signals.breakout import BreakoutSignal
from src.signals.channel import ChannelPositionSignal, ChannelSlopeSignal

def make_signals():
    return [
        MomentumSignal(),
        RSISignal(),
        BollingerSignal(),
        VWAPSignal(),
        ATRSignal(),
        VolumeSignal(),
        BreakoutSignal(),
        ChannelPositionSignal(lookback=600),
        ChannelSlopeSignal(lookback=600),
    ]

ALL_SIGNALS = make_signals()

__all__ = [
    "MomentumSignal", "RSISignal", "BollingerSignal", "VWAPSignal",
    "ATRSignal", "VolumeSignal", "BreakoutSignal",
    "ChannelPositionSignal", "ChannelSlopeSignal", "ALL_SIGNALS", "make_signals",
]
