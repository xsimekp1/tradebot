import asyncio
import time
from datetime import datetime, timezone

from colorama import Fore, Style, init as colorama_init

from src.config import settings
from src.engine.data import fetch_bars
from src.engine.executor import (
    get_account,
    get_current_position,
    close_position,
    open_long,
    open_short,
)
from src.engine.scoring import compute_score
from src.signals import ALL_SIGNALS
from src.writer import write_signals, write_equity, load_active_weights

colorama_init(autoreset=True)


def is_market_open() -> bool:
    """Simple check: NYSE market hours Mon-Fri 9:30-16:00 ET (UTC-4/5)."""
    from alpaca.trading.client import TradingClient
    try:
        client = TradingClient(
            api_key=settings.ALPACA_API_KEY,
            secret_key=settings.ALPACA_SECRET_KEY,
            paper=True,
        )
        clock = client.get_clock()
        return clock.is_open
    except Exception:
        return True  # assume open if check fails


async def run_intraday_loop():
    symbol = settings.SYMBOL
    print(f"{Fore.CYAN}[loop] Starting intraday loop for {symbol}{Style.RESET_ALL}")

    while True:
        iteration_start = time.time()
        now = datetime.now(timezone.utc)

        try:
            if settings.ASSET_CLASS == "stock" and not is_market_open():
                print(f"{Fore.YELLOW}[loop] Market closed, waiting...{Style.RESET_ALL}")
                await asyncio.sleep(settings.LOOP_INTERVAL_SECONDS)
                continue

            # 1. Fetch bars
            bars = fetch_bars(symbol, limit=settings.BARS_LIMIT)
            if bars.empty:
                print(f"{Fore.YELLOW}[loop] No bars received, skipping{Style.RESET_ALL}")
                await asyncio.sleep(settings.LOOP_INTERVAL_SECONDS)
                continue

            # 2. Compute signals
            signal_values = {s.name: s.safe_compute(bars) for s in ALL_SIGNALS}

            # 3. Load weights and score
            weights = await load_active_weights()
            score = compute_score(signal_values, weights)

            print(
                f"{Fore.WHITE}[loop] {now.strftime('%H:%M:%S')} | "
                f"Score: {score:+.3f} | "
                f"Signals: " +
                " ".join(f"{k}={v:+.2f}" for k, v in signal_values.items())
            )

            # 4. Get current position
            position = get_current_position(symbol)
            current_side = position["side"] if position else None

            # 5. Execute trade logic
            order_id = None
            if score > settings.SCORE_LONG_THRESHOLD and current_side != "long":
                if current_side == "short":
                    print(f"{Fore.YELLOW}[loop] Closing short{Style.RESET_ALL}")
                    close_position(symbol)
                print(f"{Fore.GREEN}[loop] Opening LONG (score={score:+.3f}){Style.RESET_ALL}")
                order_id = open_long(symbol, score)

            elif score < settings.SCORE_SHORT_THRESHOLD and current_side != "short":
                if settings.ASSET_CLASS == "crypto":
                    # Crypto: no short selling — just close long if held
                    if current_side == "long":
                        print(f"{Fore.YELLOW}[loop] Score bearish, closing long (no crypto shorts){Style.RESET_ALL}")
                        close_position(symbol)
                else:
                    if current_side == "long":
                        print(f"{Fore.YELLOW}[loop] Closing long{Style.RESET_ALL}")
                        close_position(symbol)
                    print(f"{Fore.RED}[loop] Opening SHORT (score={score:+.3f}){Style.RESET_ALL}")
                    order_id = open_short(symbol, score)

            # 6. Write signals and equity to DB
            await write_signals(symbol, signal_values, weights, score, now)

            account = get_account()
            await write_equity(account, now)

        except Exception as e:
            print(f"{Fore.RED}[loop] Error: {e}{Style.RESET_ALL}")

        # Sleep for remainder of interval
        elapsed = time.time() - iteration_start
        sleep_time = max(0, settings.LOOP_INTERVAL_SECONDS - elapsed)
        await asyncio.sleep(sleep_time)
