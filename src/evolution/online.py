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
TEST_DAYS = 14  # 14 days = ~10 trading days, minus 600 lookback = ~7 days actual test
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


def update_evolution_progress(phase: str, progress_pct: int, message: str = ""):
    """Update evolution progress to bot_cache for frontend display."""
    import psycopg
    from datetime import datetime, timezone
    try:
        with psycopg.connect(_db_url()) as conn:
            status = {
                "phase": phase,  # idle, fetching, computing_signals, evaluating, saving
                "progress_pct": progress_pct,
                "message": message,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            conn.execute(
                """INSERT INTO bot_cache (key, value) VALUES ('evolution_progress', %s::jsonb)
                   ON CONFLICT (key) DO UPDATE SET value = %s::jsonb""",
                (json.dumps(status), json.dumps(status))
            )
            conn.commit()
    except Exception as e:
        print(f"[evolution] Progress update failed: {e}")


def save_channel_info(channel_info: dict) -> None:
    """Save channel info to bot_cache for frontend display (sync version for evolution)."""
    import psycopg
    try:
        # Convert numpy types to native Python types
        clean_info = {}
        for k, v in channel_info.items():
            if hasattr(v, 'item'):
                clean_info[k] = v.item()
            else:
                clean_info[k] = v

        with psycopg.connect(_db_url()) as conn:
            conn.execute(
                """INSERT INTO bot_cache (key, value, updated_at)
                   VALUES ('channel_info', %s::jsonb, NOW())
                   ON CONFLICT (key) DO UPDATE SET value = %s::jsonb, updated_at = NOW()""",
                (json.dumps(clean_info), json.dumps(clean_info))
            )
            conn.commit()
    except Exception as e:
        print(f"[evolution] Channel info save failed: {e}")


def load_active_weights() -> tuple[dict, int, float, float]:
    """Returns (signal_weights, version, threshold, entry_bias). Falls back to defaults."""
    import psycopg
    from src.engine.scoring import DEFAULT_WEIGHTS
    try:
        with psycopg.connect(_db_url()) as conn:
            row = conn.execute(
                "SELECT weights, version, performance FROM signal_weights WHERE is_active=TRUE ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            if row:
                # Handle corrupted weights (string instead of dict)
                raw_weights = row[0]
                if isinstance(raw_weights, str):
                    try:
                        weights_dict = json.loads(raw_weights)
                    except:
                        print(f"{Fore.RED}Weights corrupted (string), using defaults{Style.RESET_ALL}")
                        return {n: 1.0 / len(SIGNAL_NAMES) for n in SIGNAL_NAMES}, 0, DEFAULT_THRESHOLD, DEFAULT_ENTRY_BIAS
                elif isinstance(raw_weights, dict):
                    weights_dict = raw_weights.copy()
                else:
                    print(f"{Fore.RED}Weights unknown type {type(raw_weights)}, using defaults{Style.RESET_ALL}")
                    return {n: 1.0 / len(SIGNAL_NAMES) for n in SIGNAL_NAMES}, 0, DEFAULT_THRESHOLD, DEFAULT_ENTRY_BIAS

                # Validate that keys are signal names, not corrupted
                valid_keys = [k for k in weights_dict.keys() if k in SIGNAL_NAMES or k == "_threshold"]
                if len(valid_keys) < len(SIGNAL_NAMES) // 2:
                    print(f"{Fore.RED}Weights have corrupted keys ({list(weights_dict.keys())[:3]}...), using defaults{Style.RESET_ALL}")
                    return {n: 1.0 / len(SIGNAL_NAMES) for n in SIGNAL_NAMES}, 0, DEFAULT_THRESHOLD, DEFAULT_ENTRY_BIAS

                perf = row[2] if row[2] else {}
                if isinstance(perf, str):
                    try:
                        perf = json.loads(perf)
                    except:
                        perf = {}
                threshold = float(perf.get("threshold", weights_dict.pop("_threshold", DEFAULT_THRESHOLD)))
                entry_bias = float(perf.get("entry_bias", DEFAULT_ENTRY_BIAS))
                # Merge in any NEW signals from DEFAULT_WEIGHTS that aren't in active model
                for signal_name in SIGNAL_NAMES:
                    if signal_name not in weights_dict:
                        default_w = DEFAULT_WEIGHTS.get(signal_name, 0.05)
                        weights_dict[signal_name] = default_w
                        print(f"{Fore.CYAN}Added new signal: {signal_name} = {default_w}{Style.RESET_ALL}")
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
                    round(float(current_sharpe), 6) if current_sharpe is not None else None,
                    round(float(best_sharpe), 6) if best_sharpe is not None else None,
                    mutations_tried,
                    model_changed,
                    round(float(improvement), 6) if improvement is not None else None,
                ),
            )
            conn.commit()
    except Exception as e:
        print(f"{Fore.YELLOW}Evolution result logging failed: {e}{Style.RESET_ALL}")


def _convert_numpy_types(obj):
    """Recursively convert numpy types to native Python types for JSON serialization."""
    if isinstance(obj, dict):
        return {k: _convert_numpy_types(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_convert_numpy_types(v) for v in obj]
    elif hasattr(obj, 'item'):  # numpy scalar
        return obj.item()
    elif hasattr(obj, 'tolist'):  # numpy array
        return obj.tolist()
    return obj


def save_weights(weights: dict, version: int, performance: dict, threshold: float) -> None:
    import psycopg
    payload = {k: round(float(v), 4) for k, v in weights.items()}  # Ensure float
    performance["threshold"] = round(float(threshold), 4)  # store in performance, not weights
    # Convert numpy types to native Python types
    clean_perf = _convert_numpy_types(performance)
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
                json.dumps(clean_perf),
                datetime.now(timezone.utc),
            ),
        )
        conn.commit()
    print(f"  {Fore.GREEN}[saved v{version} to DB  threshold={threshold:.3f}]{Style.RESET_ALL}")


def update_performance(version: int, performance: dict) -> None:
    """Update performance metrics of the active model (without changing weights/version)."""
    import psycopg
    # Convert numpy types to native Python types
    clean_perf = _convert_numpy_types(performance)
    with psycopg.connect(_db_url()) as conn:
        conn.execute(
            """
            UPDATE signal_weights
            SET performance = %s::jsonb
            WHERE version = %s AND is_active = TRUE
            """,
            (json.dumps(clean_perf), version),
        )
        conn.commit()
    print(f"  {Fore.CYAN}[updated v{version} performance metrics]{Style.RESET_ALL}")


# ── Data ──────────────────────────────────────────────────────────────────────

def fetch_bars(symbol: str):
    """Fetch historical bars from Yahoo Finance (free, no API key)."""
    import pandas as pd
    import httpx

    total_days = TRAIN_WEEKS * 7 + TEST_DAYS
    end = datetime.now(timezone.utc).replace(second=0, microsecond=0)

    # Yahoo limits: 1m=7d, 2m=60d, 5m=60d
    # For 35 days, use 2m interval
    interval = "2m" if total_days > 7 else "1m"
    range_str = f"{total_days}d"

    print(f"Fetching {symbol} {total_days}d of {interval} bars from Yahoo...")

    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        params = {"interval": interval, "range": range_str}

        with httpx.Client(timeout=30) as client:
            resp = client.get(url, params=params, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            data = resp.json()

        result = data.get("chart", {}).get("result", [])
        if not result:
            raise RuntimeError(f"No data returned for {symbol}")

        quote = result[0].get("indicators", {}).get("quote", [{}])[0]
        timestamps = result[0].get("timestamp", [])

        if not timestamps:
            raise RuntimeError(f"No timestamps for {symbol}")

        df = pd.DataFrame({
            "open": quote.get("open", []),
            "high": quote.get("high", []),
            "low": quote.get("low", []),
            "close": quote.get("close", []),
            "volume": quote.get("volume", []),
        }, index=pd.to_datetime(timestamps, unit="s", utc=True))

        df = df.dropna()  # Remove NaN rows

        if df.empty:
            raise RuntimeError(f"No valid data for {symbol}")

    except Exception as e:
        raise RuntimeError(f"Yahoo fetch failed: {e}")

    test_cutoff = end - timedelta(days=TEST_DAYS)
    df_train = df[df.index < test_cutoff]
    df_test = df[df.index >= test_cutoff]

    if len(df_train) < 100:
        raise RuntimeError(f"Not enough training data: {len(df_train)} bars")

    print(f"  Train: {len(df_train):,} bars ({df_train.index[0].strftime('%m-%d')} to {df_train.index[-1].strftime('%m-%d')})")
    print(f"  Test:  {len(df_test):,} bars  ({df_test.index[0].strftime('%m-%d')} to {df_test.index[-1].strftime('%m-%d')})")
    return df_train, df_test


# ── Signal matrix ─────────────────────────────────────────────────────────────

def compute_signal_matrix(df, label: str = "", step: int = 1, profile: bool = False) -> tuple[np.ndarray, np.ndarray, list]:
    """
    Compute signal matrix and channel info for all bars.

    Args:
        step: Compute signals every N bars (interpolate in between).
              step=1 is full resolution, step=5 is 5x faster but less precise.
        profile: If True, track and print per-signal timing at the end.

    Returns:
        (signal_matrix, channel_spreads, channel_infos) - matrix of signal values, array of spreads, list of channel info dicts
    """
    from src.signals.channel import ChannelPositionSignal

    signals = make_signals()  # fresh instances — don't pollute live trading state
    n = len(df)
    matrix = np.zeros((n, len(signals)), dtype=np.float32)
    channel_spreads = np.zeros(n, dtype=np.float32)  # Track channel spread per bar
    channel_infos: list = [None] * n  # Full channel info per bar
    total = (n - LOOKBACK) // step
    tag = f"{label}signals" if label else "signals"
    # Report progress every 1000 bars or ~5% (whichever is smaller)
    report_interval = min(1000, max(1, total // 20))

    # Per-signal timing
    signal_times = np.zeros(len(signals), dtype=np.float64) if profile else None

    # Find channel_position signal index
    channel_sig_idx = None
    for j, sig in enumerate(signals):
        if isinstance(sig, ChannelPositionSignal):
            channel_sig_idx = j
            break

    last_values = np.zeros(len(signals), dtype=np.float32)
    last_spread = 0.0
    last_channel_info = None
    computed_idx = 0
    for idx, i in enumerate(range(LOOKBACK, n)):
        if idx % step == 0:
            # Compute signals at this bar
            if total > 0 and computed_idx % report_interval == 0:
                print(f"  {tag}: {computed_idx * 100 // total}% ({computed_idx}/{total} bars)")
            window = df.iloc[i - LOOKBACK: i + 1]
            for j, sig in enumerate(signals):
                if profile:
                    t0 = time.time()
                    last_values[j] = sig.safe_compute(window)
                    signal_times[j] += time.time() - t0
                else:
                    last_values[j] = sig.safe_compute(window)

            # Extract channel info from channel_position signal
            if channel_sig_idx is not None:
                ch_sig = signals[channel_sig_idx]
                if hasattr(ch_sig, 'last_channel_info') and ch_sig.last_channel_info:
                    ci = ch_sig.last_channel_info
                    last_spread = ci.get('resistance_price', 0) - ci.get('support_price', 0)
                    last_channel_info = ci.copy()
                else:
                    last_channel_info = None

            computed_idx += 1
        # Use last computed values (interpolation = hold previous value)
        matrix[i] = last_values
        channel_spreads[i] = last_spread
        channel_infos[i] = last_channel_info

    # Print profiling results
    if profile and signal_times is not None:
        total_time = np.sum(signal_times)
        print(f"\n  {Fore.CYAN}Signal profiling ({label or 'all'}):{Style.RESET_ALL}")
        print(f"  {'Signal':<20} {'Time (s)':>10} {'%':>8} {'ms/bar':>10}")
        print(f"  {'-'*50}")
        sorted_idx = np.argsort(signal_times)[::-1]
        for j in sorted_idx:
            sig_name = signals[j].name
            sig_time = signal_times[j]
            pct = sig_time / total_time * 100 if total_time > 0 else 0
            ms_per_bar = sig_time / computed_idx * 1000 if computed_idx > 0 else 0
            print(f"  {sig_name:<20} {sig_time:>10.2f} {pct:>7.1f}% {ms_per_bar:>9.2f}")
        print(f"  {'-'*50}")
        print(f"  {'TOTAL':<20} {total_time:>10.2f} {'100.0':>7}% {total_time/computed_idx*1000:>9.2f}")

    return matrix, channel_spreads, channel_infos


# ── Simulation ────────────────────────────────────────────────────────────────

def simulate(df, mat: np.ndarray, weights_arr: np.ndarray,
             channel_spreads: np.ndarray,
             long_thr: float = DEFAULT_THRESHOLD, short_thr: float = -DEFAULT_THRESHOLD,
             allow_short: bool = True, record_trades: bool = False,
             fee_pct: float = 0.0025, entry_bias: float = 0.0,
             channel_infos: list = None) -> dict:
    """
    Simulate trading strategy with transaction costs and channel-based stop loss.

    Args:
        channel_spreads: Array of channel spreads per bar (resistance - support).
                         Stop loss = half of channel spread.
        fee_pct: Transaction fee as percentage (default 0.25% = 0.0025 per trade)
                 This covers spread + commission. Applied on entry and exit.
        entry_bias: Additional threshold offset for entering positions (default 0).
                    Positive value = more conservative (harder to enter trades).
                    E.g., entry_bias=0.05 means need score > 0.20 instead of 0.15.
                    Does NOT affect exit thresholds - easy to exit when signal reverses.
        channel_infos: List of channel info dicts per bar (for trade logging).
    """
    wsum = np.sum(np.abs(weights_arr))
    scores = (mat @ weights_arr) / wsum if wsum > 0 else np.zeros(len(df))

    prices = df["close"].values
    lows = df["low"].values if "low" in df.columns else prices
    highs = df["high"].values if "high" in df.columns else prices
    timestamps = [str(t) for t in df.index]
    capital = 10_000.0
    pos_size = 1_000.0
    cash = capital
    position = None
    trades: list[float] = []
    trades_log: list[dict] = []
    equity = np.full(len(df), capital, dtype=np.float64)
    positions = np.zeros(len(df), dtype=np.int8)  # 0=flat, 1=long, -1=short
    total_fees = 0.0

    # Entry thresholds are higher (more conservative) due to entry_bias
    entry_long_thr = long_thr + entry_bias
    entry_short_thr = short_thr - entry_bias  # More negative = harder to short

    for i in range(LOOKBACK, len(df)):
        price = prices[i]
        low = lows[i]
        high = highs[i]
        score = scores[i]

        # Dynamic stop loss = half of channel spread (resistance - support)
        # With minimum of 1% of price to avoid getting stopped by normal noise
        channel_spread = channel_spreads[i] if channel_spreads[i] > 0 else 5.0  # Fallback $5
        min_stop = price * 0.01  # Minimum 1% of price
        stop_distance = max(channel_spread / 2, min_stop)  # Half channel spread, but at least 1%

        # Check trailing stop loss first (before signal-based exit)
        if position is not None and stop_distance > 0:
            if position["side"] == "long":
                # Update highest price (trailing)
                position["highest"] = max(position["highest"], high)
                # Trailing stop = highest - half channel spread
                stop_price = position["highest"] - stop_distance
                if low <= stop_price:
                    # Trailing stop triggered for long
                    exit_price = stop_price
                    exit_value = position["qty"] * exit_price
                    exit_fee = exit_value * fee_pct
                    pnl = (exit_price - position["entry"]) * position["qty"] - exit_fee
                    cash += exit_value - exit_fee
                    total_fees += exit_fee
                    trades.append(pnl)
                    if record_trades:
                        close_entry = {"action": "close", "side": "long", "close_reason": "stop_loss", "price": round(exit_price, 2), "ts": timestamps[i], "pnl": round(pnl, 2), "fee": round(exit_fee, 2)}
                        if channel_infos and channel_infos[i]:
                            ci = channel_infos[i]
                            close_entry["support"] = round(ci.get("support", 0), 2)
                            close_entry["resistance"] = round(ci.get("resistance", 0), 2)
                            close_entry["position_pct"] = round(ci.get("position_pct", 0.5), 2)
                        trades_log.append(close_entry)
                    position = None
            elif position["side"] == "short":
                # Update lowest price (trailing)
                position["lowest"] = min(position["lowest"], low)
                # Trailing stop = lowest + half channel spread
                stop_price = position["lowest"] + stop_distance
                if high >= stop_price:
                    # Trailing stop triggered for short
                    exit_price = stop_price
                    exit_cost = position["qty"] * exit_price
                    exit_fee = exit_cost * fee_pct
                    pnl = (position["entry"] - exit_price) * position["qty"] - exit_fee
                    cash -= exit_cost + exit_fee
                    total_fees += exit_fee
                    trades.append(pnl)
                    if record_trades:
                        close_entry = {"action": "close", "side": "short", "close_reason": "stop_loss", "price": round(exit_price, 2), "ts": timestamps[i], "pnl": round(pnl, 2), "fee": round(exit_fee, 2)}
                        if channel_infos and channel_infos[i]:
                            ci = channel_infos[i]
                            close_entry["support"] = round(ci.get("support", 0), 2)
                            close_entry["resistance"] = round(ci.get("resistance", 0), 2)
                            close_entry["position_pct"] = round(ci.get("position_pct", 0.5), 2)
                        trades_log.append(close_entry)
                    position = None

        if position is None:
            if score > entry_long_thr:
                entry_fee = pos_size * fee_pct
                qty = (pos_size - entry_fee) / price  # Buy slightly less due to fee
                cash -= pos_size
                total_fees += entry_fee
                position = {"side": "long", "entry": price, "qty": qty, "idx": i, "highest": price}
                if record_trades:
                    entry = {"action": "open", "side": "long", "price": round(price, 2), "ts": timestamps[i], "fee": round(entry_fee, 2), "score": round(score, 3), "spread": round(channel_spread, 2)}
                    if channel_infos and channel_infos[i]:
                        ci = channel_infos[i]
                        entry["support"] = round(ci.get("support", 0), 2)
                        entry["resistance"] = round(ci.get("resistance", 0), 2)
                        entry["position_pct"] = round(ci.get("position_pct", 0.5), 2)
                    trades_log.append(entry)
            elif allow_short and score < entry_short_thr:
                entry_fee = pos_size * fee_pct
                qty = pos_size / price
                cash += pos_size - entry_fee
                total_fees += entry_fee
                position = {"side": "short", "entry": price, "qty": qty, "idx": i, "lowest": price}
                if record_trades:
                    entry = {"action": "open", "side": "short", "price": round(price, 2), "ts": timestamps[i], "fee": round(entry_fee, 2), "score": round(score, 3), "spread": round(channel_spread, 2)}
                    if channel_infos and channel_infos[i]:
                        ci = channel_infos[i]
                        entry["support"] = round(ci.get("support", 0), 2)
                        entry["resistance"] = round(ci.get("resistance", 0), 2)
                        entry["position_pct"] = round(ci.get("position_pct", 0.5), 2)
                    trades_log.append(entry)
        elif position["side"] == "long" and score < short_thr:
            exit_value = position["qty"] * price
            exit_fee = exit_value * fee_pct
            pnl = (price - position["entry"]) * position["qty"] - exit_fee
            cash += exit_value - exit_fee
            total_fees += exit_fee
            trades.append(pnl)
            if record_trades:
                close_entry = {"action": "close", "side": "long", "close_reason": "signal", "price": round(price, 2), "ts": timestamps[i], "pnl": round(pnl, 2), "fee": round(exit_fee, 2)}
                if channel_infos and channel_infos[i]:
                    ci = channel_infos[i]
                    close_entry["support"] = round(ci.get("support", 0), 2)
                    close_entry["resistance"] = round(ci.get("resistance", 0), 2)
                    close_entry["position_pct"] = round(ci.get("position_pct", 0.5), 2)
                trades_log.append(close_entry)
            position = None
        elif position["side"] == "short" and score > long_thr:
            exit_cost = position["qty"] * price
            exit_fee = exit_cost * fee_pct
            pnl = (position["entry"] - price) * position["qty"] - exit_fee
            cash -= exit_cost + exit_fee
            total_fees += exit_fee
            trades.append(pnl)
            if record_trades:
                close_entry = {"action": "close", "side": "short", "close_reason": "signal", "price": round(price, 2), "ts": timestamps[i], "pnl": round(pnl, 2), "fee": round(exit_fee, 2)}
                if channel_infos and channel_infos[i]:
                    ci = channel_infos[i]
                    close_entry["support"] = round(ci.get("support", 0), 2)
                    close_entry["resistance"] = round(ci.get("resistance", 0), 2)
                    close_entry["position_pct"] = round(ci.get("position_pct", 0.5), 2)
                trades_log.append(close_entry)
            position = None

        if position:
            if position["side"] == "long":
                pv = position["qty"] * price  # value of shares owned
                positions[i] = 1
            else:
                # Short: we received cash from sale, now owe shares
                # pv = negative of current liability (cost to buy back)
                pv = -position["qty"] * price
                positions[i] = -1
            equity[i] = cash + pv
        else:
            equity[i] = cash
            positions[i] = 0

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

    # Buy-and-hold benchmark: what if we just bought at start and held?
    start_price = prices[LOOKBACK]
    end_price = prices[-1]
    buyhold_return = (end_price - start_price) / start_price * 100 if start_price > 0 else 0.0

    # Time in position stats
    pos_slice = positions[LOOKBACK:]
    total_bars = len(pos_slice)
    time_long_pct = (pos_slice == 1).sum() / total_bars * 100 if total_bars > 0 else 0.0
    time_short_pct = (pos_slice == -1).sum() / total_bars * 100 if total_bars > 0 else 0.0
    time_flat_pct = (pos_slice == 0).sum() / total_bars * 100 if total_bars > 0 else 0.0

    result = {
        "return_pct": round(ret, 4),
        "sharpe": round(sharpe, 4),
        "num_trades": int(len(pnls)),
        "win_rate": round(win_rate, 2),
        "profit_factor": round(min(pf, 999.0), 4),
        "max_dd": round(max_dd, 4),
        "total_fees": round(total_fees, 2),
        "entry_bias": round(entry_bias, 4),
        "buyhold_return": round(float(buyhold_return), 4),
        "beats_buyhold": bool(ret > buyhold_return),
        "time_long_pct": round(time_long_pct, 1),
        "time_short_pct": round(time_short_pct, 1),
        "time_flat_pct": round(time_flat_pct, 1),
    }

    if record_trades:
        # Downsample equity to max 300 points for storage
        step = max(1, len(eq) // 300)
        ts_slice = timestamps[LOOKBACK::step]
        eq_slice = eq[::step].tolist()
        pos_slice_sampled = pos_slice[::step].tolist()
        result["equity_curve"] = [
            {"ts": ts_slice[i], "eq": round(eq_slice[i], 2), "pos": int(pos_slice_sampled[i])}
            for i in range(min(len(ts_slice), len(eq_slice), len(pos_slice_sampled)))
        ]
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

    # Integrate any new signals added since last saved version (using DEFAULT_WEIGHTS)
    from src.engine.scoring import DEFAULT_WEIGHTS
    new_signals = [n for n in SIGNAL_NAMES if n not in current_weights]
    if new_signals:
        for n in new_signals:
            default_w = DEFAULT_WEIGHTS.get(n, 0.05)
            current_weights[n] = default_w
            print(f"{Fore.YELLOW}  New signal: {n} — seeding at {default_w:.2f}{Style.RESET_ALL}")
    # Drop signals removed from ALL_SIGNALS
    current_weights = {k: v for k, v in current_weights.items() if k in SIGNAL_NAMES}
    total = sum(current_weights.values())
    if total > 0:
        current_weights = {k: v / total for k, v in current_weights.items()}

    evolution_start = time.time()

    print(f"\n{Fore.CYAN}Evolution v{version} -> {n_mutations} mutations (sigma={sigma}, thr={current_threshold:.3f}, bias={current_entry_bias:.3f}){Style.RESET_ALL}")
    top = sorted(current_weights, key=current_weights.get, reverse=True)
    print("  Current: " + "  ".join(f"{k}={current_weights[k]:.3f}" for k in top if current_weights[k] > 0.01))

    update_evolution_progress("fetching", 5, f"Fetching {symbol} historical data...")
    df_train, df_test = fetch_bars(symbol)

    if len(df_train) < LOOKBACK + 50 or len(df_test) < LOOKBACK + 10:
        print(f"{Fore.RED}Not enough bars to evolve.{Style.RESET_ALL}")
        return

    update_evolution_progress("computing_signals", 15, "Computing signal matrices...")
    print("  Computing signal matrices...")
    signal_start = time.time()
    # Use step=5 for training (5x faster, slight precision loss is OK for selection)
    mat_train, spreads_train, _ = compute_signal_matrix(df_train, "Train ", step=5)
    update_evolution_progress("computing_signals", 40, "Train signals done, computing test signals...")
    # Use step=1 for test (full precision for final evaluation, profile to see bottlenecks)
    mat_test, spreads_test, channel_infos_test = compute_signal_matrix(df_test, "Test  ", step=1, profile=True)
    signal_duration = time.time() - signal_start
    print(f"  {Fore.CYAN}Signal computation took {signal_duration:.1f}s{Style.RESET_ALL}")

    # Show channel spread stats
    valid_spreads = spreads_test[spreads_test > 0]
    if len(valid_spreads) > 0:
        print(f"  Channel spread: avg=${valid_spreads.mean():.2f}, min=${valid_spreads.min():.2f}, max=${valid_spreads.max():.2f}")

    current_arr = np.array([current_weights.get(n, 0.0) for n in SIGNAL_NAMES], dtype=np.float32)
    current_oos = simulate(df_test, mat_test, current_arr, spreads_test, current_threshold, -current_threshold,
                           entry_bias=current_entry_bias)

    update_evolution_progress("evaluating", 50, "Evaluating current strategy...")
    candidates = [{"weights": current_weights, "arr": current_arr, "oos": current_oos,
                   "threshold": current_threshold, "entry_bias": current_entry_bias, "label": "current"}]
    for i in range(n_mutations):
        update_evolution_progress("evaluating", 50 + int(40 * (i + 1) / n_mutations), f"Testing mutation {i+1}/{n_mutations}...")
        w_dict = mutate(current_weights, sigma)
        w_arr = np.array([w_dict.get(n, 0.0) for n in SIGNAL_NAMES], dtype=np.float32)
        thr = mutate_threshold(current_threshold, sigma)
        bias = mutate_entry_bias(current_entry_bias, sigma)
        oos = simulate(df_test, mat_test, w_arr, spreads_test, thr, -thr, entry_bias=bias)
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
        print(f"\n  {Fore.YELLOW}Current strategy is best — keeping v{version}.{Style.RESET_ALL}")
        # Update performance metrics with current test results (includes fees now)
        is_stats = simulate(df_train, mat_train, current_arr, spreads_train, current_threshold, -current_threshold, entry_bias=current_entry_bias)
        oos_full = simulate(df_test, mat_test, current_arr, spreads_test, current_threshold, -current_threshold, record_trades=True, entry_bias=current_entry_bias, channel_infos=channel_infos_test)
        update_performance(version, {
            "in_sample": is_stats,
            "out_of_sample": oos_full,
            "threshold": current_threshold,
            "entry_bias": current_entry_bias,
            "evolution_duration_sec": round(evolution_duration, 1),
            "signal_computation_sec": round(signal_duration, 1),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
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
    is_stats = simulate(df_train, mat_train, best["arr"], spreads_train, best_thr, -best_thr, entry_bias=best_bias)
    best_oos_full = simulate(df_test, mat_test, best["arr"], spreads_test, best_thr, -best_thr, record_trades=True, entry_bias=best_bias, channel_infos=channel_infos_test)
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
    print(f"  {'Signal':<12} {'Old':>7} {'New':>7} {'Diff':>7}")
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
    update_evolution_progress("idle", 100, f"Completed v{new_version if best['label'] != 'current' else version}")
