"""
RSI single-signal paper backtest using Alpaca historical 1-min bars.

Usage:
  python scripts/backtest_rsi.py              # 7 days, SPY
  python scripts/backtest_rsi.py --days 14 --symbol SPY
  python scripts/backtest_rsi.py --rsi-period 14 --buy-level 30 --sell-level 70
"""
import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd
import ta
from colorama import Fore, Style, init as colorama_init

from src.config import settings

colorama_init(autoreset=True)


def fetch_historical_bars(symbol: str, days: int) -> pd.DataFrame:
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    client = StockHistoricalDataClient(
        api_key=settings.ALPACA_API_KEY,
        secret_key=settings.ALPACA_SECRET_KEY,
    )

    # Go back a bit extra to account for weekends/holidays
    end = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    start = end - timedelta(days=days + 4)

    print(f"Fetching {symbol} 1-min bars from {start.date()} to {end.date()}...")

    req = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Minute,
        start=start,
        end=end,
        feed="iex",
    )
    bars = client.get_stock_bars(req)
    df = bars.df

    if df.empty:
        print(f"{Fore.RED}No data returned.{Style.RESET_ALL}")
        sys.exit(1)

    if isinstance(df.index, pd.MultiIndex):
        df = df.xs(symbol, level=0)

    df = df.rename(columns=str.lower)
    df = df[["open", "high", "low", "close", "volume"]].copy()
    df = df.sort_index()

    # Keep only last `days` calendar days
    cutoff = end - timedelta(days=days)
    df = df[df.index >= cutoff]

    print(f"Got {len(df):,} bars | {df.index[0]} to {df.index[-1]}")
    return df


def run_backtest(
    df: pd.DataFrame,
    symbol: str,
    rsi_period: int,
    buy_level: float,
    sell_level: float,
    position_size_usd: float,
    allow_short: bool,
) -> dict:
    """
    Simulate RSI strategy on 1-min bars.
    Returns stats dict.
    """
    # Compute RSI
    df = df.copy()
    df["rsi"] = ta.momentum.RSIIndicator(close=df["close"], window=rsi_period).rsi()
    df = df.dropna(subset=["rsi"])

    equity = position_size_usd * 10  # starting capital
    cash = equity
    position = None  # None | {"side": "long"|"short", "entry": float, "qty": float, "entry_time": ts}
    trades = []
    equity_curve = []

    for ts, row in df.iterrows():
        price = row["close"]
        rsi = row["rsi"]

        # --- Entry logic ---
        if position is None:
            if rsi < buy_level:
                qty = position_size_usd / price
                cash -= position_size_usd
                position = {"side": "long", "entry": price, "qty": qty, "entry_time": ts}

            elif allow_short and rsi > sell_level:
                qty = position_size_usd / price
                cash += position_size_usd  # short proceeds
                position = {"side": "short", "entry": price, "qty": qty, "entry_time": ts}

        # --- Exit logic ---
        elif position["side"] == "long":
            if rsi > sell_level:
                pnl = (price - position["entry"]) * position["qty"]
                cash += position_size_usd + pnl
                trades.append({
                    "side": "long",
                    "entry": position["entry"],
                    "exit": price,
                    "qty": position["qty"],
                    "pnl": pnl,
                    "entry_time": position["entry_time"],
                    "exit_time": ts,
                    "duration_min": int((ts - position["entry_time"]).total_seconds() / 60),
                    "rsi_entry": df.loc[position["entry_time"], "rsi"] if position["entry_time"] in df.index else None,
                    "rsi_exit": rsi,
                })
                position = None

        elif position["side"] == "short":
            if rsi < buy_level:
                pnl = (position["entry"] - price) * position["qty"]
                cash -= position_size_usd - pnl  # return borrowed + profit
                trades.append({
                    "side": "short",
                    "entry": position["entry"],
                    "exit": price,
                    "qty": position["qty"],
                    "pnl": pnl,
                    "entry_time": position["entry_time"],
                    "exit_time": ts,
                    "duration_min": int((ts - position["entry_time"]).total_seconds() / 60),
                    "rsi_entry": df.loc[position["entry_time"], "rsi"] if position["entry_time"] in df.index else None,
                    "rsi_exit": rsi,
                })
                position = None

        # Mark-to-market equity
        if position is not None:
            if position["side"] == "long":
                pos_value = position["qty"] * price
            else:
                pos_value = position["qty"] * (2 * position["entry"] - price)  # short P&L
            total_equity = cash + pos_value
        else:
            total_equity = cash

        equity_curve.append({"ts": ts, "equity": total_equity, "rsi": rsi})

    # Close open position at last price if any
    if position is not None:
        last_price = df["close"].iloc[-1]
        last_ts = df.index[-1]
        if position["side"] == "long":
            pnl = (last_price - position["entry"]) * position["qty"]
        else:
            pnl = (position["entry"] - last_price) * position["qty"]
        trades.append({
            "side": position["side"] + " (open→close)",
            "entry": position["entry"],
            "exit": last_price,
            "qty": position["qty"],
            "pnl": pnl,
            "entry_time": position["entry_time"],
            "exit_time": last_ts,
            "duration_min": int((last_ts - position["entry_time"]).total_seconds() / 60),
            "rsi_entry": None,
            "rsi_exit": df["rsi"].iloc[-1],
        })

    eq = pd.DataFrame(equity_curve).set_index("ts")
    trades_df = pd.DataFrame(trades) if trades else pd.DataFrame()

    # Stats
    final_equity = eq["equity"].iloc[-1] if not eq.empty else equity
    total_return = (final_equity - equity) / equity * 100
    max_equity = eq["equity"].cummax()
    drawdown = ((eq["equity"] - max_equity) / max_equity * 100)
    max_dd = drawdown.min()

    winners = trades_df[trades_df["pnl"] > 0] if not trades_df.empty else pd.DataFrame()
    losers = trades_df[trades_df["pnl"] <= 0] if not trades_df.empty else pd.DataFrame()

    daily_returns = eq["equity"].resample("D").last().pct_change().dropna()
    sharpe = (daily_returns.mean() / daily_returns.std() * (252 ** 0.5)) if len(daily_returns) > 1 and daily_returns.std() > 0 else 0

    return {
        "starting_capital": equity,
        "final_equity": final_equity,
        "total_return_pct": total_return,
        "total_pnl": final_equity - equity,
        "num_trades": len(trades_df),
        "num_winners": len(winners),
        "num_losers": len(losers),
        "win_rate": len(winners) / len(trades_df) * 100 if len(trades_df) > 0 else 0,
        "avg_win": winners["pnl"].mean() if len(winners) > 0 else 0,
        "avg_loss": losers["pnl"].mean() if len(losers) > 0 else 0,
        "profit_factor": abs(winners["pnl"].sum() / losers["pnl"].sum()) if len(losers) > 0 and losers["pnl"].sum() != 0 else float("inf"),
        "max_drawdown_pct": max_dd,
        "sharpe_ratio": sharpe,
        "avg_duration_min": trades_df["duration_min"].mean() if not trades_df.empty else 0,
        "trades": trades_df,
        "equity_curve": eq,
    }


def print_results(results: dict, symbol: str, rsi_period: int, buy_level: float, sell_level: float):
    r = results
    win_color = Fore.GREEN if r["total_return_pct"] > 0 else Fore.RED

    print(f"\n{Fore.CYAN}{'=' * 60}")
    print(f"  RSI({rsi_period}) Backtest — {symbol}")
    print(f"  Buy < {buy_level} | Sell > {sell_level}")
    print(f"{'=' * 60}{Style.RESET_ALL}\n")

    print(f"{'Starting Capital:':<30} ${r['starting_capital']:>12,.2f}")
    print(f"{'Final Equity:':<30} {win_color}${r['final_equity']:>12,.2f}{Style.RESET_ALL}")
    print(f"{'Total Return:':<30} {win_color}{r['total_return_pct']:>+11.2f}%{Style.RESET_ALL}")
    print(f"{'Total P&L:':<30} {win_color}${r['total_pnl']:>+11.2f}{Style.RESET_ALL}")
    print()
    print(f"{'Trades:':<30} {r['num_trades']:>12}")
    print(f"{'Winners / Losers:':<30} {r['num_winners']:>5} / {r['num_losers']:<5}")
    print(f"{'Win Rate:':<30} {r['win_rate']:>11.1f}%")
    print(f"{'Avg Win:':<30} ${r['avg_win']:>+11.2f}")
    print(f"{'Avg Loss:':<30} ${r['avg_loss']:>+11.2f}")
    print(f"{'Profit Factor:':<30} {r['profit_factor']:>12.2f}")
    print(f"{'Avg Trade Duration:':<30} {r['avg_duration_min']:>9.0f} min")
    print()
    dd_color = Fore.RED if r["max_drawdown_pct"] < -5 else Fore.YELLOW
    print(f"{'Max Drawdown:':<30} {dd_color}{r['max_drawdown_pct']:>+11.2f}%{Style.RESET_ALL}")
    print(f"{'Sharpe Ratio (daily):':<30} {r['sharpe_ratio']:>12.2f}")

    if not r["trades"].empty:
        print(f"\n{Fore.CYAN}Last 10 Trades:{Style.RESET_ALL}")
        print(f"  {'Side':<8} {'Entry':>8} {'Exit':>8} {'PnL':>9} {'Dur(min)':>10}")
        print(f"  {'-'*8} {'-'*8} {'-'*8} {'-'*9} {'-'*10}")
        for _, t in r["trades"].tail(10).iterrows():
            pnl_color = Fore.GREEN if t["pnl"] > 0 else Fore.RED
            print(
                f"  {str(t['side']):<8} "
                f"${t['entry']:>7.2f} "
                f"${t['exit']:>7.2f} "
                f"{pnl_color}${t['pnl']:>+8.2f}{Style.RESET_ALL} "
                f"{int(t['duration_min']):>10}"
            )

    print(f"\n{Fore.CYAN}{'=' * 60}{Style.RESET_ALL}\n")


def main():
    parser = argparse.ArgumentParser(description="RSI single-signal backtest")
    parser.add_argument("--symbol", default=settings.SYMBOL)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--rsi-period", type=int, default=14)
    parser.add_argument("--buy-level", type=float, default=35)
    parser.add_argument("--sell-level", type=float, default=65)
    parser.add_argument("--position-size", type=float, default=settings.POSITION_SIZE_USD)
    parser.add_argument("--no-short", action="store_true", help="Long-only strategy")
    args = parser.parse_args()

    df = fetch_historical_bars(args.symbol, args.days)
    results = run_backtest(
        df=df,
        symbol=args.symbol,
        rsi_period=args.rsi_period,
        buy_level=args.buy_level,
        sell_level=args.sell_level,
        position_size_usd=args.position_size,
        allow_short=not args.no_short,
    )
    print_results(results, args.symbol, args.rsi_period, args.buy_level, args.sell_level)


if __name__ == "__main__":
    main()
