"use client";

type Props = {
  score: number | null;
  openPosition: { side: string; entryPrice: number } | null;
  signalValues: Record<string, number> | null;
  weights: Record<string, number> | null;
  threshold?: number;
  entryBias?: number;
};

const SIGNAL_COLORS: Record<string, string> = {
  momentum: "#6366f1",
  rsi: "#8b5cf6",
  bollinger: "#06b6d4",
  vwap: "#0ea5e9",
  atr: "#f59e0b",
  volume: "#10b981",
  breakout: "#f43f5e",
  channel_position: "#ec4899",
  channel_slope: "#a855f7",
  channel_trend: "#14b8a6",
};

export function ScoreGauge({ score, openPosition, signalValues, weights, threshold = 0.15, entryBias = 0.03 }: Props) {
  const noData = score === null;
  const s = score ?? 0;

  // LONG-ONLY thresholds
  const EXIT_THR = threshold;             // Exit when score drops below this
  const ENTRY_THR = threshold + entryBias; // Enter when score rises above this

  // Position of elements as % along the 0…+1 bar (we only show positive half)
  // Map 0 → 0%, +1 → 100%
  const needlePct = Math.max(0, Math.min(100, s * 100));
  const exitThrPct = EXIT_THR * 100;
  const entryThrPct = ENTRY_THR * 100;

  // Status
  let status = "";
  let statusColor = "#9ca3af";
  if (!noData) {
    if (openPosition) {
      // We have a position - are we above exit threshold?
      if (s >= EXIT_THR) {
        status = "HOLDING (above exit)";
        statusColor = "#10b981";
      } else {
        status = "EXIT SIGNAL (below exit threshold)";
        statusColor = "#f59e0b";
      }
    } else {
      // No position - are we above entry threshold?
      if (s >= ENTRY_THR) {
        status = "BUY SIGNAL (above entry)";
        statusColor = "#10b981";
      } else if (s >= EXIT_THR) {
        status = "Neutral (in hysteresis zone)";
        statusColor = "#6ee7b7";
      } else {
        status = "Neutral (below thresholds)";
        statusColor = "#9ca3af";
      }
    }
  }

  const scoreColor = s >= ENTRY_THR ? "#10b981" : s >= EXIT_THR ? "#6ee7b7" : s >= 0 ? "#9ca3af" : "#fca5a5";

  return (
    <div className="space-y-4">
      {/* Score number */}
      <div className="flex items-baseline gap-3">
        <span
          className="text-4xl font-bold tabular-nums"
          style={{ color: noData ? "#4b5563" : scoreColor }}
        >
          {noData ? "—" : (s >= 0 ? "+" : "") + s.toFixed(3)}
        </span>
        <div className="text-xs leading-tight">
          <div className="text-gray-500">composite score</div>
          {!noData && <div style={{ color: statusColor }}>{status}</div>}
        </div>
      </div>

      {/* Gauge bar - only positive side (0 to +1) */}
      <div className="relative h-8 rounded-full bg-[#2a2d3a] overflow-hidden">
        {/* Entry zone (green) - everything above entry threshold */}
        <div
          className="absolute top-0 bottom-0 right-0"
          style={{ width: `${100 - entryThrPct}%`, background: "rgba(16,185,129,0.2)" }}
        />
        {/* Hysteresis zone (yellow-ish) - between exit and entry */}
        <div
          className="absolute top-0 bottom-0"
          style={{
            left: `${exitThrPct}%`,
            width: `${entryThrPct - exitThrPct}%`,
            background: "rgba(251,191,36,0.1)"
          }}
        />

        {/* Exit threshold marker */}
        <div
          className="absolute top-0 bottom-0 w-0.5 bg-amber-500/70"
          style={{ left: `${exitThrPct}%` }}
        />
        {/* Entry threshold marker */}
        <div
          className="absolute top-0 bottom-0 w-0.5 bg-green-500/70"
          style={{ left: `${entryThrPct}%` }}
        />

        {/* Needle */}
        {!noData && (
          <div
            className="absolute top-1 bottom-1 w-2 rounded-full shadow-lg transition-all duration-700"
            style={{
              left: `calc(${needlePct}% - 4px)`,
              backgroundColor: scoreColor,
              boxShadow: `0 0 8px ${scoreColor}50`
            }}
          />
        )}
      </div>

      {/* Labels - simple */}
      <div className="flex justify-between text-xs px-1">
        <span className="text-gray-600">0</span>
        <span className="text-amber-500">
          exit {EXIT_THR.toFixed(2)}
        </span>
        <span className="text-green-500">
          entry {ENTRY_THR.toFixed(2)}
        </span>
        <span className="text-gray-600">+1.0</span>
      </div>

      {/* Bias info */}
      {entryBias > 0 && (
        <div className="text-[10px] text-gray-600 text-center">
          hysteresis: entry − exit = {entryBias.toFixed(3)} (prevents rapid switching)
        </div>
      )}

      {/* Open position */}
      {openPosition && (
        <div className="text-xs px-3 py-2 rounded-lg font-medium bg-green-500/10 text-green-400 border border-green-500/20">
          Open LONG @ ${Number(openPosition.entryPrice).toLocaleString("en", { minimumFractionDigits: 2 })}
        </div>
      )}

      {/* Per-signal breakdown */}
      {signalValues && (
        <div className="space-y-0.5 pt-1">
          <div className="grid grid-cols-[1fr_auto_auto_auto] gap-x-2 text-[10px] text-gray-600 uppercase tracking-wide px-2 pb-1">
            <span>Signal</span>
            <span className="text-right">raw</span>
            <span className="text-right">×w</span>
            <span className="text-right w-10">contrib</span>
          </div>
          {Object.entries(signalValues)
            .sort(([, a], [, b]) => Math.abs(Number(b)) - Math.abs(Number(a)))
            .map(([name, val]) => {
              const v = Number(val);
              const w = weights?.[name] ?? null;
              const contrib = w !== null ? v * w : null;
              const color = SIGNAL_COLORS[name] ?? "#6b7280";
              const rawColor = v > 0 ? "#6ee7b7" : v < 0 ? "#fca5a5" : "#6b7280";
              const contribColor = contrib !== null ? (contrib > 0 ? "#6ee7b7" : contrib < 0 ? "#fca5a5" : "#6b7280") : "#4b5563";
              return (
                <div key={name} className="grid grid-cols-[1fr_auto_auto_auto] gap-x-2 items-center text-xs px-2 py-1 rounded bg-[#2a2d3a]/50">
                  <div className="flex items-center gap-1.5">
                    <div className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: color }} />
                    <span className="text-gray-400 capitalize truncate">{name.replace("_", " ")}</span>
                  </div>
                  <span className="font-mono text-right" style={{ color: rawColor }}>
                    {v >= 0 ? "+" : ""}{v.toFixed(3)}
                  </span>
                  <span className="font-mono text-right text-gray-600 text-[10px]">
                    {w !== null ? w.toFixed(3) : "—"}
                  </span>
                  <span className="font-mono text-right w-10" style={{ color: contribColor }}>
                    {contrib !== null ? ((contrib >= 0 ? "+" : "") + contrib.toFixed(3)) : "—"}
                  </span>
                </div>
              );
            })}
        </div>
      )}

      {noData && (
        <p className="text-xs text-gray-600">
          No live signal data yet — start the trading loop to see live scores.
        </p>
      )}
    </div>
  );
}
