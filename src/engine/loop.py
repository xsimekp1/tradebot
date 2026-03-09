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
    submit_stop_loss,
)
from src.engine.scoring import compute_score
from src.signals import ALL_SIGNALS
from src.signals.channel import ChannelPositionSignal
from src.writer import write_signals, write_equity, write_trade_open, write_trade_close, load_active_weights

colorama_init(autoreset=True)


def is_market_open() -> bool:
    """Check if stock market is open. For crypto/forex, always returns True."""
    # Crypto and forex trade 24/7
    if settings.ASSET_CLASS in ("crypto", "forex"):
        return True

    # For stocks, check market hours
    if settings.BROKER == "alpaca":
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
            pass

    # For IBKR or fallback: simple time-based check (NYSE hours)
    from datetime import datetime
    import pytz
    now = datetime.now(pytz.timezone("US/Eastern"))
    # Mon=0, Sun=6
    if now.weekday() >= 5:  # Weekend
        return False
    # Regular trading hours: 9:30 - 16:00 ET
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    return market_open <= now <= market_close


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

    # 2. No DB trade — check if broker has a position and create synthetic entry
    position = get_current_position(symbol)
    if position:
        now = datetime.now(timezone.utc)
        print(f"{Fore.YELLOW}[loop] Found orphaned {position['side']} position, creating DB entry{Style.RESET_ALL}")
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
                    s_breaks_str = f"  breaks={ci['support_breaks']}({ci['support_breaks_pct']}%)" if 'support_breaks' in ci else ""
                    s_slope_str = f"  slope={ci['support_slope']:+.6f}" if 'support_slope' in ci else ""
                    r_breaks_str = f"  breaks={ci['resistance_breaks']}({ci['resistance_breaks_pct']}%)" if 'resistance_breaks' in ci else ""
                    r_slope_str = f"  slope={ci['resistance_slope']:+.6f}" if 'resistance_slope' in ci else ""
                    print(
                        f"[channel] support={ci['support_price']:.2f}{ds}{s_breaks_str}{s_slope_str}  "
                        f"resistance={ci['resistance_price']:.2f}{dr}{r_breaks_str}{r_slope_str}  "
                        f"pos={ci['position_pct']:.1f}%  "
                        f"signal={signal_values.get('channel_position', 0):+.4f}"
                    )
                    _prev_support = ci['support_price']
                    _prev_resistance = ci['resistance_price']
                    break

            # 3. Load weights and score
            weights, _ = await load_active_weights()
            score = compute_score(signal_values, weights)

            # Use 4 thresholds from config for two-sided trading
            long_entry = settings.LONG_ENTRY_THRESHOLD
            long_exit = settings.LONG_EXIT_THRESHOLD
            short_entry = settings.SHORT_ENTRY_THRESHOLD
            short_exit = settings.SHORT_EXIT_THRESHOLD

            print(
                f"{Fore.WHITE}[loop] {now.strftime('%H:%M:%S')} | "
                f"Score: {score:+.3f} | "
                f"Thresholds: L[{long_entry:+.2f}/{long_exit:+.2f}] S[{short_entry:+.2f}/{short_exit:+.2f}] | "
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

            # Fee calculation depends on broker/asset
            if settings.BROKER == "alpaca" and settings.ASSET_CLASS == "crypto":
                fee_rate = 0.0025  # 0.25% per side
            elif settings.BROKER == "ibkr":
                fee_rate = 0.00002  # ~$2 per $100k = 0.002%
            else:
                fee_rate = 0.0001  # Default 0.01%

            def calc_pnl(side: str) -> float:
                """Calculate PnL including fees."""
                if not position:
                    return 0.0
                qty = position["qty"]
                avg_entry = position["avg_entry_price"]
                if side == "long":
                    pnl_price = (current_price - avg_entry) * qty
                else:  # short
                    pnl_price = (avg_entry - current_price) * qty
                fee_open = avg_entry * qty * fee_rate
                fee_close = current_price * qty * fee_rate
                return pnl_price - fee_open - fee_close

            # Two-sided trading logic with 4 thresholds
            if current_side == "long":
                # We have a LONG position - check for exit
                if score < long_exit:
                    pnl = calc_pnl("long")
                    await write_trade_close(open_trade_id, current_price, pnl, now)
                    open_trade_id = None
                    print(f"{Fore.YELLOW}[loop] -> CLOSE LONG  score={score:+.3f} < {long_exit:+.3f}  pnl=${pnl:+.2f}{Style.RESET_ALL}")
                    close_position(symbol)
                    # Check if we should immediately open SHORT
                    if score < short_entry and settings.ASSET_CLASS != "crypto":
                        print(f"{Fore.RED}[loop] -> OPEN SHORT ${position_usd:.0f}  score={score:+.3f} < {short_entry:+.3f}{Style.RESET_ALL}")
                        order_id = open_short(symbol, score, position_usd)
                        if order_id:
                            qty = position_usd / current_price
                            open_trade_id = await write_trade_open(symbol, "short", qty, current_price, score, order_id, now)
                else:
                    print(f"[loop] -> HOLD LONG  score={score:+.3f} >= {long_exit:+.3f}")

            elif current_side == "short":
                # We have a SHORT position - check for exit
                if score > short_exit:
                    pnl = calc_pnl("short")
                    await write_trade_close(open_trade_id, current_price, pnl, now)
                    open_trade_id = None
                    print(f"{Fore.YELLOW}[loop] -> CLOSE SHORT  score={score:+.3f} > {short_exit:+.3f}  pnl=${pnl:+.2f}{Style.RESET_ALL}")
                    close_position(symbol)
                    # Check if we should immediately open LONG
                    if score > long_entry:
                        print(f"{Fore.GREEN}[loop] -> OPEN LONG ${position_usd:.0f}  score={score:+.3f} > {long_entry:+.3f}{Style.RESET_ALL}")
                        order_id = open_long(symbol, score, position_usd)
                        if order_id:
                            qty = position_usd / current_price
                            open_trade_id = await write_trade_open(symbol, "long", qty, current_price, score, order_id, now)
                else:
                    print(f"[loop] -> HOLD SHORT  score={score:+.3f} <= {short_exit:+.3f}")

            else:
                # No position - check for entry signals
                # Calculate stop loss distance from channel spread
                stop_distance = None
                if channel_info:
                    spread = channel_info.get('resistance_price', 0) - channel_info.get('support_price', 0)
                    if spread > 0:
                        stop_distance = spread / 2  # Half channel spread

                if score > long_entry:
                    print(f"{Fore.GREEN}[loop] -> OPEN LONG ${position_usd:.0f}  score={score:+.3f} > {long_entry:+.3f}{Style.RESET_ALL}")
                    order_id = open_long(symbol, score, position_usd)
                    if order_id:
                        qty = int(position_usd / current_price)
                        open_trade_id = await write_trade_open(symbol, "long", qty, current_price, score, order_id, now)
                        # Submit stop loss
                        if stop_distance and qty > 0:
                            stop_price = current_price - stop_distance
                            print(f"{Fore.YELLOW}[loop] -> STOP LOSS @ ${stop_price:.2f} (spread/2=${stop_distance:.2f}){Style.RESET_ALL}")
                            submit_stop_loss(symbol, "long", qty, stop_price)

                elif score < short_entry and settings.ASSET_CLASS != "crypto":
                    print(f"{Fore.RED}[loop] -> OPEN SHORT ${position_usd:.0f}  score={score:+.3f} < {short_entry:+.3f}{Style.RESET_ALL}")
                    order_id = open_short(symbol, score, position_usd)
                    if order_id:
                        qty = int(position_usd / current_price)
                        open_trade_id = await write_trade_open(symbol, "short", qty, current_price, score, order_id, now)
                        # Submit stop loss
                        if stop_distance and qty > 0:
                            stop_price = current_price + stop_distance
                            print(f"{Fore.YELLOW}[loop] -> STOP LOSS @ ${stop_price:.2f} (spread/2=${stop_distance:.2f}){Style.RESET_ALL}")
                            submit_stop_loss(symbol, "short", qty, stop_price)
                else:
                    print(f"[loop] -> NO POSITION  score={score:+.3f} (need >{long_entry:+.3f} for long, <{short_entry:+.3f} for short)")

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
