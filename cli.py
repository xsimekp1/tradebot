"""
CLI entry point for manual operations.

Usage:
  python cli.py intraday          # run intraday trading loop
  python cli.py nightly           # run weight mutation job
  python cli.py status            # show current equity, weights, last trade
  python cli.py backtest --days 7 # PnL summary from DB
"""
import argparse
import asyncio
from datetime import datetime, timezone, timedelta

from colorama import Fore, Style, init as colorama_init

colorama_init(autoreset=True)


async def cmd_intraday():
    from src.engine.loop import run_intraday_loop
    await run_intraday_loop()


async def cmd_nightly():
    from src.evolution.mutator import run_nightly_mutation
    weights = await run_nightly_mutation()
    print(f"\n{Fore.GREEN}New weights:{Style.RESET_ALL}")
    for k, v in weights.items():
        print(f"  {k}: {v:.4f}")


async def cmd_status():
    from sqlalchemy import select
    from src.db.session import AsyncSessionLocal
    from src.models.equity import EquityCurve
    from src.models.trade import Trade
    from src.models.weights import SignalWeights
    from src.engine.executor import get_account, get_current_position
    from src.config import settings

    print(f"\n{Fore.CYAN}=== TradeBot Status ==={Style.RESET_ALL}")
    print(f"Symbol: {settings.SYMBOL}")

    # Alpaca account
    try:
        account = get_account()
        print(f"\n{Fore.GREEN}Account:{Style.RESET_ALL}")
        print(f"  Equity:          ${account['equity']:,.2f}")
        print(f"  Cash:            ${account['cash']:,.2f}")
        print(f"  Portfolio Value: ${account['portfolio_value']:,.2f}")
        print(f"  Daily PnL:       ${account['equity'] - account['last_equity']:+,.2f}")
    except Exception as e:
        print(f"{Fore.RED}  Could not fetch Alpaca account: {e}{Style.RESET_ALL}")

    # Current position
    try:
        pos = get_current_position(settings.SYMBOL)
        if pos:
            print(f"\n{Fore.YELLOW}Open Position:{Style.RESET_ALL}")
            print(f"  Side:        {pos['side']}")
            print(f"  Qty:         {pos['qty']}")
            print(f"  Entry Price: ${pos['avg_entry_price']:,.2f}")
        else:
            print(f"\n  No open position for {settings.SYMBOL}")
    except Exception as e:
        print(f"{Fore.RED}  Could not fetch position: {e}{Style.RESET_ALL}")

    async with AsyncSessionLocal() as db:
        # Active weights
        result = await db.execute(
            select(SignalWeights)
            .where(SignalWeights.is_active == True)
            .order_by(SignalWeights.created_at.desc())
        )
        active_weights = result.scalars().first()
        if active_weights:
            print(f"\n{Fore.CYAN}Active Weights (v{active_weights.version}):{Style.RESET_ALL}")
            for k, v in active_weights.weights.items():
                print(f"  {k}: {float(v):.4f}")
        else:
            print(f"\n  No weights in DB (using defaults)")

        # Last trade
        result = await db.execute(
            select(Trade).order_by(Trade.created_at.desc()).limit(1)
        )
        last_trade = result.scalars().first()
        if last_trade:
            print(f"\n{Fore.YELLOW}Last Trade:{Style.RESET_ALL}")
            print(f"  Symbol:    {last_trade.symbol}")
            print(f"  Side:      {last_trade.side}")
            print(f"  PnL:       {f'${float(last_trade.pnl):+,.2f}' if last_trade.pnl else 'open'}")
            print(f"  Opened:    {last_trade.opened_at}")
        else:
            print(f"\n  No trades in DB yet")

        # Latest equity snapshot
        result = await db.execute(
            select(EquityCurve).order_by(EquityCurve.timestamp.desc()).limit(1)
        )
        last_equity = result.scalars().first()
        if last_equity:
            print(f"\n{Fore.CYAN}Last DB Equity Snapshot:{Style.RESET_ALL}")
            print(f"  Total Equity: ${float(last_equity.total_equity):,.2f}")
            print(f"  Timestamp:    {last_equity.timestamp}")


async def cmd_backtest(days: int):
    from sqlalchemy import select
    from src.db.session import AsyncSessionLocal
    from src.models.trade import Trade

    since = datetime.now(timezone.utc) - timedelta(days=days)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Trade).where(
                Trade.closed_at.isnot(None),
                Trade.closed_at >= since,
            ).order_by(Trade.closed_at)
        )
        trades = result.scalars().all()

    if not trades:
        print(f"No closed trades in the last {days} days.")
        return

    total_pnl = sum(float(t.pnl) for t in trades if t.pnl)
    winners = [t for t in trades if t.pnl and float(t.pnl) > 0]
    losers = [t for t in trades if t.pnl and float(t.pnl) <= 0]

    print(f"\n{Fore.CYAN}=== Backtest ({days}d) ==={Style.RESET_ALL}")
    print(f"  Total trades:  {len(trades)}")
    print(f"  Winners:       {len(winners)}")
    print(f"  Losers:        {len(losers)}")
    win_rate = len(winners) / len(trades) * 100 if trades else 0
    print(f"  Win rate:      {win_rate:.1f}%")
    print(f"  Total PnL:     ${total_pnl:+,.2f}")
    if winners:
        avg_win = sum(float(t.pnl) for t in winners) / len(winners)
        print(f"  Avg win:       ${avg_win:+,.2f}")
    if losers:
        avg_loss = sum(float(t.pnl) for t in losers) / len(losers)
        print(f"  Avg loss:      ${avg_loss:+,.2f}")


def main():
    parser = argparse.ArgumentParser(description="TradeBot CLI")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("intraday", help="Run intraday trading loop")
    subparsers.add_parser("nightly", help="Run nightly weight mutation")
    subparsers.add_parser("status", help="Show current status")

    backtest_parser = subparsers.add_parser("backtest", help="PnL summary from DB")
    backtest_parser.add_argument("--days", type=int, default=7, help="Lookback days")

    args = parser.parse_args()

    if args.command == "intraday":
        asyncio.run(cmd_intraday())
    elif args.command == "nightly":
        asyncio.run(cmd_nightly())
    elif args.command == "status":
        asyncio.run(cmd_status())
    elif args.command == "backtest":
        asyncio.run(cmd_backtest(args.days))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
