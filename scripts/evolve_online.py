"""
Online strategy evolution via walk-forward backtesting.

Every N minutes:
  1. Load current active weights from DB (or defaults)
  2. Fetch 4 weeks train + last 7 days test of 1-min bars
  3. Generate M gentle mutations of current weights
  4. Backtest each mutation on the OOS (out-of-sample) test window
  5. Promote the best performer as the new active strategy

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
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from colorama import Fore, Style, init as colorama_init
from datetime import datetime, timezone, timedelta

from src.config import settings
from src.signals import ALL_SIGNALS

colorama_init(autoreset=True)

LOOKBACK = 100
TRAIN_WEEKS = 4
TEST_DAYS = 7
SIGNAL_NAMES = [s.name for s in ALL_SIGNALS]


# ── DB ────────────────────────────────────────────────────────────────────────

def _db_url():
    return (
        settings.DATABASE_URL_ASYNC
        .replace("postgresql+asyncpg://", "postgresql://")
        .replace("?ssl=require", "?sslmode=require")
    )


def load_active_weights() -> tuple[dict, int]:
    """Returns (weights_dict, version). Falls back to equal weights if table empty."""
    import psycopg
    try:
        with psycopg.connect(_db_url()) as conn:
            row = conn.execute(
                "SELECT weights, version FROM signal_weights WHERE is_active=TRUE ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            if row:
                return dict(row[0]), int(row[1])
    except Exception as e:
        print(f"{Fore.YELLOW}DB load failed: {e}{Style.RESET_ALL}")
    default = {n: 1.0 / len(SIGNAL_NAMES) for n in SIGNAL_NAMES}
    return default, 0


def save_weights(weights: dict, version: int, performance: dict):
    import psycopg
    with psycopg.connect(_db_url()) as conn:
        conn.execute("UPDATE signal_weights SET is_active=FALSE WHERE is_active=TRUE")
        conn.execute(
            """
            INSERT INTO signal_weights (id, version, weights, performance, is_active, created_at)
            VALUES (%s, %s, %s::jsonb, %s::jsonb, TRUE, %s)
            """,
            (
                str(uuid.uuid4()),
                version,
                json.dumps({k: round(v, 4) for k, v in weights.items()}),
                json.dumps(performance),
                datetime.now(timezone.utc),
            ),
        )
        conn.commit()
    print(f"  {Fore.GREEN}[saved v{version} to DB]{Style.RESET_ALL}")


# ── Data fetching ─────────────────────────────────────────────────────────────

def fetch_bars(symbol: str):
    import pandas as pd
    from alpaca.data.timeframe import TimeFrame

    total_days = TRAIN_WEEKS * 7 + TEST_DAYS
    end = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    start = end - timedelta(days=total_days)

    print(f"Fetching {symbol} {total_days}d of 1-min bars...")

    is_crypto = "/" in symbol or settings.ASSET_CLASS == "crypto"
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
        raise RuntimeError("No data returned from Alpaca")
    if isinstance(df.index, pd.MultiIndex):
        df = df.xs(symbol, level=0)
    df = df.rename(columns=str.lower)
    cols = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
    df = df[cols].sort_index()

    test_cutoff = end - timedelta(days=TEST_DAYS)
    df_train = df[df.index < test_cutoff]
    df_test = df[df.index >= test_cutoff]

    print(f"  Train: {len(df_train):,} bars ({df_train.index[0].strftime('%m-%d')} to {df_train.index[-1].strftime('%m-%d')})")
    print(f"  Test:  {len(df_test):,} bars  ({df_test.index[0].strftime('%m-%d')} to {df_test.index[-1].strftime('%m-%d')})")
    return df_train, df_test


# ── Signal matrix ─────────────────────────────────────────────────────────────

def compute_signal_matrix(df, label=""):
    n = len(df)
    matrix = np.zeros((n, len(ALL_SIGNALS)), dtype=np.float32)
    print(f"  {label}signals on {n:,} bars", end="", flush=True)
    for i in range(LOOKBACK, n):
        window = df.iloc[i - LOOKBACK: i + 1]
        for j, sig in enumerate(ALL_SIGNALS):
            matrix[i, j] = sig.safe_compute(window)
        if i % 5000 == 0:
            print(".", end="", flush=True)
    print(" done")
    return matrix


# ── Simulation ────────────────────────────────────────────────────────────────

def simulate(df, mat, weights_arr, long_thr=0.15, short_thr=-0.15, allow_short=False):
    wsum = np.sum(np.abs(weights_arr))
    scores = (mat @ weights_arr) / wsum if wsum > 0 else np.zeros(len(df))

    prices = df["close"].values
    capital = 10_000.0
    pos_size = 1_000.0
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
        elif position["side"] == "long" and score < short_thr:
            pnl = (price - position["entry"]) * position["qty"]
            cash += pos_size + pnl
            trades.append(pnl)
            position = None
        elif position["side"] == "short" and score > long_thr:
            pnl = (position["entry"] - price) * position["qty"]
            cash -= pos_size - pnl
            trades.append(pnl)
            position = None

        if position:
            pv = position["qty"] * price if position["side"] == "long" \
                else position["qty"] * (2 * position["entry"] - price)
            equity[i] = cash + pv
        else:
            equity[i] = cash

    if position:
        p = prices[-1]
        pnl = (p - position["entry"]) * position["qty"] if position["side"] == "long" \
            else (position["entry"] - p) * position["qty"]
        trades.append(pnl)

    eq = equity[LOOKBACK:]
    ret = (eq[-1] - capital) / capital * 100 if len(eq) > 0 else 0.0
    max_eq = np.maximum.accumulate(eq)
    max_dd = ((eq - max_eq) / np.where(max_eq > 0, max_eq, 1) * 100).min()

    pnls = np.array(trades) if trades else np.array([0.0])
    winners = pnls[pnls > 0]
    losers = pnls[pnls <= 0]
    win_rate = len(winners) / len(pnls) * 100 if len(pnls) else 0.0

    # Sharpe on 1440-bar (daily) equity samples
    daily_eq = eq[::1440]
    daily_ret = np.diff(daily_eq) / daily_eq[:-1] if len(daily_eq) > 1 else np.array([0.0])
    std = daily_ret.std()
    sharpe = (daily_ret.mean() / std * (252 ** 0.5)) if std > 0 else 0.0

    pf = abs(winners.sum() / losers.sum()) if losers.sum() != 0 else 999.0

    return {
        "return_pct": round(ret, 4),
        "sharpe": round(sharpe, 4),
        "num_trades": int(len(pnls)),
        "win_rate": round(win_rate, 2),
        "profit_factor": round(min(pf, 999.0), 4),
        "max_dd": round(max_dd, 4),
    }


# ── Mutation ──────────────────────────────────────────────────────────────────

def mutate(weights: dict, sigma: float) -> dict:
    """Add Gaussian noise to each weight, clamp ≥0, renormalize."""
    mutated = {k: max(0.0, v + float(np.random.normal(0, sigma))) for k, v in weights.items()}
    total = sum(mutated.values())
    if total == 0:
        return weights.copy()
    return {k: v / total for k, v in mutated.items()}


# ── Evolution cycle ───────────────────────────────────────────────────────────

def evolve_once(symbol: str, n_mutations: int, sigma: float):
    current_weights, version = load_active_weights()

    print(f"\n{Fore.CYAN}Evolution v{version} → {n_mutations} mutations (sigma={sigma}){Style.RESET_ALL}")
    top_keys = sorted(current_weights, key=current_weights.get, reverse=True)
    print("  Current: " + "  ".join(f"{k}={current_weights[k]:.3f}" for k in top_keys if current_weights[k] > 0.01))

    df_train, df_test = fetch_bars(symbol)

    if len(df_train) < LOOKBACK + 50 or len(df_test) < LOOKBACK + 10:
        print(f"{Fore.RED}Not enough bars to evolve.{Style.RESET_ALL}")
        return

    print("  Computing signal matrices...")
    mat_train = compute_signal_matrix(df_train, "Train ")
    mat_test = compute_signal_matrix(df_test, "Test  ")

    # Evaluate current + all mutations on OOS test
    current_arr = np.array([current_weights.get(n, 0.0) for n in SIGNAL_NAMES], dtype=np.float32)
    current_oos = simulate(df_test, mat_test, current_arr)

    candidates = [{"weights": current_weights, "arr": current_arr, "oos": current_oos, "label": "current"}]

    for i in range(n_mutations):
        w_dict = mutate(current_weights, sigma)
        w_arr = np.array([w_dict.get(n, 0.0) for n in SIGNAL_NAMES], dtype=np.float32)
        oos = simulate(df_test, mat_test, w_arr)
        candidates.append({"weights": w_dict, "arr": w_arr, "oos": oos, "label": f"mut#{i+1:02d}"})

    candidates.sort(key=lambda c: (c["oos"]["sharpe"], c["oos"]["return_pct"]), reverse=True)

    # Print top 5
    print(f"\n  {'Rank':<6} {'Label':<10} {'Return':>8} {'Sharpe':>7} {'WR':>7} {'Trades':>7}")
    print(f"  {'-'*6} {'-'*10} {'-'*8} {'-'*7} {'-'*7} {'-'*7}")
    for rank, c in enumerate(candidates[:6], 1):
        o = c["oos"]
        star = " *" if rank == 1 else ""
        ret_col = Fore.GREEN if o["return_pct"] >= 0 else Fore.RED
        print(f"  {rank:<6} {c['label']:<10} {ret_col}{o['return_pct']:>+7.2f}%{Style.RESET_ALL} "
              f"{o['sharpe']:>7.2f} {o['win_rate']:>6.1f}% {o['num_trades']:>7}{star}")

    best = candidates[0]
    if best["label"] == "current":
        print(f"\n  {Fore.YELLOW}Current strategy is still best — no update this cycle.{Style.RESET_ALL}")
        return

    # Compute in-sample stats for the winning mutation (for the DB record)
    is_stats = simulate(df_train, mat_train, best["arr"])

    new_version = version + 1
    save_weights(
        best["weights"],
        new_version,
        {
            "in_sample": is_stats,
            "out_of_sample": best["oos"],
            "evolved_from_version": version,
            "mutations_tried": n_mutations,
            "sigma": sigma,
        },
    )

    print(f"\n  {Fore.GREEN}Promoted v{new_version} (OOS sharpe {best['oos']['sharpe']:.2f}, return {best['oos']['return_pct']:+.2f}%):{Style.RESET_ALL}")
    for name in sorted(best["weights"], key=best["weights"].get, reverse=True):
        v = best["weights"][name]
        if v > 0.01:
            bar = "|" * int(v * 35)
            print(f"    {name:<12} {Fore.CYAN}{bar:<35}{Style.RESET_ALL} {v:.3f}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Online strategy evolution via walk-forward backtesting")
    parser.add_argument("--symbol", default=settings.SYMBOL)
    parser.add_argument("--mutations", type=int, default=10, help="Mutations per cycle (default: 10)")
    parser.add_argument("--sigma", type=float, default=0.05, help="Mutation strength (default: 0.05)")
    parser.add_argument("--interval", type=int, default=600, help="Loop interval seconds (default: 600)")
    parser.add_argument("--loop", action="store_true", help="Run continuously")
    args = parser.parse_args()

    if args.loop:
        print(f"{Fore.CYAN}Online evolution loop | {args.symbol} | every {args.interval}s | {args.mutations} mutations | sigma={args.sigma}{Style.RESET_ALL}")
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
