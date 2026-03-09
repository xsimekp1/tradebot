import random
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import AsyncSessionLocal
from src.engine.scoring import DEFAULT_WEIGHTS
from src.models.trade import Trade
from src.models.weights import SignalWeights


async def run_nightly_mutation():
    """
    Genetic-style weight mutation:
    1. Load recent trades and evaluate PnL per active weight config
    2. If insufficient data, use defaults as seed
    3. Mutate: each weight += gauss(0, 0.1), then normalize
    4. Save new weights as active, deactivate old
    """
    async with AsyncSessionLocal() as db:
        # Load last N days of closed trades
        lookback_days = 7
        since = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        result = await db.execute(
            select(Trade).where(
                Trade.closed_at.isnot(None),
                Trade.closed_at >= since,
            )
        )
        trades = result.scalars().all()

        # Load current active weights
        active_result = await db.execute(
            select(SignalWeights).where(SignalWeights.is_active == True).order_by(
                SignalWeights.created_at.desc()
            )
        )
        active = active_result.scalars().first()

        if active:
            current_weights = dict(active.weights)
            current_version = active.version
            # Merge in any NEW signals from DEFAULT_WEIGHTS that aren't in active model
            for signal_name, default_weight in DEFAULT_WEIGHTS.items():
                if signal_name not in current_weights:
                    current_weights[signal_name] = default_weight
                    print(f"[mutator] Added new signal: {signal_name} = {default_weight}")
        else:
            current_weights = dict(DEFAULT_WEIGHTS)
            current_version = 0

        # Evaluate performance
        total_pnl = sum(float(t.pnl) for t in trades if t.pnl is not None)
        num_trades = len(trades)
        win_rate = (
            sum(1 for t in trades if t.pnl and float(t.pnl) > 0) / num_trades
            if num_trades > 0
            else 0.0
        )

        performance = {
            "total_pnl": round(total_pnl, 4),
            "num_trades": num_trades,
            "win_rate": round(win_rate, 4),
            "lookback_days": lookback_days,
        }

        print(f"[mutator] Performance: {performance}")

        # Mutate weights
        new_weights = {}
        for signal_name, weight in current_weights.items():
            mutated = weight + random.gauss(0, 0.1)
            new_weights[signal_name] = max(0.0, mutated)  # keep weights non-negative

        # Normalize so weights sum to 1.0
        total = sum(new_weights.values())
        if total > 0:
            new_weights = {k: round(v / total, 6) for k, v in new_weights.items()}
        else:
            new_weights = dict(DEFAULT_WEIGHTS)

        print(f"[mutator] New weights: {new_weights}")

        # Deactivate current active weights
        await db.execute(
            update(SignalWeights).where(SignalWeights.is_active == True).values(is_active=False)
        )

        # Insert new weights
        new_version = current_version + 1
        new_record = SignalWeights(
            version=new_version,
            weights=new_weights,
            performance=performance,
            is_active=True,
        )
        db.add(new_record)
        await db.commit()

        print(f"[mutator] Saved new weights v{new_version} as active")
        return new_weights
