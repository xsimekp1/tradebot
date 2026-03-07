"use client";

import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, ReferenceLine,
} from "recharts";

type WeightRow = {
  version: number;
  weights: Record<string, number>;
  performance: Record<string, unknown> | null;
  is_active: boolean;
  created_at: string;
};

function getThreshold(r: WeightRow): number | null {
  if (r.performance?.threshold != null) return Number(r.performance.threshold);
  if (r.weights._threshold != null) return Number(r.weights._threshold);
  return null;
}

export function ThresholdHistoryChart({ rows }: { rows: WeightRow[] }) {
  const sorted = [...rows]
    .filter((r) => getThreshold(r) != null)
    .sort((a, b) => a.version - b.version);

  if (sorted.length < 2) {
    return (
      <p className="text-sm text-gray-500 text-center py-8">
        Need at least 2 versions with threshold data.
      </p>
    );
  }

  const data = sorted.map((r) => ({
    label: `v${r.version}`,
    threshold: +Number(getThreshold(r)).toFixed(4),
    active: r.is_active,
  }));

  return (
    <ResponsiveContainer width="100%" height={200}>
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
          tickFormatter={(v) => v.toFixed(2)}
          domain={[0.04, 0.42]}
        />
        <Tooltip
          contentStyle={{ background: "#1a1d27", border: "1px solid #2a2d3a", borderRadius: 8, fontSize: 12 }}
          formatter={(v: number) => [v.toFixed(4), "threshold"]}
        />
        <ReferenceLine y={0.15} stroke="#4b5563" strokeDasharray="4 4" label={{ value: "default 0.15", fill: "#4b5563", fontSize: 10 }} />
        <Line
          type="monotone"
          dataKey="threshold"
          stroke="#f59e0b"
          strokeWidth={2}
          dot={{ r: 3, strokeWidth: 0, fill: "#f59e0b" }}
          activeDot={{ r: 5 }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
