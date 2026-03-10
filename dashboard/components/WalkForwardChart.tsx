"use client";

import { useMemo } from "react";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, Legend, ReferenceLine,
} from "recharts";

type WeightRow = {
  id: string;
  version: number;
  weights: Record<string, number>;
  performance: {
    in_sample?: { return_pct: number; sharpe: number };
    out_of_sample?: { return_pct: number; sharpe: number };
  } | null;
  created_at: string;
};

export function WalkForwardChart({ rows }: { rows: WeightRow[] }) {
  const dataRows = useMemo(() => {
    if (!rows.length) return [];

    // Filter to last 24 hours and sort by time ascending
    const oneDayAgo = Date.now() - 24 * 60 * 60 * 1000;
    const recentRows = rows
      .filter((r) => new Date(r.created_at).getTime() > oneDayAgo)
      .sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime());

    // If no data in last 24 hours, show all data (up to 50 points)
    return recentRows.length > 0 ? recentRows : rows.slice(0, 50).reverse();
  }, [rows]);

  const data = useMemo(() => {
    return dataRows.map((r) => {
      const ins = r.performance?.in_sample;
      const oos = r.performance?.out_of_sample;
      return {
        time: new Date(r.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        version: `v${r.version}`,
        "In-sample": ins?.return_pct != null ? +ins.return_pct.toFixed(2) : null,
        "Out-of-sample": oos?.return_pct != null ? +oos.return_pct.toFixed(2) : null,
      };
    });
  }, [dataRows]);

  if (!data.length) return null;

  return (
    <div className="bg-[#1a1d27] rounded-xl border border-[#2a2d3a] p-4">
      <h3 className="text-xs text-gray-500 uppercase tracking-wide mb-3">
        Evolution Performance (last 24 hours)
      </h3>
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={data} margin={{ top: 5, right: 20, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#2a2d3a" />
          <XAxis dataKey="time" tick={{ fill: "#6b7280", fontSize: 11 }} tickLine={false} axisLine={false} />
          <YAxis tick={{ fill: "#6b7280", fontSize: 11 }} tickLine={false} axisLine={false}
            tickFormatter={(v) => `${v}%`} />
          <Tooltip
            contentStyle={{ background: "#1a1d27", border: "1px solid #2a2d3a", borderRadius: 8, fontSize: 12 }}
            labelFormatter={(label, payload) => {
              const item = payload?.[0]?.payload;
              return item ? `${item.version} @ ${label}` : label;
            }}
            formatter={(v: number, name: string) => [`${v >= 0 ? "+" : ""}${v}%`, name]}
          />
          <Legend wrapperStyle={{ fontSize: 11, color: "#6b7280" }} />
          <ReferenceLine y={0} stroke="#2a2d3a" />
          <Line type="monotone" dataKey="In-sample" stroke="#6366f1" strokeWidth={2} dot={{ r: 3 }} />
          <Line type="monotone" dataKey="Out-of-sample" stroke="#10b981" strokeWidth={2} dot={{ r: 3 }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
