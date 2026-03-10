"""
CLI wrapper for the online evolution loop.

Usage:
  python scripts/evolve_online.py               # single cycle
  python scripts/evolve_online.py --loop        # continuous every 10min
  python scripts/evolve_online.py --mutations 20 --sigma 0.08
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from colorama import Fore, Style, init as colorama_init
from src.config import settings
from src.evolution.online import evolve_once, _db_url

colorama_init(autoreset=True)


def check_and_clear_trigger() -> bool:
    """Check if evolution was triggered from frontend and clear the flag."""
    import psycopg
    try:
        with psycopg.connect(_db_url()) as conn:
            row = conn.execute(
                "SELECT value FROM bot_cache WHERE key = 'evolution_trigger'"
            ).fetchone()
            if row and row[0]:
                val = row[0] if isinstance(row[0], dict) else json.loads(row[0])
                if val.get("requested"):
                    # Clear the trigger
                    conn.execute(
                        "UPDATE bot_cache SET value = '{\"requested\": false}'::jsonb WHERE key = 'evolution_trigger'"
                    )
                    conn.commit()
                    print(f"{Fore.YELLOW}[trigger] Evolution triggered from frontend!{Style.RESET_ALL}")
                    return True
    except Exception as e:
        print(f"{Fore.RED}[trigger] Check failed: {e}{Style.RESET_ALL}")
    return False


def main():
    parser = argparse.ArgumentParser(description="Online strategy evolution via walk-forward backtesting")
    parser.add_argument("--symbol", default=settings.SYMBOL)
    parser.add_argument("--mutations", type=int, default=2, help="Mutations per cycle (default: 2)")
    parser.add_argument("--sigma", type=float, default=0.02, help="Mutation strength (default: 0.02)")
    parser.add_argument("--interval", type=int, default=600, help="Loop interval seconds (default: 600)")
    parser.add_argument("--loop", action="store_true", help="Run continuously")
    args = parser.parse_args()

    if args.loop:
        print(f"{Fore.CYAN}Online evolution loop | {args.symbol} | every {args.interval}s | "
              f"{args.mutations} mutations | sigma={args.sigma}{Style.RESET_ALL}")
        cycle = 0
        while True:
            cycle += 1
            print(f"\n{Fore.CYAN}{'=' * 60}")
            print(f"  Cycle #{cycle}  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"{'=' * 60}{Style.RESET_ALL}")
            try:
                evolve_once(args.symbol, args.mutations, args.sigma)
            except Exception as exc:
                print(f"{Fore.RED}Cycle error: {exc}{Style.RESET_ALL}")

            # Sleep with trigger check every 10 seconds
            print(f"\n  Sleeping {args.interval}s (checking for triggers every 10s)...")
            sleep_remaining = args.interval
            while sleep_remaining > 0:
                time.sleep(min(10, sleep_remaining))
                sleep_remaining -= 10
                if check_and_clear_trigger():
                    print(f"{Fore.GREEN}  Waking up early due to trigger!{Style.RESET_ALL}")
                    break
    else:
        # Single run - also check for trigger first
        check_and_clear_trigger()
        evolve_once(args.symbol, args.mutations, args.sigma)


if __name__ == "__main__":
    main()
