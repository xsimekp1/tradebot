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
from src.writer import write_signals, write_equity, write_trade_open, write_trade_close, load_active_weights

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

    open_trade_id: str | None = None  # DB id of current open trade

    while True:
        iteration_start = time.time()
        now = datetime.now(timezone.utc)

        try:
            if settings.ASSET_CLASS == "stock" and not is_market_open():
                print(f"{Fore.YELLOW}[loop] Market closed, waiting...{Style.RESET_ALL}")
                try:
                    account = get_account()
                    await write_equity(account, now)
                except Exception as e:
                    print(f"{Fore.RED}[loop] Equity write error: {e}{Style.RESET_ALL}")
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
            weights, threshold = await load_active_weights()
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
            current_price = float(bars["close"].iloc[-1])

            if score > threshold and current_side != "long" and open_trade_id is None:
                if current_side == "short":
                    close_position(symbol)
                print(f"{Fore.GREEN}[loop] Opening LONG (score={score:+.3f} > {threshold:.3f}){Style.RESET_ALL}")
                order_id = open_long(symbol, score)
                if order_id:
                    qty = settings.POSITION_SIZE_USD / current_price
                    open_trade_id = await write_trade_open(symbol, "long", qty, current_price, score, order_id, now)

            elif score < -threshold and open_trade_id is not None and current_side == "long":
                # Close long on bearish signal
                pnl = (current_price - position["avg_entry_price"]) * position["qty"] if position else 0.0
                await write_trade_close(open_trade_id, current_price, pnl, now)
                open_trade_id = None
                print(f"{Fore.YELLOW}[loop] Closing LONG, score={score:+.3f} < {-threshold:.3f}{Style.RESET_ALL}")
                close_position(symbol)
                if settings.ASSET_CLASS != "crypto":
                    print(f"{Fore.RED}[loop] Opening SHORT (score={score:+.3f}){Style.RESET_ALL}")
                    order_id = open_short(symbol, score)
                    if order_id:
                        qty = settings.POSITION_SIZE_USD / current_price
                        open_trade_id = await write_trade_open(symbol, "short", qty, current_price, score, order_id, now)

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
