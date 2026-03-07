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
from src.signals.channel import ChannelPositionSignal
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


async def _recover_open_trade(symbol: str) -> str | None:
    """On startup, find any open trade in DB. If Alpaca has a position but DB doesn't, create a synthetic entry."""
    from sqlalchemy import select
    from src.db.session import AsyncSessionLocal
    from src.models.trade import Trade

    # 1. Check DB for open trade
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Trade)
                .where(Trade.symbol == symbol, Trade.closed_at.is_(None))
                .order_by(Trade.opened_at.desc())
            )
            trade = result.scalars().first()
            if trade:
                print(f"{Fore.CYAN}[loop] Recovered open trade {trade.id} ({trade.side}) from DB{Style.RESET_ALL}")
                return str(trade.id)
    except Exception as e:
        print(f"{Fore.RED}[loop] DB trade recovery error: {e}{Style.RESET_ALL}")

    # 2. No DB trade — check if Alpaca has a position and create synthetic entry
    position = get_current_position(symbol)
    if position:
        now = datetime.now(timezone.utc)
        print(f"{Fore.YELLOW}[loop] Found orphaned Alpaca {position['side']} position, creating DB entry{Style.RESET_ALL}")
        try:
            trade_id = await write_trade_open(
                symbol, position["side"], position["qty"],
                position["avg_entry_price"], 0.0, None, now
            )
            return trade_id
        except Exception as e:
            print(f"{Fore.RED}[loop] Failed to create synthetic trade: {e}{Style.RESET_ALL}")

    return None


async def run_intraday_loop():
    symbol = settings.SYMBOL
    print(f"{Fore.CYAN}[loop] Starting intraday loop for {symbol}{Style.RESET_ALL}")
    _prev_support: float | None = None
    _prev_resistance: float | None = None

    # Recover open trade from DB on startup (survives restarts)
    open_trade_id: str | None = await _recover_open_trade(symbol)

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

            # Get channel info from ChannelPositionSignal for frontend display
            channel_info = None
            for sig in ALL_SIGNALS:
                if isinstance(sig, ChannelPositionSignal) and sig.last_channel_info:
                    channel_info = sig.last_channel_info
                    ci = channel_info
                    ds = f"  Δs={ci['support_price'] - _prev_support:+.2f}" if _prev_support else ""
                    dr = f"  Δr={ci['resistance_price'] - _prev_resistance:+.2f}" if _prev_resistance else ""
                    breaks_str = f"  breaks={ci['support_breaks']}({ci['support_breaks_pct']}%)" if 'support_breaks' in ci else ""
                    slope_str = f"  slope={ci['support_slope']:+.6f}" if 'support_slope' in ci else ""
                    print(
                        f"[channel] support={ci['support_price']:.2f}{ds}{breaks_str}{slope_str}  "
                        f"resistance={ci['resistance_price']:.2f}{dr}  "
                        f"pos={ci['position_pct']:.1f}%  "
                        f"signal={signal_values.get('channel_position', 0):+.4f}"
                    )
                    _prev_support = ci['support_price']
                    _prev_resistance = ci['resistance_price']
                    break

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
            position_usd = get_account()["equity"] * 0.05  # 5% of current equity

            if score > threshold and current_side != "long" and open_trade_id is None:
                if current_side == "short":
                    close_position(symbol)
                print(f"{Fore.GREEN}[loop] → OPEN LONG ${position_usd:.0f}  score={score:+.3f} > threshold={threshold:.3f}{Style.RESET_ALL}")
                order_id = open_long(symbol, score, position_usd)
                if order_id:
                    qty = position_usd / current_price
                    open_trade_id = await write_trade_open(symbol, "long", qty, current_price, score, order_id, now)

            elif score < -threshold and open_trade_id is not None and current_side == "long":
                pnl = (current_price - position["avg_entry_price"]) * position["qty"] if position else 0.0
                await write_trade_close(open_trade_id, current_price, pnl, now)
                open_trade_id = None
                print(f"{Fore.YELLOW}[loop] → CLOSE LONG  score={score:+.3f} < -{threshold:.3f}  pnl=${pnl:+.2f}{Style.RESET_ALL}")
                close_position(symbol)
                if settings.ASSET_CLASS != "crypto":
                    print(f"{Fore.RED}[loop] → OPEN SHORT ${position_usd:.0f}  score={score:+.3f}{Style.RESET_ALL}")
                    order_id = open_short(symbol, score, position_usd)
                    if order_id:
                        qty = position_usd / current_price
                        open_trade_id = await write_trade_open(symbol, "short", qty, current_price, score, order_id, now)

            else:
                pos_str = f"pozice={current_side}" if current_side else "bez pozice"
                if score > 0:
                    reason = f"score={score:+.3f} pod prahem {threshold:.3f}" if score <= threshold else f"score={score:+.3f} ale {pos_str}"
                elif score < 0:
                    reason = f"score={score:+.3f} nad prahem -{threshold:.3f}" if score >= -threshold else f"score={score:+.3f} ale {pos_str}"
                else:
                    reason = f"score={score:+.3f}"
                print(f"[loop] → žádná akce  {reason}  ({pos_str})")

            # 6. Write signals and equity to DB
            await write_signals(symbol, signal_values, weights, score, now, channel_info)

            account = get_account()
            await write_equity(account, now)

        except Exception as e:
            print(f"{Fore.RED}[loop] Error: {e}{Style.RESET_ALL}")

        # Sleep for remainder of interval
        elapsed = time.time() - iteration_start
        sleep_time = max(0, settings.LOOP_INTERVAL_SECONDS - elapsed)
        await asyncio.sleep(sleep_time)
