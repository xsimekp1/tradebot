"""
Multi-signal backtest with optional weight optimization.

Precomputes all signals as a matrix, then simulates any weight combination
instantly via matrix multiply — no redundant bar processing.

Usage:
  # Default weights, BTC/USD, 7 days
  python scripts/backtest_multi.py

  # Custom weights
  python scripts/backtest_multi.py --weights momentum=0.4 rsi=0.3 bollinger=0.3

  # Only specific signals
  python scripts/backtest_multi.py --only rsi bollinger vwap

  # Random search: try 500 weight combinations, show top 10
  python scripts/backtest_multi.py --optimize --trials 500

  # Optimize on ETH, 14 days
  python scripts/backtest_multi.py --symbol ETH/USD --days 14 --optimize --trials 1000
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import ta
from colorama import Fore, Style, init as colorama_init
from datetime import datetime, timezone, timedelta

from src.config import settings
from src.signals import ALL_SIGNALS
from src.engine.scoring import DEFAULT_WEIGHTS

colorama_init(autoreset=True)

LOOKBACK = 100  # bars fed to each signal computation


# ─── Data fetching ────────────────────────────────────────────────────────────

def fetch_bars(symbol: str, days: int) -> pd.DataFrame:
    from alpaca.data.timeframe import TimeFrame
    is_crypto = "/" in symbol or settings.ASSET_CLASS == "crypto"
    end = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    start = end - timedelta(days=days + (0 if is_crypto else 4))

    print(f"Fetching {symbol} 1-min bars ({days}d)...")

    if is_crypto:
        from alpaca.data.historical import CryptoHistoricalDataClient
        from alpaca.data.requests import CryptoBarsRequest
        client = CryptoHistoricalDataClient(
            api_key=settings.ALPACA_API_KEY, secret_key=settings.ALPACA_SECRET_KEY
        )
        bars = client.get_crypto_bars(
            CryptoBarsRequest(symbol_or_symbols=symbol, timeframe=TimeFrame.Minute, start=start, end=end)
        )
    else:
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockBarsRequest
        client = StockHistoricalDataClient(
            api_key=settings.ALPACA_API_KEY, secret_key=settings.ALPACA_SECRET_KEY
        )
        bars = client.get_stock_bars(
            StockBarsRequest(symbol_or_symbols=symbol, timeframe=TimeFrame.Minute, start=start, end=end, feed="iex")
        )

    df = bars.df
    if df.empty:
        print(f"{Fore.RED}No data.{Style.RESET_ALL}")
        sys.exit(1)
    if isinstance(df.index, pd.MultiIndex):
        df = df.xs(symbol, level=0)
    df = df.rename(columns=str.lower)
    cols = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
    df = df[cols].sort_index()
    cutoff = end - timedelta(days=days)
    df = df[df.index >= cutoff]
    print(f"Got {len(df):,} bars | {df.index[0].strftime('%Y-%m-%d %H:%M')} to {df.index[-1].strftime('%Y-%m-%d %H:%M')}")
    return df


# ─── Signal matrix precomputation ────────────────────────────────────────────

def compute_signal_matrix(df: pd.DataFrame, signal_objects: list) -> np.ndarray:
    """
    Returns matrix of shape (n_bars, n_signals).
    Row i = signal values computed on bars[i-LOOKBACK : i+1].
    First LOOKBACK rows are 0 (insufficient data).
    """
    n = len(df)
    n_signals = len(signal_objects)
    matrix = np.zeros((n, n_signals), dtype=np.float32)

    print(f"Computing {n_signals} signals on {n:,} bars", end="", flush=True)

    for i in range(LOOKBACK, n):
        window = df.iloc[i - LOOKBACK: i + 1]
        for j, sig in enumerate(signal_objects):
            matrix[i, j] = sig.safe_compute(window)

        if i % 1000 == 0:
            print(".", end="", flush=True)

    print(f" done")
    return matrix


# ─── Simulation ───────────────────────────────────────────────────────────────

def simulate(
    df: pd.DataFrame,
    signal_matrix: np.ndarray,
    weights: np.ndarray,
    long_threshold: float,
    short_threshold: float,
    position_size_usd: float,
    allow_short: bool,
) -> dict:
    """
    Fast simulation: precomputed signals × weights → scores → trades.
    Returns stats dict.
    """
    weight_sum = np.sum(np.abs(weights))
    scores = (signal_matrix @ weights) / weight_sum if weight_sum > 0 else np.zeros(len(df))

    prices = df["close"].values
    capital = position_size_usd * 10
    cash = capital
    position = None  # {"side","entry","qty","idx"}
    trades = []
    equity_curve = np.full(len(df), capital, dtype=np.float64)

    for i in range(LOOKBACK, len(df)):
        price = prices[i]
        score = scores[i]

        if position is None:
            if score > long_threshold:
                qty = position_size_usd / price
                cash -= position_size_usd
                position = {"side": "long", "entry": price, "qty": qty, "idx": i}
            elif allow_short and score < short_threshold:
                qty = position_size_usd / price
                cash += position_size_usd
                position = {"side": "short", "entry": price, "qty": qty, "idx": i}

        elif position["side"] == "long":
            if score < short_threshold:
                pnl = (price - position["entry"]) * position["qty"]
                cash += position_size_usd + pnl
                trades.append({"side": "long", "pnl": pnl, "duration": i - position["idx"]})
                position = None

        elif position["side"] == "short":
            if score > long_threshold:
                pnl = (position["entry"] - price) * position["qty"]
                cash -= position_size_usd - pnl
                trades.append({"side": "short", "pnl": pnl, "duration": i - position["idx"]})
                position = None

        # Mark-to-market
        if position is not None:
            pos_val = position["qty"] * price if position["side"] == "long" \
                else position["qty"] * (2 * position["entry"] - price)
            equity_curve[i] = cash + pos_val
        else:
            equity_curve[i] = cash

    # Close open position at last price
    if position is not None:
        last_price = prices[-1]
        if position["side"] == "long":
            pnl = (last_price - position["entry"]) * position["qty"]
        else:
            pnl = (position["entry"] - last_price) * position["qty"]
        trades.append({"side": position["side"], "pnl": pnl, "duration": len(df) - position["idx"]})

    eq = equity_curve[LOOKBACK:]
    final_equity = eq[-1] if len(eq) > 0 else capital
    total_return = (final_equity - capital) / capital * 100

    max_eq = np.maximum.accumulate(eq)
    drawdowns = (eq - max_eq) / np.where(max_eq > 0, max_eq, 1) * 100
    max_dd = drawdowns.min()

    pnls = np.array([t["pnl"] for t in trades]) if trades else np.array([0.0])
    winners = pnls[pnls > 0]
    losers = pnls[pnls <= 0]
    win_rate = len(winners) / len(pnls) * 100 if len(pnls) > 0 else 0

    # Daily returns for Sharpe (resample by LOOKBACK-step approximation)
    bars_per_day = 390 if "/" not in df.index.name or True else 1440
    daily_eq = eq[::bars_per_day]
    daily_ret = np.diff(daily_eq) / daily_eq[:-1] if len(daily_eq) > 1 else np.array([0.0])
    std = daily_ret.std()
    sharpe = (daily_ret.mean() / std * (252 ** 0.5)) if std > 0 else 0.0

    profit_factor = abs(winners.sum() / losers.sum()) if losers.sum() != 0 else float("inf")

    return {
        "total_return_pct": total_return,
        "total_pnl": final_equity - capital,
        "final_equity": final_equity,
        "num_trades": len(trades),
        "win_rate": win_rate,
        "avg_win": winners.mean() if len(winners) > 0 else 0,
        "avg_loss": losers.mean() if len(losers) > 0 else 0,
        "profit_factor": profit_factor,
        "max_drawdown_pct": max_dd,
        "sharpe": sharpe,
        "avg_duration_bars": pnls.size and np.mean([t["duration"] for t in trades]) or 0,
    }


# ─── Print results ─────────────────────────────────────────────────────────────

def print_result(r: dict, label: str, weights_dict: dict, signal_names: list):
    win_color = Fore.GREEN if r["total_return_pct"] > 0 else Fore.RED
    print(f"\n{Fore.CYAN}{'=' * 62}")
    print(f"  {label}")
    print(f"{'=' * 62}{Style.RESET_ALL}")

    # Weights bar
    for name in signal_names:
        w = weights_dict.get(name, 0.0)
        bar = int(abs(w) * 40)
        color = Fore.CYAN if w > 0 else Fore.YELLOW
        print(f"  {name:<12} {color}{'|' * bar}{Style.RESET_ALL} {w:.3f}")

    print()
    print(f"  {'Return:':<22} {win_color}{r['total_return_pct']:>+8.2f}%{Style.RESET_ALL}  (${r['total_pnl']:>+,.2f})")
    print(f"  {'Trades:':<22} {r['num_trades']:>8}   Win rate: {r['win_rate']:.1f}%")
    print(f"  {'Avg win / loss:':<22} ${r['avg_win']:>+7.2f} / ${r['avg_loss']:>+7.2f}")
    print(f"  {'Profit factor:':<22} {r['profit_factor']:>8.2f}")
    print(f"  {'Max drawdown:':<22} {r['max_drawdown_pct']:>+8.2f}%")
    print(f"  {'Sharpe (daily):':<22} {r['sharpe']:>8.2f}")
    print(f"  {'Avg duration:':<22} {r['avg_duration_bars']:>7.0f} bars (~{r['avg_duration_bars']:.0f} min)")
    print(f"{Fore.CYAN}{'=' * 62}{Style.RESET_ALL}")


# ─── Optimization ─────────────────────────────────────────────────────────────

def optimize(
    df: pd.DataFrame,
    signal_matrix: np.ndarray,
    signal_names: list,
    signal_objects: list,
    trials: int,
    long_thr: float,
    short_thr: float,
    position_size: float,
    allow_short: bool,
    top_n: int = 10,
):
    print(f"\n{Fore.CYAN}Optimizing {trials} random weight vectors...{Style.RESET_ALL}")

    results = []
    n_signals = len(signal_names)

    for t in range(trials):
        # Random weights: Dirichlet gives weights that sum to 1
        raw = np.random.dirichlet(np.ones(n_signals))
        # Randomly zero out 1-3 signals to find sparse combos
        if np.random.random() < 0.4:
            n_zero = np.random.randint(1, min(4, n_signals))
            zero_idx = np.random.choice(n_signals, n_zero, replace=False)
            raw[zero_idx] = 0.0
            if raw.sum() > 0:
                raw /= raw.sum()

        r = simulate(df, signal_matrix, raw, long_thr, short_thr, position_size, allow_short)
        results.append({"weights": raw.copy(), "stats": r})

        if (t + 1) % 100 == 0:
            print(f"  {t + 1}/{trials} trials...", flush=True)

    # Sort by Sharpe, then by return
    results.sort(key=lambda x: (x["stats"]["sharpe"], x["stats"]["total_return_pct"]), reverse=True)

    print(f"\n{Fore.GREEN}Top {top_n} weight combinations (by Sharpe):{Style.RESET_ALL}\n")
    print(f"  {'#':<4} {'Sharpe':>7} {'Return':>8} {'WinRate':>8} {'Trades':>7} {'MaxDD':>8}  Weights")
    print(f"  {'-'*4} {'-'*7} {'-'*8} {'-'*8} {'-'*7} {'-'*8}  {'-'*40}")

    for i, res in enumerate(results[:top_n]):
        r = res["stats"]
        w = res["weights"]
        w_str = "  ".join(
            f"{signal_names[j]}={w[j]:.2f}" for j in np.argsort(w)[::-1] if w[j] > 0.01
        )
        color = Fore.GREEN if r["total_return_pct"] > 0 else Fore.RED
        print(
            f"  {i+1:<4} {r['sharpe']:>7.2f} "
            f"{color}{r['total_return_pct']:>+7.2f}%{Style.RESET_ALL} "
            f"{r['win_rate']:>7.1f}% "
            f"{r['num_trades']:>7} "
            f"{r['max_drawdown_pct']:>+7.2f}%  "
            f"{w_str}"
        )

    # Show best in detail
    best = results[0]
    best_weights_dict = {signal_names[j]: float(best["weights"][j]) for j in range(n_signals)}
    print_result(best["stats"], f"Best combo (trial #{1})", best_weights_dict, signal_names)

    # Print copy-pasteable weights for .env / cli
    print(f"\n{Fore.YELLOW}Best weights to use:{Style.RESET_ALL}")
    w_args = " ".join(f"{signal_names[j]}={best['weights'][j]:.4f}" for j in range(n_signals))
    print(f"  python scripts/backtest_multi.py --weights {w_args}")

    return results[:top_n]


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Multi-signal backtest with optional weight optimization")
    parser.add_argument("--symbol", default=settings.SYMBOL)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--long-threshold", type=float, default=settings.SCORE_LONG_THRESHOLD)
    parser.add_argument("--short-threshold", type=float, default=settings.SCORE_SHORT_THRESHOLD)
    parser.add_argument("--position-size", type=float, default=settings.POSITION_SIZE_USD)
    parser.add_argument("--no-short", action="store_true", help="Long-only (required for crypto)")
    parser.add_argument(
        "--only", nargs="+", metavar="SIGNAL",
        help="Use only these signals, e.g. --only rsi bollinger vwap",
    )
    parser.add_argument(
        "--weights", nargs="+", metavar="NAME=VALUE",
        help="Custom weights, e.g. --weights rsi=0.4 momentum=0.3 bollinger=0.3",
    )
    parser.add_argument("--optimize", action="store_true", help="Random search over weight combos")
    parser.add_argument("--trials", type=int, default=300, help="Number of optimization trials")
    parser.add_argument("--top", type=int, default=10, help="Show top N results")
    args = parser.parse_args()

    # Select signals
    signal_objects = ALL_SIGNALS
    if args.only:
        signal_objects = [s for s in ALL_SIGNALS if s.name in args.only]
        if not signal_objects:
            print(f"No matching signals. Available: {[s.name for s in ALL_SIGNALS]}")
            sys.exit(1)

    signal_names = [s.name for s in signal_objects]
    n_signals = len(signal_names)
    allow_short = not args.no_short

    # Fetch data
    df = fetch_bars(args.symbol, args.days)

    # Precompute signal matrix (done once, reused for all weight combos)
    matrix = compute_signal_matrix(df, signal_objects)

    if args.optimize:
        optimize(
            df, matrix, signal_names, signal_objects,
            trials=args.trials,
            long_thr=args.long_threshold,
            short_thr=args.short_threshold,
            position_size=args.position_size,
            allow_short=allow_short,
            top_n=args.top,
        )
        return

    # Parse custom weights or use defaults
    if args.weights:
        w_dict = {}
        for item in args.weights:
            name, val = item.split("=")
            w_dict[name.strip()] = float(val)
        weights = np.array([w_dict.get(n, 0.0) for n in signal_names])
        total = weights.sum()
        if total > 0:
            weights /= total
    else:
        weights = np.array([DEFAULT_WEIGHTS.get(n, 0.1) for n in signal_names])
        weights /= weights.sum()

    weights_dict = {signal_names[i]: float(weights[i]) for i in range(n_signals)}

    r = simulate(df, matrix, weights, args.long_threshold, args.short_threshold, args.position_size, allow_short)
    print_result(r, f"{args.symbol} | {args.days}d | {n_signals} signals", weights_dict, signal_names)


if __name__ == "__main__":
    main()
