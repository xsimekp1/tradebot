"""
Create evolution_results table for tracking evolution cycle outcomes.
Run this script once to create the table in the database.

Usage:
    python scripts/create_evolution_results_table.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import settings


def get_db_url() -> str:
    return (
        settings.DATABASE_URL_ASYNC
        .replace("postgresql+asyncpg://", "postgresql://")
        .replace("?ssl=require", "?sslmode=require")
    )


def create_table():
    import psycopg

    print("Connecting to database...")
    with psycopg.connect(get_db_url()) as conn:
        print("Creating evolution_results table...")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS evolution_results (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                symbol VARCHAR(20) NOT NULL,
                version_before INTEGER NOT NULL,
                version_after INTEGER,
                current_sharpe NUMERIC(10, 6),
                best_sharpe NUMERIC(10, 6),
                mutations_tried INTEGER NOT NULL,
                model_changed BOOLEAN NOT NULL,
                improvement NUMERIC(10, 6),
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)

        # Create indexes
        conn.execute("""
            CREATE INDEX IF NOT EXISTS ix_evolution_results_created_at
            ON evolution_results(created_at)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS ix_evolution_results_symbol
            ON evolution_results(symbol)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS ix_evolution_results_model_changed
            ON evolution_results(model_changed)
        """)

        conn.commit()
        print("Table and indexes created successfully!")

        # Verify
        result = conn.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'evolution_results'
            ORDER BY ordinal_position
        """)
        print("\nTable structure:")
        for row in result:
            print(f"  {row[0]}: {row[1]}")


if __name__ == "__main__":
    create_table()
