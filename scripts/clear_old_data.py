"""
Clear old trading data from database while keeping weights.
Run: python scripts/clear_old_data.py
"""
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from src.db.session import AsyncSessionLocal


async def clear_data():
    async with AsyncSessionLocal() as db:
        # Clear trades
        result = await db.execute(text("DELETE FROM trades"))
        print(f"Deleted {result.rowcount} trades")

        # Clear signals
        result = await db.execute(text("DELETE FROM trading_signals"))
        print(f"Deleted {result.rowcount} signals")

        # Clear equity curve
        result = await db.execute(text("DELETE FROM equity_curve"))
        print(f"Deleted {result.rowcount} equity entries")

        await db.commit()
        print("\nDone! Weights preserved.")


if __name__ == "__main__":
    asyncio.run(clear_data())
