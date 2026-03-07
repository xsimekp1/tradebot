"use client";

const LONG_THR = 0.15;
const SHORT_THR = -0.15;

type Props = {
  score: number | null;
  openPosition: { side: string; entryPrice: number } | null;
  signalValues: Record<string, number> | null;
  weights: Record<string, number> | null;
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
};

export function ScoreGauge({ score, openPosition, signalValues, weights }: Props) {
  const noData = score === null;
  const s = score ?? 0;

  // Position of needle as % along the -1…+1 bar
  const needlePct = ((s + 1) / 2) * 100;
  const longThrPct = ((LONG_THR + 1) / 2) * 100;
  const shortThrPct = ((SHORT_THR + 1) / 2) * 100;

  // Distance to nearest threshold
  let distLabel = "";
  let distPct = 0;
  let direction = "";
  if (!noData) {
    if (s >= LONG_THR) {
      direction = "LONG active";
      distLabel = `Score above LONG threshold`;
      distPct = 100;
    } else if (s <= SHORT_THR) {
      direction = "SHORT active";
      distLabel = `Score below SHORT threshold`;
      distPct = 100;
    } else if (s >= 0) {
      distPct = (s / LONG_THR) * 100;
      distLabel = `${distPct.toFixed(0)}% toward LONG`;
      direction = "neutral";
    } else {
      distPct = (Math.abs(s) / Math.abs(SHORT_THR)) * 100;
      distLabel = `${distPct.toFixed(0)}% toward SHORT`;
      direction = "neutral";
    }
  }

  const scoreColor =
    s >= LONG_THR ? "#10b981" :
    s <= SHORT_THR ? "#f43f5e" :
    s > 0 ? "#6ee7b7" : s < 0 ? "#fca5a5" : "#9ca3af";

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
        <div className="text-xs text-gray-500 leading-tight">
          <div>composite score</div>
          {!noData && <div style={{ color: scoreColor }}>{distLabel}</div>}
        </div>
      </div>

      {/* Gauge bar */}
      <div className="relative h-6 rounded-full bg-[#2a2d3a] overflow-hidden">
        {/* Short zone */}
        <div
          className="absolute top-0 bottom-0 left-0"
          style={{ width: `${shortThrPct}%`, background: "rgba(244,63,94,0.15)" }}
        />
        {/* Long zone */}
        <div
          className="absolute top-0 bottom-0 right-0"
          style={{ width: `${100 - longThrPct}%`, background: "rgba(16,185,129,0.15)" }}
        />
        {/* Short threshold marker */}
        <div
          className="absolute top-0 bottom-0 w-px bg-red-500/50"
          style={{ left: `${shortThrPct}%` }}
        />
        {/* Long threshold marker */}
        <div
          className="absolute top-0 bottom-0 w-px bg-green-500/50"
          style={{ left: `${longThrPct}%` }}
        />
        {/* Center marker */}
        <div
          className="absolute top-1 bottom-1 w-px bg-gray-600"
          style={{ left: "50%" }}
        />
        {/* Needle */}
        {!noData && (
          <div
            className="absolute top-1 bottom-1 w-1.5 rounded-full shadow-lg transition-all duration-700"
            style={{ left: `calc(${needlePct}% - 3px)`, backgroundColor: scoreColor }}
          />
        )}
      </div>

      {/* Labels */}
      <div className="flex justify-between text-xs text-gray-600">
        <span>SHORT −1.0</span>
        <span className="text-red-500/60">−{Math.abs(SHORT_THR)}</span>
        <span>0</span>
        <span className="text-green-500/60">+{LONG_THR}</span>
        <span>LONG +1.0</span>
      </div>

      {/* Open position */}
      {openPosition && (
        <div className={`text-xs px-3 py-2 rounded-lg font-medium ${
          openPosition.side === "long"
            ? "bg-green-500/10 text-green-400 border border-green-500/20"
            : "bg-red-500/10 text-red-400 border border-red-500/20"
        }`}>
          Open {openPosition.side.toUpperCase()} @ ${Number(openPosition.entryPrice).toLocaleString("en", { minimumFractionDigits: 2 })}
        </div>
      )}

      {/* Per-signal breakdown */}
      {signalValues && (
        <div className="space-y-0.5 pt-1">
          {/* Header */}
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
