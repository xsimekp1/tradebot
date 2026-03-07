from src.signals.momentum import MomentumSignal
from src.signals.rsi import RSISignal
from src.signals.bollinger import BollingerSignal
from src.signals.vwap import VWAPSignal
from src.signals.atr import ATRSignal
from src.signals.volume import VolumeSignal
from src.signals.breakout import BreakoutSignal

ALL_SIGNALS = [
    MomentumSignal(),
    RSISignal(),
    BollingerSignal(),
    VWAPSignal(),
    ATRSignal(),
    VolumeSignal(),
    BreakoutSignal(),
]

__all__ = [
    "MomentumSignal", "RSISignal", "BollingerSignal", "VWAPSignal",
    "ATRSignal", "VolumeSignal", "BreakoutSignal", "ALL_SIGNALS",
]
