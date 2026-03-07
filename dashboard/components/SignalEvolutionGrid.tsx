"use client";

import {
  AreaChart, Area, ResponsiveContainer, Tooltip, ReferenceLine, YAxis,
} from "recharts";

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

type WeightRow = {
  version: number;
  weights: Record<string, number>;
  is_active: boolean;
  created_at: string;
};

export function SignalEvolutionGrid({ rows }: { rows: WeightRow[] }) {
  if (rows.length === 0) return null;

  // Chronological order
  const sorted = [...rows].sort((a, b) => a.version - b.version);

  // All signal names across all versions
  const signals = Array.from(
    new Set(sorted.flatMap((r) => Object.keys(r.weights)))
  ).sort();

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
      {signals.map((signal) => {
        const color = SIGNAL_COLORS[signal] ?? "#6b7280";
        const data = sorted.map((r) => ({
          v: `v${r.version}`,
          w: r.weights[signal] != null ? +Number(r.weights[signal]).toFixed(4) : 0,
          active: r.is_active,
        }));

        const current = data[data.length - 1]?.w ?? 0;
        const first = data[0]?.w ?? 0;
        const delta = current - first;
        const max = Math.max(...data.map((d) => d.w));
        const min = Math.min(...data.map((d) => d.w));
        const range = max - min;

        const trendColor =
          delta > 0.005 ? "#10b981" :
          delta < -0.005 ? "#f43f5e" :
          "#6b7280";

        return (
          <div
            key={signal}
            className="bg-[#1a1d27] rounded-xl border border-[#2a2d3a] p-3 space-y-2"
          >
            {/* Header */}
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium capitalize" style={{ color }}>
                {signal}
              </span>
              <span className="text-xs font-mono text-gray-300">
                {(current * 100).toFixed(1)}%
              </span>
            </div>

            {/* Sparkline */}
            <ResponsiveContainer width="100%" height={56}>
              <AreaChart data={data} margin={{ top: 4, right: 2, left: 2, bottom: 0 }}>
                <YAxis domain={[0.05, 0.30]} hide />
                <defs>
                  <linearGradient id={`grad-${signal}`} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={color} stopOpacity={0.3} />
                    <stop offset="95%" stopColor={color} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <Tooltip
                  contentStyle={{
                    background: "#0f1117",
                    border: `1px solid ${color}40`,
                    borderRadius: 6,
                    fontSize: 11,
                    padding: "4px 8px",
                  }}
                  formatter={(v: number) => [`${(v * 100).toFixed(2)}%`, signal]}
                  labelFormatter={(l) => l}
                />
                {data.length > 1 && (
                  <ReferenceLine
                    y={first}
                    stroke="#ffffff10"
                    strokeDasharray="3 3"
                  />
                )}
                <Area
                  type="monotone"
                  dataKey="w"
                  stroke={color}
                  strokeWidth={1.5}
                  fill={`url(#grad-${signal})`}
                  dot={data.length <= 10
                    ? { r: 2, fill: color, strokeWidth: 0 }
                    : false
                  }
                  activeDot={{ r: 4, fill: color, strokeWidth: 0 }}
                />
              </AreaChart>
            </ResponsiveContainer>

            {/* Footer: delta + range */}
            <div className="flex items-center justify-between text-xs">
              <span style={{ color: trendColor }} className="font-mono">
                {delta >= 0 ? "+" : ""}{(delta * 100).toFixed(1)}%
              </span>
              <span className="text-gray-600 font-mono text-[10px]">
                {sorted.length}v · Δ{(range * 100).toFixed(1)}%
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
