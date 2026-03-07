"""
CLI wrapper for the online evolution loop.

Usage:
  python scripts/evolve_online.py               # single cycle
  python scripts/evolve_online.py --loop        # continuous every 10min
  python scripts/evolve_online.py --mutations 20 --sigma 0.08
"""
import argparse
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from colorama import Fore, Style, init as colorama_init
from src.config import settings
from src.evolution.online import evolve_once

colorama_init(autoreset=True)


def main():
    parser = argparse.ArgumentParser(description="Online strategy evolution via walk-forward backtesting")
    parser.add_argument("--symbol", default=settings.SYMBOL)
    parser.add_argument("--mutations", type=int, default=2, help="Mutations per cycle (default: 2)")
    parser.add_argument("--sigma", type=float, default=0.05, help="Mutation strength (default: 0.05)")
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
            print(f"\n  Sleeping {args.interval}s...")
            time.sleep(args.interval)
    else:
        evolve_once(args.symbol, args.mutations, args.sigma)


if __name__ == "__main__":
    main()
