"""
Railway entry point — starts the intraday trading loop.
Nightly mutation runs as a timed check inside the main process.
"""
import asyncio
import threading
from datetime import datetime, timezone

from src.engine.loop import run_intraday_loop
from src.evolution.mutator import run_nightly_mutation


async def nightly_scheduler():
    """Run weight mutation once per day around 18:00 UTC (after market close)."""
    last_mutation_date = None
    while True:
        now = datetime.now(timezone.utc)
        if now.hour >= 18 and now.date() != last_mutation_date:
            print("[main] Running nightly weight mutation...")
            try:
                await run_nightly_mutation()
                last_mutation_date = now.date()
            except Exception as e:
                print(f"[main] Nightly mutation error: {e}")
        await asyncio.sleep(600)  # check every 10 minutes


async def main():
    await asyncio.gather(
        run_intraday_loop(),
        nightly_scheduler(),
    )


if __name__ == "__main__":
    asyncio.run(main())
