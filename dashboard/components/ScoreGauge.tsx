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

  // Two-sided thresholds (from config)
  const LONG_ENTRY = threshold + entryBias;   // +0.18
  const LONG_EXIT = threshold;                 // +0.15
  const SHORT_ENTRY = -(threshold + entryBias); // -0.18
  const SHORT_EXIT = -threshold;               // -0.15

  // Map score from -1...+1 to 0%...100%
  const needlePct = Math.max(0, Math.min(100, (s + 1) * 50));

  // Threshold positions on -1 to +1 scale (mapped to 0-100%)
  const longEntryPct = (LONG_ENTRY + 1) * 50;   // ~59%
  const longExitPct = (LONG_EXIT + 1) * 50;     // ~57.5%
  const shortEntryPct = (SHORT_ENTRY + 1) * 50; // ~41%
  const shortExitPct = (SHORT_EXIT + 1) * 50;   // ~42.5%

  // Status based on score and position
  let status = "";
  let statusColor = "#9ca3af";
  if (!noData) {
    if (openPosition?.side === "long") {
      if (s >= LONG_EXIT) {
        status = "HOLDING LONG";
        statusColor = "#10b981";
      } else {
        status = "EXIT LONG SIGNAL";
        statusColor = "#f59e0b";
      }
    } else if (openPosition?.side === "short") {
      if (s <= SHORT_EXIT) {
        status = "HOLDING SHORT";
        statusColor = "#ef4444";
      } else {
        status = "EXIT SHORT SIGNAL";
        statusColor = "#f59e0b";
      }
    } else {
      // No position
      if (s >= LONG_ENTRY) {
        status = "BUY SIGNAL";
        statusColor = "#10b981";
      } else if (s <= SHORT_ENTRY) {
        status = "SHORT SIGNAL";
        statusColor = "#ef4444";
      } else {
        status = "Neutral";
        statusColor = "#9ca3af";
      }
    }
  }

  // Color based on score position
  const scoreColor = s >= LONG_ENTRY ? "#10b981" : s <= SHORT_ENTRY ? "#ef4444" : "#9ca3af";

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

      {/* Two-sided gauge bar: -1 to +1 */}
      <div className="relative h-8 rounded-full bg-[#2a2d3a] overflow-hidden">
        {/* SHORT zone (left, red) - below short entry */}
        <div
          className="absolute top-0 bottom-0 left-0"
          style={{ width: `${shortEntryPct}%`, background: "rgba(239,68,68,0.15)" }}
        />
        {/* LONG zone (right, green) - above long entry */}
        <div
          className="absolute top-0 bottom-0 right-0"
          style={{ width: `${100 - longEntryPct}%`, background: "rgba(16,185,129,0.15)" }}
        />

        {/* Center line (zero) */}
        <div
          className="absolute top-0 bottom-0 w-0.5 bg-gray-600"
          style={{ left: "50%" }}
        />

        {/* Short entry threshold marker (left) */}
        <div
          className="absolute top-0 bottom-0 w-0.5 bg-red-500/70"
          style={{ left: `${shortEntryPct}%` }}
        />
        {/* Short exit threshold marker */}
        <div
          className="absolute top-0 bottom-0 w-0.5 bg-red-400/40"
          style={{ left: `${shortExitPct}%` }}
        />

        {/* Long exit threshold marker */}
        <div
          className="absolute top-0 bottom-0 w-0.5 bg-green-400/40"
          style={{ left: `${longExitPct}%` }}
        />
        {/* Long entry threshold marker (right) */}
        <div
          className="absolute top-0 bottom-0 w-0.5 bg-green-500/70"
          style={{ left: `${longEntryPct}%` }}
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

      {/* Labels */}
      <div className="flex justify-between text-xs px-1">
        <span className="text-red-500">-1</span>
        <span className="text-red-400 text-[10px]">short {SHORT_ENTRY.toFixed(2)}</span>
        <span className="text-gray-600">0</span>
        <span className="text-green-400 text-[10px]">long {LONG_ENTRY.toFixed(2)}</span>
        <span className="text-green-500">+1</span>
      </div>

      {/* Open position */}
      {openPosition && (
        <div className={`text-xs px-3 py-2 rounded-lg font-medium border ${
          openPosition.side === "long"
            ? "bg-green-500/10 text-green-400 border-green-500/20"
            : "bg-red-500/10 text-red-400 border-red-500/20"
        }`}>
          Open {openPosition.side.toUpperCase()} @ ${Number(openPosition.entryPrice).toLocaleString("en", { minimumFractionDigits: 2 })}
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
