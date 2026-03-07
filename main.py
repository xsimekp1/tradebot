"""
Railway entry point.

Modes (set via RAILWAY_MODE env var):
  evolve   — continuous strategy evolution every EVOLVE_INTERVAL seconds (default)
  trade    — intraday trading loop + nightly weight mutation
  both     — evolution + trading in parallel
"""
import asyncio
import os
from datetime import datetime, timezone

from src.config import settings

MODE = os.environ.get("RAILWAY_MODE", "evolve").strip().lstrip("=")
EVOLVE_INTERVAL = int(os.environ.get("EVOLVE_INTERVAL", "600"))   # seconds
EVOLVE_MUTATIONS = int(os.environ.get("EVOLVE_MUTATIONS", "10"))
EVOLVE_SIGMA = float(os.environ.get("EVOLVE_SIGMA", "0.05"))


async def evolution_loop():
    """Run strategy evolution every EVOLVE_INTERVAL seconds."""
    from src.evolution.online import evolve_once
    cycle = 0
    while True:
        cycle += 1
        print(f"\n[evolve] Cycle #{cycle}  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
        try:
            await asyncio.to_thread(evolve_once, settings.SYMBOL, EVOLVE_MUTATIONS, EVOLVE_SIGMA)
        except Exception as e:
            print(f"[evolve] Error: {e}")
        print(f"[evolve] Sleeping {EVOLVE_INTERVAL}s until next cycle...")
        await asyncio.sleep(EVOLVE_INTERVAL)


async def trading_loop():
    """Run intraday trading loop + nightly weight mutation."""
    from src.engine.loop import run_intraday_loop
    from src.evolution.mutator import run_nightly_mutation

    async def nightly_scheduler():
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
            await asyncio.sleep(600)

    await asyncio.gather(run_intraday_loop(), nightly_scheduler())


async def main():
    print(f"[main] Starting in mode={MODE}  symbol={settings.SYMBOL}")
    if MODE == "evolve":
        await evolution_loop()
    elif MODE == "trade":
        await trading_loop()
    elif MODE == "both":
        await asyncio.gather(evolution_loop(), trading_loop())
    else:
        print(f"[main] Unknown RAILWAY_MODE={MODE!r}. Use: evolve | trade | both")


if __name__ == "__main__":
    asyncio.run(main())
