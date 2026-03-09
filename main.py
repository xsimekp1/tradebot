"""
Railway entry point.

Modes (set via RAILWAY_MODE env var):
  evolve   — continuous strategy evolution every EVOLVE_INTERVAL seconds (default)
  trade    — intraday trading loop + nightly weight mutation
  both     — evolution + trading in parallel
"""
# Apply nest_asyncio FIRST before any asyncio imports (needed for ib_insync)
import nest_asyncio
nest_asyncio.apply()

import asyncio
import os
from datetime import datetime, timezone

from src.config import settings

MODE = os.environ.get("RAILWAY_MODE", "evolve").strip().lstrip("=")
EVOLVE_INTERVAL = int(os.environ.get("EVOLVE_INTERVAL", "600"))   # seconds
EVOLVE_MUTATIONS = int(os.environ.get("EVOLVE_MUTATIONS", "10"))  # More candidates for faster exploration
EVOLVE_SIGMA = float(os.environ.get("EVOLVE_SIGMA", "0.15"))      # Larger mutations to escape local optima


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
    """Run intraday trading loop."""
    from src.engine.loop import run_intraday_loop
    await run_intraday_loop()


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
