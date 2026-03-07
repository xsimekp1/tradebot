from datetime import datetime, timezone

from sqlalchemy import select

from src.db.session import AsyncSessionLocal
from src.engine.scoring import DEFAULT_WEIGHTS
from src.models.equity import EquityCurve
from src.models.signal import TradingSignal
from src.models.trade import Trade
from src.models.weights import SignalWeights


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
            weights_dict = dict(active.weights)
            perf = dict(active.performance) if active.performance else {}
            threshold = float(perf.get("threshold", weights_dict.pop("_threshold", DEFAULT_THRESHOLD)))
            return weights_dict, threshold
        return dict(DEFAULT_WEIGHTS), DEFAULT_THRESHOLD


async def write_signals(
    symbol: str,
    signal_values: dict[str, float],
    weights: dict[str, float],
    total_score: float,
    timestamp: datetime,
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
