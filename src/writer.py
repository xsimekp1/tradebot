import json
from datetime import datetime, timezone

from sqlalchemy import select

from src.db.session import AsyncSessionLocal
from src.engine.scoring import DEFAULT_WEIGHTS
from src.models.equity import EquityCurve
from src.models.signal import TradingSignal
from src.models.trade import Trade
from src.models.weights import SignalWeights
from src.signals import ALL_SIGNALS

SIGNAL_NAMES = [s.name for s in ALL_SIGNALS]
DEFAULT_THRESHOLD = 0.15


async def load_active_weights() -> tuple[dict[str, float], float]:
    """Load active signal weights and threshold from DB, fall back to defaults."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(SignalWeights)
            .where(SignalWeights.is_active == True)
            .order_by(SignalWeights.created_at.desc())
        )
        active = result.scalars().first()
        if active:
            # Handle corrupted weights (string instead of dict)
            raw_weights = active.weights
            if isinstance(raw_weights, str):
                try:
                    weights_dict = json.loads(raw_weights)
                except:
                    print(f"[loop] Weights corrupted (string), using defaults")
                    return dict(DEFAULT_WEIGHTS), DEFAULT_THRESHOLD
            elif isinstance(raw_weights, dict):
                weights_dict = raw_weights.copy()
            else:
                print(f"[loop] Weights unknown type {type(raw_weights)}, using defaults")
                return dict(DEFAULT_WEIGHTS), DEFAULT_THRESHOLD

            # Validate that keys are signal names, not corrupted
            valid_keys = [k for k in weights_dict.keys() if k in SIGNAL_NAMES or k == "_threshold"]
            if len(valid_keys) < len(SIGNAL_NAMES) // 2:
                print(f"[loop] Weights have corrupted keys, using defaults")
                return dict(DEFAULT_WEIGHTS), DEFAULT_THRESHOLD

            perf = active.performance if active.performance else {}
            if isinstance(perf, str):
                try:
                    perf = json.loads(perf)
                except:
                    perf = {}
            threshold = float(perf.get("threshold", weights_dict.pop("_threshold", DEFAULT_THRESHOLD)))
            return weights_dict, threshold
        return dict(DEFAULT_WEIGHTS), DEFAULT_THRESHOLD


async def write_signals(
    symbol: str,
    signal_values: dict[str, float],
    weights: dict[str, float],
    total_score: float,
    timestamp: datetime,
    channel_info: dict | None = None,
):
    """Write one row per signal to trading_signals table."""
    async with AsyncSessionLocal() as db:
        for name, value in signal_values.items():
            weight = weights.get(name, 0.0)
            weight_sum = sum(abs(w) for k, w in weights.items() if not k.startswith("_"))
            contribution = (value * weight / weight_sum) if weight_sum > 0 else 0.0

            row = TradingSignal(
                symbol=symbol,
                signal_name=name,
                value=round(value, 6),
                weight=round(weight, 6),
                score_contribution=round(contribution, 6),
                timestamp=timestamp,
            )
            db.add(row)
        await db.commit()

    # Store channel info in database for dashboard access
    if channel_info:
        await write_channel_info(channel_info)


async def write_channel_info(channel_info: dict) -> None:
    """Store channel info in database (upsert into cache table)."""
    import json
    from sqlalchemy import text

    # Convert numpy types to native Python types for JSON serialization
    def convert_numpy(obj):
        if hasattr(obj, 'item'):  # numpy scalar
            return obj.item()
        return obj

    clean_info = {k: convert_numpy(v) for k, v in channel_info.items()}

    async with AsyncSessionLocal() as db:
        # Create table if not exists and upsert the data
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS bot_cache (
                key VARCHAR(50) PRIMARY KEY,
                value JSONB NOT NULL,
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))
        # Use CAST instead of :: to avoid parameter parsing issues
        await db.execute(text("""
            INSERT INTO bot_cache (key, value, updated_at)
            VALUES ('channel_info', CAST(:value AS JSONB), NOW())
            ON CONFLICT (key) DO UPDATE SET value = CAST(:value AS JSONB), updated_at = NOW()
        """), {"value": json.dumps(clean_info)})
        await db.commit()


async def write_trade_open(
    symbol: str, side: str, qty: float, entry_price: float, score: float,
    order_id: str | None, timestamp: datetime
) -> str:
    """Insert an open trade row, return the DB trade id."""
    import uuid
    trade_id = uuid.uuid4()
    async with AsyncSessionLocal() as db:
        trade = Trade(
            id=trade_id,
            symbol=symbol,
            side=side,
            quantity=round(qty, 8),
            entry_price=round(entry_price, 8),
            score=round(score, 6),
            alpaca_order_id=order_id,
            opened_at=timestamp,
        )
        db.add(trade)
        await db.commit()
    return str(trade_id)


async def write_trade_close(
    trade_id: str, exit_price: float, pnl: float, timestamp: datetime
) -> None:
    """Update an open trade row with exit info."""
    from sqlalchemy import update
    from src.models.trade import Trade as TradeModel
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(TradeModel)
            .where(TradeModel.id == trade_id)
            .values(exit_price=round(exit_price, 8), pnl=round(pnl, 8), closed_at=timestamp)
        )
        await db.commit()


async def write_equity(account: dict, timestamp: datetime):
    """Write equity snapshot to equity_curve table."""
    async with AsyncSessionLocal() as db:
        equity = account.get("equity", 0.0)
        last_equity = account.get("last_equity", equity)
        daily_pnl = equity - last_equity

        # Approximate cumulative PnL by comparing to initial equity
        # (for now, just use daily_pnl — proper cumulative requires baseline)
        row = EquityCurve(
            total_equity=round(equity, 8),
            cash=round(account.get("cash", 0.0), 8),
            portfolio_value=round(account.get("portfolio_value", 0.0), 8),
            daily_pnl=round(daily_pnl, 8),
            cumulative_pnl=round(daily_pnl, 8),  # TODO: track proper baseline
            timestamp=timestamp,
        )
        db.add(row)
        await db.commit()
