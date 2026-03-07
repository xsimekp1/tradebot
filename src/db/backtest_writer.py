"""Save backtest results to DB."""
import asyncio
import uuid
from datetime import datetime, timezone

from src.db.session import AsyncSessionLocal


async def _save(record: dict):
    from sqlalchemy import text
    async with AsyncSessionLocal() as db:
        await db.execute(
            text("""
                INSERT INTO backtest_results
                    (id, symbol, strategy, train_days, test_days, weights, params,
                     in_sample, out_of_sample, notes, created_at)
                VALUES
                    (:id, :symbol, :strategy, :train_days, :test_days,
                     :weights::jsonb, :params::jsonb,
                     :in_sample::jsonb, :out_of_sample::jsonb,
                     :notes, :created_at)
            """),
            {
                "id": str(uuid.uuid4()),
                "symbol": record["symbol"],
                "strategy": record["strategy"],
                "train_days": record["train_days"],
                "test_days": record.get("test_days"),
                "weights": __import__("json").dumps(record.get("weights") or {}),
                "params": __import__("json").dumps(record.get("params") or {}),
                "in_sample": __import__("json").dumps(record["in_sample"]),
                "out_of_sample": __import__("json").dumps(record.get("out_of_sample")) if record.get("out_of_sample") else None,
                "notes": record.get("notes"),
                "created_at": datetime.now(timezone.utc),
            }
        )
        await db.commit()


def save_backtest(record: dict):
    """Sync wrapper — call from CLI scripts."""
    asyncio.run(_save(record))
