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
from src.signals import ALL_SIGNALS, make_signals

LOOKBACK = 600  # Must be >= max signal lookback (channel uses 600)
TRAIN_WEEKS = 4
TEST_DAYS = 7
SIGNAL_NAMES = [s.name for s in ALL_SIGNALS]


# ── DB ────────────────────────────────────────────────────────────────────────

DEFAULT_THRESHOLD = 0.15
THRESHOLD_MIN = 0.05
THRESHOLD_MAX = 0.40

DEFAULT_ENTRY_BIAS = 0.03  # Start with small bias to compensate for fees
ENTRY_BIAS_MIN = 0.0
ENTRY_BIAS_MAX = 0.15


def _db_url() -> str:
    return (
        settings.DATABASE_URL_ASYNC
        .replace("postgresql+asyncpg://", "postgresql://")
        .replace("?ssl=require", "?sslmode=require")
    )


def load_active_weights() -> tuple[dict, int, float, float]:
    """Returns (signal_weights, version, threshold, entry_bias). Falls back to defaults."""
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
                entry_bias = float(perf.get("entry_bias", DEFAULT_ENTRY_BIAS))
                return weights_dict, int(row[1]), threshold, entry_bias
    except Exception as e:
        print(f"{Fore.YELLOW}DB load failed: {e}{Style.RESET_ALL}")
    return {n: 1.0 / len(SIGNAL_NAMES) for n in SIGNAL_NAMES}, 0, DEFAULT_THRESHOLD, DEFAULT_ENTRY_BIAS


def _ensure_evolution_results_table(conn) -> None:
    """Create evolution_results table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS evolution_results (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            symbol VARCHAR(20) NOT NULL,
            version_before INTEGER NOT NULL,
            version_after INTEGER,
            current_sharpe NUMERIC(10, 6),
            best_sharpe NUMERIC(10, 6),
            mutations_tried INTEGER NOT NULL,
            model_changed BOOLEAN NOT NULL,
            improvement NUMERIC(10, 6),
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS ix_evolution_results_created_at ON evolution_results(created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_evolution_results_model_changed ON evolution_results(model_changed)")
    conn.commit()


def log_evolution_result(
    symbol: str,
    version_before: int,
    version_after: int | None,
    current_sharpe: float,
    best_sharpe: float,
    mutations_tried: int,
    model_changed: bool,
) -> None:
    """Log evolution cycle result to database for tracking success rate."""
    import psycopg
    improvement = best_sharpe - current_sharpe if model_changed else None
    try:
        with psycopg.connect(_db_url()) as conn:
            _ensure_evolution_results_table(conn)
            conn.execute(
                """
                INSERT INTO evolution_results
                (symbol, version_before, version_after, current_sharpe, best_sharpe,
                 mutations_tried, model_changed, improvement)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    symbol,
                    version_before,
                    version_after,
                    round(current_sharpe, 6) if current_sharpe else None,
                    round(best_sharpe, 6) if best_sharpe else None,
                    mutations_tried,
                    model_changed,
                    round(improvement, 6) if improvement else None,
                ),
            )
            conn.commit()
    except Exception as e:
        print(f"{Fore.YELLOW}Evolution result logging failed: {e}{Style.RESET_ALL}")


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
    signals = make_signals()  # fresh instances — don't pollute live trading state
    n = len(df)
    matrix = np.zeros((n, len(signals)), dtype=np.float32)
    total = n - LOOKBACK
    tag = f"{label}signals" if label else "signals"
    # Report progress every 1000 bars or ~5% (whichever is smaller)
    report_interval = min(1000, max(1, total // 20))
    for idx, i in enumerate(range(LOOKBACK, n)):
        if total > 0 and idx % report_interval == 0:
            print(f"  {tag}: {idx * 100 // total}% ({idx}/{total} bars)")
        window = df.iloc[i - LOOKBACK: i + 1]
        for j, sig in enumerate(signals):
            matrix[i, j] = sig.safe_compute(window)
    return matrix


# ── Simulation ────────────────────────────────────────────────────────────────

def simulate(df, mat: np.ndarray, weights_arr: np.ndarray,
             long_thr: float = DEFAULT_THRESHOLD, short_thr: float = -DEFAULT_THRESHOLD,
             allow_short: bool = False, record_trades: bool = False,
             fee_pct: float = 0.0025, entry_bias: float = 0.0) -> dict:
    """
    Simulate trading strategy with transaction costs.

    Args:
        fee_pct: Transaction fee as percentage (default 0.25% = 0.0025 per trade)
                 This covers spread + commission. Applied on entry and exit.
        entry_bias: Additional threshold offset for entering positions (default 0).
                    Positive value = more conservative (harder to enter trades).
                    E.g., entry_bias=0.05 means need score > 0.20 instead of 0.15.
                    Does NOT affect exit thresholds - easy to exit when signal reverses.
    """
    wsum = np.sum(np.abs(weights_arr))
    scores = (mat @ weights_arr) / wsum if wsum > 0 else np.zeros(len(df))

    prices = df["close"].values
    timestamps = [str(t) for t in df.index]
    capital = 10_000.0
    pos_size = 1_000.0
    cash = capital
    position = None
    trades: list[float] = []
    trades_log: list[dict] = []
    equity = np.full(len(df), capital, dtype=np.float64)
    total_fees = 0.0

    # Entry thresholds are higher (more conservative) due to entry_bias
    entry_long_thr = long_thr + entry_bias
    entry_short_thr = short_thr - entry_bias  # More negative = harder to short

    for i in range(LOOKBACK, len(df)):
        price = prices[i]
        score = scores[i]

        if position is None:
            if score > entry_long_thr:
                entry_fee = pos_size * fee_pct
                qty = (pos_size - entry_fee) / price  # Buy slightly less due to fee
                cash -= pos_size
                total_fees += entry_fee
                position = {"side": "long", "entry": price, "qty": qty, "idx": i}
                if record_trades:
                    trades_log.append({"type": "buy", "price": round(price, 2), "ts": timestamps[i], "fee": round(entry_fee, 2)})
            elif allow_short and score < entry_short_thr:
                entry_fee = pos_size * fee_pct
                qty = pos_size / price
                cash += pos_size - entry_fee
                total_fees += entry_fee
                position = {"side": "short", "entry": price, "qty": qty, "idx": i}
                if record_trades:
                    trades_log.append({"type": "sell", "price": round(price, 2), "ts": timestamps[i], "fee": round(entry_fee, 2)})
        elif position["side"] == "long" and score < short_thr:
            exit_value = position["qty"] * price
            exit_fee = exit_value * fee_pct
            pnl = (price - position["entry"]) * position["qty"] - exit_fee
            cash += exit_value - exit_fee
            total_fees += exit_fee
            trades.append(pnl)
            if record_trades:
                trades_log.append({"type": "sell", "price": round(price, 2), "ts": timestamps[i], "pnl": round(pnl, 2), "fee": round(exit_fee, 2)})
            position = None
        elif position["side"] == "short" and score > long_thr:
            exit_cost = position["qty"] * price
            exit_fee = exit_cost * fee_pct
            pnl = (position["entry"] - price) * position["qty"] - exit_fee
            cash -= exit_cost + exit_fee
            total_fees += exit_fee
            trades.append(pnl)
            if record_trades:
                trades_log.append({"type": "buy", "price": round(price, 2), "ts": timestamps[i], "pnl": round(pnl, 2), "fee": round(exit_fee, 2)})
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

    result = {
        "return_pct": round(ret, 4),
        "sharpe": round(sharpe, 4),
        "num_trades": int(len(pnls)),
        "win_rate": round(win_rate, 2),
        "profit_factor": round(min(pf, 999.0), 4),
        "max_dd": round(max_dd, 4),
        "total_fees": round(total_fees, 2),
        "entry_bias": round(entry_bias, 4),
    }

    if record_trades:
        # Downsample equity to max 300 points for storage
        step = max(1, len(eq) // 300)
        ts_slice = timestamps[LOOKBACK::step]
        eq_slice = eq[::step].tolist()
        result["equity_curve"] = [{"ts": ts_slice[i], "eq": round(eq_slice[i], 2)} for i in range(min(len(ts_slice), len(eq_slice)))]
        result["trades_log"] = trades_log

    return result


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


def mutate_entry_bias(entry_bias: float, sigma: float) -> float:
    """Mutate entry_bias with small noise, clamped to valid range."""
    new_bias = entry_bias + float(np.random.normal(0, sigma * 0.3))
    return float(np.clip(new_bias, ENTRY_BIAS_MIN, ENTRY_BIAS_MAX))


# ── Evolution cycle ───────────────────────────────────────────────────────────

def evolve_once(symbol: str, n_mutations: int = 2, sigma: float = 0.05) -> None:
    current_weights, version, current_threshold, current_entry_bias = load_active_weights()

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

    print(f"\n{Fore.CYAN}Evolution v{version} → {n_mutations} mutations (sigma={sigma}, thr={current_threshold:.3f}, bias={current_entry_bias:.3f}){Style.RESET_ALL}")
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
    current_oos = simulate(df_test, mat_test, current_arr, current_threshold, -current_threshold,
                           entry_bias=current_entry_bias)

    candidates = [{"weights": current_weights, "arr": current_arr, "oos": current_oos,
                   "threshold": current_threshold, "entry_bias": current_entry_bias, "label": "current"}]
    for i in range(n_mutations):
        w_dict = mutate(current_weights, sigma)
        w_arr = np.array([w_dict.get(n, 0.0) for n in SIGNAL_NAMES], dtype=np.float32)
        thr = mutate_threshold(current_threshold, sigma)
        bias = mutate_entry_bias(current_entry_bias, sigma)
        oos = simulate(df_test, mat_test, w_arr, thr, -thr, entry_bias=bias)
        candidates.append({"weights": w_dict, "arr": w_arr, "threshold": thr, "entry_bias": bias, "oos": oos, "label": f"mut#{i+1:02d}"})

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
        log_evolution_result(
            symbol=symbol,
            version_before=version,
            version_after=None,
            current_sharpe=current_oos["sharpe"],
            best_sharpe=current_oos["sharpe"],
            mutations_tried=n_mutations,
            model_changed=False,
        )
        return

    best_thr = best["threshold"]
    best_bias = best["entry_bias"]
    is_stats = simulate(df_train, mat_train, best["arr"], best_thr, -best_thr, entry_bias=best_bias)
    best_oos_full = simulate(df_test, mat_test, best["arr"], best_thr, -best_thr, record_trades=True, entry_bias=best_bias)
    new_version = version + 1
    save_weights(
        best["weights"],
        new_version,
        {"in_sample": is_stats, "out_of_sample": best_oos_full,
         "evolved_from_version": version, "mutations_tried": n_mutations, "sigma": sigma,
         "threshold": best_thr,
         "entry_bias": best_bias,
         "evolution_duration_sec": round(evolution_duration, 1),
         "signal_computation_sec": round(signal_duration, 1)},
        best_thr,
    )
    log_evolution_result(
        symbol=symbol,
        version_before=version,
        version_after=new_version,
        current_sharpe=current_oos["sharpe"],
        best_sharpe=best["oos"]["sharpe"],
        mutations_tried=n_mutations,
        model_changed=True,
    )

    print(f"\n  {Fore.GREEN}Promoted v{new_version} (OOS sharpe {best['oos']['sharpe']:.2f}, return {best['oos']['return_pct']:+.2f}%, thr={best_thr:.3f}, bias={best_bias:.3f}):{Style.RESET_ALL}")
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
    bias_delta = best_bias - current_entry_bias
    bias_col = Fore.GREEN if bias_delta > 0 else Fore.RED if bias_delta < 0 else Style.RESET_ALL
    print(f"  {'_entry_bias':<12} {current_entry_bias:>7.4f} {best_bias:>7.4f} {bias_col}{bias_delta:>+7.4f}{Style.RESET_ALL}")
    print(f"\n  {Fore.CYAN}Total evolution time: {evolution_duration:.1f}s (signals: {signal_duration:.1f}s){Style.RESET_ALL}")
