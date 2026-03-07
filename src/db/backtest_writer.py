"""Save backtest results to DB."""
import json
import uuid
from datetime import datetime, timezone

from src.config import settings


def save_backtest(record: dict):
    """Save a backtest result using a plain sync psycopg connection."""
    import psycopg

    # Convert asyncpg URL to plain psycopg URL (ssl= → sslmode=)
    db_url = (
        settings.DATABASE_URL_ASYNC
        .replace("postgresql+asyncpg://", "postgresql://")
        .replace("?ssl=require", "?sslmode=require")
    )

    with psycopg.connect(db_url) as conn:
        conn.execute(
            """
            INSERT INTO backtest_results
                (id, symbol, strategy, train_days, test_days, weights, params,
                 in_sample, out_of_sample, notes, created_at)
            VALUES
                (%s, %s, %s, %s, %s,
                 %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb,
                 %s, %s)
            """,
            (
                str(uuid.uuid4()),
                record["symbol"],
                record["strategy"],
                record["train_days"],
                record.get("test_days"),
                json.dumps(record.get("weights") or {}),
                json.dumps(record.get("params") or {}),
                json.dumps(record["in_sample"]),
                json.dumps(record.get("out_of_sample")) if record.get("out_of_sample") else None,
                record.get("notes"),
                datetime.now(timezone.utc),
            ),
        )
        conn.commit()
