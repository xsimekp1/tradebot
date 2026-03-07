"""
Walk-forward validation:
  1. Fetch (train_weeks + 1) weeks of data
  2. Optimize weights on train window
  3. Evaluate best weights out-of-sample on last 7 days
  4. Compare in-sample vs out-of-sample

Usage:
  python scripts/walk_forward.py --train-weeks 2
  python scripts/walk_forward.py --train-weeks 3
  python scripts/walk_forward.py --train-weeks 4
  python scripts/walk_forward.py --train-weeks 2 3 4   # all at once
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
from colorama import Fore, Style, init as colorama_init
from datetime import datetime, timezone, timedelta

from src.config import settings
from src.signals import ALL_SIGNALS
from src.engine.scoring import DEFAULT_WEIGHTS

colorama_init(autoreset=True)

LOOKBACK = 100
TEST_DAYS = 7


# ─── Shared helpers (same as backtest_multi) ─────────────────────────────────

def fetch_bars(symbol: str, days: int) -> pd.DataFrame:
    from alpaca.data.timeframe import TimeFrame
    is_crypto = "/" in symbol
    end = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    start = end - timedelta(days=days + (0 if is_crypto else 4))

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
    return df[cols].sort_index()


def compute_signal_matrix(df: pd.DataFrame) -> np.ndarray:
    n = len(df)
    matrix = np.zeros((n, len(ALL_SIGNALS)), dtype=np.float32)
    for i in range(LOOKBACK, n):
        window = df.iloc[i - LOOKBACK: i + 1]
        for j, sig in enumerate(ALL_SIGNALS):
            matrix[i, j] = sig.safe_compute(window)
    return matrix


def simulate(df, matrix, weights, long_thr, short_thr, pos_size, allow_short=True):
    weight_sum = np.sum(np.abs(weights))
    scores = (matrix @ weights) / weight_sum if weight_sum > 0 else np.zeros(len(df))
    prices = df["close"].values
    capital = pos_size * 10
    cash = capital
    position = None
    trades = []
    equity = np.full(len(df), capital, dtype=np.float64)

    for i in range(LOOKBACK, len(df)):
        price = prices[i]
        score = scores[i]

        if position is None:
            if score > long_thr:
                qty = pos_size / price
                cash -= pos_size
                position = {"side": "long", "entry": price, "qty": qty, "idx": i}
            elif allow_short and score < short_thr:
                qty = pos_size / price
                cash += pos_size
                position = {"side": "short", "entry": price, "qty": qty, "idx": i}
        elif position["side"] == "long":
            if score < short_thr:
                pnl = (price - position["entry"]) * position["qty"]
                cash += pos_size + pnl
                trades.append(pnl)
                position = None
        elif position["side"] == "short":
            if score > long_thr:
                pnl = (position["entry"] - price) * position["qty"]
                cash -= pos_size - pnl
                trades.append(pnl)
                position = None

        if position is not None:
            pos_val = position["qty"] * price if position["side"] == "long" \
                else position["qty"] * (2 * position["entry"] - price)
            equity[i] = cash + pos_val
        else:
            equity[i] = cash

    if position is not None:
        last_price = prices[-1]
        pnl = (last_price - position["entry"]) * position["qty"] \
            if position["side"] == "long" \
            else (position["entry"] - last_price) * position["qty"]
        trades.append(pnl)

    eq = equity[LOOKBACK:]
    final = eq[-1] if len(eq) > 0 else capital
    pnls = np.array(trades) if trades else np.array([0.0])
    winners = pnls[pnls > 0]
    losers = pnls[pnls <= 0]

    max_eq = np.maximum.accumulate(eq)
    dd = (eq - max_eq) / np.where(max_eq > 0, max_eq, 1) * 100

    bars_per_day = 1440
    daily_eq = eq[::bars_per_day]
    daily_ret = np.diff(daily_eq) / daily_eq[:-1] if len(daily_eq) > 1 else np.array([0.0])
    std = daily_ret.std()
    sharpe = (daily_ret.mean() / std * (252 ** 0.5)) if std > 0 and not np.isnan(std) else 0.0

    return {
        "return_pct": (final - capital) / capital * 100,
        "total_pnl": final - capital,
        "num_trades": len(pnls),
        "win_rate": len(winners) / len(pnls) * 100 if len(pnls) > 0 else 0,
        "profit_factor": abs(winners.sum() / losers.sum()) if losers.sum() != 0 else float("inf"),
        "max_dd": dd.min(),
        "sharpe": sharpe,
        "avg_win": winners.mean() if len(winners) > 0 else 0,
        "avg_loss": losers.mean() if len(losers) > 0 else 0,
    }


def optimize(df, matrix, trials, long_thr, short_thr, pos_size, allow_short):
    n_signals = len(ALL_SIGNALS)
    results = []
    for _ in range(trials):
        raw = np.random.dirichlet(np.ones(n_signals))
        if np.random.random() < 0.4:
            n_zero = np.random.randint(1, min(4, n_signals))
            raw[np.random.choice(n_signals, n_zero, replace=False)] = 0.0
            if raw.sum() > 0:
                raw /= raw.sum()
        r = simulate(df, matrix, raw, long_thr, short_thr, pos_size, allow_short)
        results.append((raw.copy(), r))
    results.sort(key=lambda x: (x[1]["sharpe"], x[1]["return_pct"]), reverse=True)
    return results


def fmt_stat(label, value, color=None, suffix=""):
    c = color or Style.RESET_ALL
    return f"    {label:<22} {c}{value}{suffix}{Style.RESET_ALL}"


def print_comparison(train_weeks, train_r, test_r, weights):
    signal_names = [s.name for s in ALL_SIGNALS]

    def color_val(v):
        return Fore.GREEN if v >= 0 else Fore.RED

    print(f"\n{Fore.CYAN}{'=' * 70}")
    print(f"  Walk-Forward: Train {train_weeks}w → Test {TEST_DAYS}d out-of-sample")
    print(f"{'=' * 70}{Style.RESET_ALL}")

    # Weights
    print(f"\n  {Fore.YELLOW}Optimized weights:{Style.RESET_ALL}")
    for i, name in enumerate(signal_names):
        w = weights[i]
        if w < 0.01:
            continue
        bar = int(w * 50)
        print(f"    {name:<12} {'|' * bar} {w:.3f}")

    # Side-by-side comparison
    print(f"\n  {'Metric':<24} {'IN-SAMPLE (train)':>22} {'OUT-OF-SAMPLE (test)':>22}")
    print(f"  {'-' * 68}")

    def row(label, train_v, test_v, fmt="{:.2f}", suffix=""):
        tv = fmt.format(train_v) + suffix
        ov = fmt.format(test_v) + suffix
        tc = color_val(train_v) if suffix in ("%", "$") else ""
        oc = color_val(test_v) if suffix in ("%", "$") else ""
        print(f"  {label:<24} {tc}{tv:>22}{Style.RESET_ALL} {oc}{ov:>22}{Style.RESET_ALL}")

    row("Return", train_r["return_pct"], test_r["return_pct"], suffix="%")
    row("Total P&L ($10k)", train_r["total_pnl"], test_r["total_pnl"], fmt="${:+,.2f}", suffix="$")
    row("Trades", train_r["num_trades"], test_r["num_trades"], fmt="{:.0f}")
    row("Win Rate", train_r["win_rate"], test_r["win_rate"], suffix="%")
    row("Profit Factor", train_r["profit_factor"], test_r["profit_factor"])
    row("Max Drawdown", train_r["max_dd"], test_r["max_dd"], suffix="%")
    row("Sharpe", train_r["sharpe"], test_r["sharpe"])

    # Verdict
    print()
    held_up = test_r["sharpe"] > 1.0 and test_r["return_pct"] > 0
    degraded = test_r["sharpe"] < train_r["sharpe"] * 0.4
    if held_up and not degraded:
        verdict = f"{Fore.GREEN}PASS — strategy generalizes well{Style.RESET_ALL}"
    elif test_r["return_pct"] > 0:
        verdict = f"{Fore.YELLOW}PARTIAL — profitable but weaker out-of-sample{Style.RESET_ALL}"
    else:
        verdict = f"{Fore.RED}FAIL — strategy did not generalize (overfit){Style.RESET_ALL}"
    print(f"  Verdict: {verdict}")
    print(f"{Fore.CYAN}{'=' * 70}{Style.RESET_ALL}\n")


# ─── Main ─────────────────────────────────────────────────────────────────────

def run_walk_forward(symbol, train_weeks, long_thr, short_thr, pos_size, allow_short, trials):
    total_days = train_weeks * 7 + TEST_DAYS

    print(f"\n{Fore.CYAN}Walk-forward: {symbol} | train={train_weeks}w | test={TEST_DAYS}d | {trials} trials{Style.RESET_ALL}")

    # Fetch all data
    print(f"Fetching {total_days} days of data...")
    df_all = fetch_bars(symbol, total_days)

    # Split at TEST_DAYS boundary
    split_time = df_all.index[-1] - timedelta(days=TEST_DAYS)
    df_train = df_all[df_all.index <= split_time]
    df_test = df_all[df_all.index > split_time]

    print(f"Train: {len(df_train):,} bars ({df_train.index[0].strftime('%m-%d')} to {df_train.index[-1].strftime('%m-%d')})")
    print(f"Test:  {len(df_test):,} bars  ({df_test.index[0].strftime('%m-%d')} to {df_test.index[-1].strftime('%m-%d')})")

    # Compute signal matrices
    print(f"Computing signals on train set", end="", flush=True)
    mat_train = compute_signal_matrix(df_train)
    print(" done")

    print(f"Computing signals on test set", end="", flush=True)
    mat_test = compute_signal_matrix(df_test)
    print(" done")

    # Optimize on train
    print(f"Optimizing {trials} trials on train set...")
    opt_results = optimize(df_train, mat_train, trials, long_thr, short_thr, pos_size, allow_short)
    best_weights, train_stats = opt_results[0]

    # Evaluate best weights on test (out-of-sample)
    test_stats = simulate(df_test, mat_test, best_weights, long_thr, short_thr, pos_size, allow_short)

    print_comparison(train_weeks, train_stats, test_stats, best_weights)

    return best_weights, train_stats, test_stats


def main():
    parser = argparse.ArgumentParser(description="Walk-forward validation")
    parser.add_argument("--symbol", default=settings.SYMBOL)
    parser.add_argument("--train-weeks", nargs="+", type=int, default=[2, 3, 4],
                        help="Training window(s) in weeks, e.g. --train-weeks 2 3 4")
    parser.add_argument("--long-threshold", type=float, default=0.15)
    parser.add_argument("--short-threshold", type=float, default=-0.15)
    parser.add_argument("--position-size", type=float, default=settings.POSITION_SIZE_USD)
    parser.add_argument("--no-short", action="store_true")
    parser.add_argument("--trials", type=int, default=300)
    parser.add_argument("--save", action="store_true", help="Save results to DB (visible on dashboard)")
    args = parser.parse_args()

    allow_short = not args.no_short
    all_results = []

    for tw in args.train_weeks:
        best_w, train_r, test_r = run_walk_forward(
            symbol=args.symbol,
            train_weeks=tw,
            long_thr=args.long_threshold,
            short_thr=args.short_threshold,
            pos_size=args.position_size,
            allow_short=allow_short,
            trials=args.trials,
        )
        all_results.append((tw, best_w, train_r, test_r))
        if args.save:
            from src.db.backtest_writer import save_backtest
            signal_names = [s.name for s in ALL_SIGNALS]
            save_backtest({
                "symbol": args.symbol,
                "strategy": "walk_forward",
                "train_days": tw * 7,
                "test_days": TEST_DAYS,
                "weights": {signal_names[i]: round(float(best_w[i]), 4) for i in range(len(signal_names))},
                "params": {"trials": args.trials, "long_thr": args.long_threshold, "short_thr": args.short_threshold, "allow_short": allow_short},
                "in_sample": {k: round(float(v), 4) for k, v in train_r.items()},
                "out_of_sample": {k: round(float(v), 4) for k, v in test_r.items()},
            })
            print(f"  [saved walk_forward {tw}w to DB]")

    # Summary across all windows
    if len(all_results) > 1:
        signal_names = [s.name for s in ALL_SIGNALS]
        print(f"\n{Fore.CYAN}{'=' * 70}")
        print(f"  Summary across all train windows — OUT-OF-SAMPLE (last {TEST_DAYS} days)")
        print(f"{'=' * 70}{Style.RESET_ALL}")
        print(f"  {'Train':>8} {'Return':>9} {'WinRate':>9} {'Sharpe':>9} {'MaxDD':>9}  Verdict")
        print(f"  {'-' * 65}")

        for tw, w, tr, te in all_results:
            held = te["sharpe"] > 1.0 and te["return_pct"] > 0
            degraded = te["sharpe"] < tr["sharpe"] * 0.4
            if held and not degraded:
                v = f"{Fore.GREEN}PASS{Style.RESET_ALL}"
            elif te["return_pct"] > 0:
                v = f"{Fore.YELLOW}PARTIAL{Style.RESET_ALL}"
            else:
                v = f"{Fore.RED}FAIL{Style.RESET_ALL}"
            rc = Fore.GREEN if te["return_pct"] > 0 else Fore.RED
            print(
                f"  {tw}w train  "
                f"{rc}{te['return_pct']:>+8.2f}%{Style.RESET_ALL}  "
                f"{te['win_rate']:>8.1f}%  "
                f"{te['sharpe']:>9.2f}  "
                f"{te['max_dd']:>+8.2f}%  {v}"
            )

        # Average weights across all windows
        avg_w = np.mean([w for _, w, _, _ in all_results], axis=0)
        avg_w /= avg_w.sum()
        print(f"\n  {Fore.YELLOW}Averaged weights across all train windows:{Style.RESET_ALL}")
        for i, name in enumerate(signal_names):
            if avg_w[i] > 0.01:
                bar = int(avg_w[i] * 40)
                print(f"    {name:<12} {'|' * bar} {avg_w[i]:.3f}")

        w_args = " ".join(f"{signal_names[i]}={avg_w[i]:.4f}" for i in range(len(signal_names)) if avg_w[i] > 0.01)
        print(f"\n  {Fore.YELLOW}Use these averaged weights:{Style.RESET_ALL}")
        print(f"  python scripts/backtest_multi.py --weights {w_args} --long-threshold {args.long_threshold}")
        print()


if __name__ == "__main__":
    main()
