"""
Online strategy evolution — core logic.
Imported by both scripts/evolve_online.py (CLI) and main.py (Railway scheduler).
"""
import json
import time
import uuid
from datetime import datetime, timezone, timedelta

import numpy as np
from colorama import Fore, Style

from src.config import settings
from src.signals import ALL_SIGNALS

LOOKBACK = 100
TRAIN_WEEKS = 4
TEST_DAYS = 7
SIGNAL_NAMES = [s.name for s in ALL_SIGNALS]


# ── DB ────────────────────────────────────────────────────────────────────────

DEFAULT_THRESHOLD = 0.15
THRESHOLD_MIN = 0.05
THRESHOLD_MAX = 0.40


def _db_url() -> str:
    return (
        settings.DATABASE_URL_ASYNC
        .replace("postgresql+asyncpg://", "postgresql://")
        .replace("?ssl=require", "?sslmode=require")
    )


def load_active_weights() -> tuple[dict, int, float]:
    """Returns (signal_weights, version, threshold). Falls back to equal weights."""
    import psycopg
    try:
        with psycopg.connect(_db_url()) as conn:
            row = conn.execute(
                "SELECT weights, version, performance FROM signal_weights WHERE is_active=TRUE ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            if row:
                weights_dict = dict(row[0])
                perf = dict(row[2]) if row[2] else {}
                threshold = float(perf.get("threshold", weights_dict.pop("_threshold", DEFAULT_THRESHOLD)))
                return weights_dict, int(row[1]), threshold
    except Exception as e:
        print(f"{Fore.YELLOW}DB load failed: {e}{Style.RESET_ALL}")
    return {n: 1.0 / len(SIGNAL_NAMES) for n in SIGNAL_NAMES}, 0, DEFAULT_THRESHOLD


def save_weights(weights: dict, version: int, performance: dict, threshold: float) -> None:
    import psycopg
    payload = {k: round(v, 4) for k, v in weights.items()}
    performance["threshold"] = round(threshold, 4)  # store in performance, not weights
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
                json.dumps(payload),
                json.dumps(performance),
                datetime.now(timezone.utc),
            ),
        )
        conn.commit()
    print(f"  {Fore.GREEN}[saved v{version} to DB  threshold={threshold:.3f}]{Style.RESET_ALL}")


# ── Data ──────────────────────────────────────────────────────────────────────

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
        raise RuntimeError(f"No data returned for {symbol}")
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

def compute_signal_matrix(df, label: str = "") -> np.ndarray:
    from tqdm import tqdm
    n = len(df)
    matrix = np.zeros((n, len(ALL_SIGNALS)), dtype=np.float32)
    desc = f"{label}signals" if label else "signals"
    for i in tqdm(range(LOOKBACK, n), desc=f"  {desc}", unit="bar", ncols=80, miniters=10000):
        window = df.iloc[i - LOOKBACK: i + 1]
        for j, sig in enumerate(ALL_SIGNALS):
            matrix[i, j] = sig.safe_compute(window)
    return matrix


# ── Simulation ────────────────────────────────────────────────────────────────

def simulate(df, mat: np.ndarray, weights_arr: np.ndarray,
             long_thr: float = DEFAULT_THRESHOLD, short_thr: float = -DEFAULT_THRESHOLD,
             allow_short: bool = False) -> dict:
    wsum = np.sum(np.abs(weights_arr))
    scores = (mat @ weights_arr) / wsum if wsum > 0 else np.zeros(len(df))

    prices = df["close"].values
    capital = 10_000.0
    pos_size = 1_000.0
    cash = capital
    position = None
    trades: list[float] = []
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
    return {k: v / total for k, v in mutated.items()} if total > 0 else weights.copy()


def mutate_threshold(threshold: float, sigma: float) -> float:
    """Mutate threshold with small noise, clamped to valid range."""
    new_thr = threshold + float(np.random.normal(0, sigma * 0.5))
    return float(np.clip(new_thr, THRESHOLD_MIN, THRESHOLD_MAX))


# ── Evolution cycle ───────────────────────────────────────────────────────────

def evolve_once(symbol: str, n_mutations: int = 2, sigma: float = 0.05) -> None:
    current_weights, version, current_threshold = load_active_weights()

    # Integrate any new signals added since last saved version
    new_signals = [n for n in SIGNAL_NAMES if n not in current_weights]
    if new_signals:
        print(f"{Fore.YELLOW}  New signals: {new_signals} — seeding at 0.02{Style.RESET_ALL}")
        for n in new_signals:
            current_weights[n] = 0.02
    # Drop signals removed from ALL_SIGNALS
    current_weights = {k: v for k, v in current_weights.items() if k in SIGNAL_NAMES}
    total = sum(current_weights.values())
    if total > 0:
        current_weights = {k: v / total for k, v in current_weights.items()}

    evolution_start = time.time()

    print(f"\n{Fore.CYAN}Evolution v{version} → {n_mutations} mutations (sigma={sigma}, threshold={current_threshold:.3f}){Style.RESET_ALL}")
    top = sorted(current_weights, key=current_weights.get, reverse=True)
    print("  Current: " + "  ".join(f"{k}={current_weights[k]:.3f}" for k in top if current_weights[k] > 0.01))

    df_train, df_test = fetch_bars(symbol)

    if len(df_train) < LOOKBACK + 50 or len(df_test) < LOOKBACK + 10:
        print(f"{Fore.RED}Not enough bars to evolve.{Style.RESET_ALL}")
        return

    print("  Computing signal matrices...")
    signal_start = time.time()
    mat_train = compute_signal_matrix(df_train, "Train ")
    mat_test = compute_signal_matrix(df_test, "Test  ")
    signal_duration = time.time() - signal_start
    print(f"  {Fore.CYAN}Signal computation took {signal_duration:.1f}s{Style.RESET_ALL}")

    current_arr = np.array([current_weights.get(n, 0.0) for n in SIGNAL_NAMES], dtype=np.float32)
    current_oos = simulate(df_test, mat_test, current_arr, current_threshold, -current_threshold)

    candidates = [{"weights": current_weights, "arr": current_arr, "oos": current_oos, "threshold": current_threshold, "label": "current"}]
    for i in range(n_mutations):
        w_dict = mutate(current_weights, sigma)
        w_arr = np.array([w_dict.get(n, 0.0) for n in SIGNAL_NAMES], dtype=np.float32)
        thr = mutate_threshold(current_threshold, sigma)
        candidates.append({"weights": w_dict, "arr": w_arr, "threshold": thr, "oos": simulate(df_test, mat_test, w_arr, thr, -thr), "label": f"mut#{i+1:02d}"})

    candidates.sort(key=lambda c: (c["oos"]["sharpe"], c["oos"]["return_pct"]), reverse=True)

    print(f"\n  {'Rank':<6} {'Label':<10} {'Return':>8} {'Sharpe':>7} {'WR':>7} {'Trades':>7}")
    print(f"  {'-'*6} {'-'*10} {'-'*8} {'-'*7} {'-'*7} {'-'*7}")
    for rank, c in enumerate(candidates[:6], 1):
        o = c["oos"]
        star = " *" if rank == 1 else ""
        col = Fore.GREEN if o["return_pct"] >= 0 else Fore.RED
        print(f"  {rank:<6} {c['label']:<10} {col}{o['return_pct']:>+7.2f}%{Style.RESET_ALL} "
              f"{o['sharpe']:>7.2f} {o['win_rate']:>6.1f}% {o['num_trades']:>7}{star}")

    best = candidates[0]
    evolution_duration = time.time() - evolution_start

    if best["label"] == "current":
        print(f"\n  {Fore.YELLOW}Current strategy is best — no update.{Style.RESET_ALL}")
        print(f"  {Fore.CYAN}Total evolution time: {evolution_duration:.1f}s (signals: {signal_duration:.1f}s){Style.RESET_ALL}")
        return

    best_thr = best["threshold"]
    is_stats = simulate(df_train, mat_train, best["arr"], best_thr, -best_thr)
    new_version = version + 1
    save_weights(
        best["weights"],
        new_version,
        {"in_sample": is_stats, "out_of_sample": best["oos"],
         "evolved_from_version": version, "mutations_tried": n_mutations, "sigma": sigma,
         "threshold": best_thr,
         "evolution_duration_sec": round(evolution_duration, 1),
         "signal_computation_sec": round(signal_duration, 1)},
        best_thr,
    )

    print(f"\n  {Fore.GREEN}Promoted v{new_version} (OOS sharpe {best['oos']['sharpe']:.2f}, return {best['oos']['return_pct']:+.2f}%, threshold={best_thr:.3f}):{Style.RESET_ALL}")
    print(f"  {'Signal':<12} {'Old':>7} {'New':>7} {'Δ':>7}")
    print(f"  {'-'*12} {'-'*7} {'-'*7} {'-'*7}")
    for name in sorted(best["weights"], key=best["weights"].get, reverse=True):
        old_v = current_weights.get(name, 0.0)
        new_v = best["weights"][name]
        delta = new_v - old_v
        col = Fore.GREEN if delta > 0 else Fore.RED if delta < 0 else Style.RESET_ALL
        print(f"  {name:<12} {old_v:>7.4f} {new_v:>7.4f} {col}{delta:>+7.4f}{Style.RESET_ALL}")
    thr_delta = best_thr - current_threshold
    thr_col = Fore.GREEN if thr_delta > 0 else Fore.RED if thr_delta < 0 else Style.RESET_ALL
    print(f"  {'_threshold':<12} {current_threshold:>7.4f} {best_thr:>7.4f} {thr_col}{thr_delta:>+7.4f}{Style.RESET_ALL}")
    print(f"\n  {Fore.CYAN}Total evolution time: {evolution_duration:.1f}s (signals: {signal_duration:.1f}s){Style.RESET_ALL}")
