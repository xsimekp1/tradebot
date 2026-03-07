"use client";

import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, Legend,
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

export function WeightHistoryChart({ rows }: { rows: WeightRow[] }) {
  if (rows.length < 2) {
    return (
      <p className="text-sm text-gray-500 text-center py-8">
        Need at least 2 versions to show history. Run more evolution cycles.
      </p>
    );
  }

  // Chronological order (oldest → newest left → right)
  const sorted = [...rows].sort((a, b) => a.version - b.version);

  // Collect all signal names present across all versions
  const signals = Array.from(
    new Set(sorted.flatMap((r) => Object.keys(r.weights)))
  );

  const data = sorted.map((r) => ({
    label: `v${r.version}`,
    active: r.is_active,
    ...Object.fromEntries(
      signals.map((s) => [s, r.weights[s] != null ? +Number(r.weights[s]).toFixed(3) : 0])
    ),
  }));

  return (
    <ResponsiveContainer width="100%" height={320}>
      <LineChart data={data} margin={{ top: 8, right: 24, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#2a2d3a" />
        <XAxis
          dataKey="label"
          tick={{ fill: "#6b7280", fontSize: 11 }}
          tickLine={false}
          axisLine={false}
        />
        <YAxis
          tick={{ fill: "#6b7280", fontSize: 11 }}
          tickLine={false}
          axisLine={false}
          tickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
          domain={[0, "auto"]}
        />
        <Tooltip
          contentStyle={{ background: "#1a1d27", border: "1px solid #2a2d3a", borderRadius: 8, fontSize: 12 }}
          formatter={(v: number, name: string) => [`${(v * 100).toFixed(1)}%`, name]}
        />
        <Legend wrapperStyle={{ fontSize: 11, color: "#9ca3af", paddingTop: 8 }} />
        {signals.map((signal) => (
          <Line
            key={signal}
            type="monotone"
            dataKey={signal}
            stroke={SIGNAL_COLORS[signal] ?? "#6b7280"}
            strokeWidth={2}
            dot={{ r: 3, strokeWidth: 0 }}
            activeDot={{ r: 5 }}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
