"use client";

import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, Legend, ReferenceLine,
} from "recharts";

type Run = Record<string, unknown>;

export function WalkForwardChart({ runs }: { runs: Run[] }) {
  if (!runs.length) return null;

  const data = runs.map((r) => {
    const ins = r.in_sample as Record<string, number> | null;
    const oos = r.out_of_sample as Record<string, number> | null;
    return {
      label: `${String(r.train_days)}d train`,
      "In-sample": ins?.return_pct != null ? +ins.return_pct.toFixed(2) : null,
      "Out-of-sample": oos?.return_pct != null ? +oos.return_pct.toFixed(2) : null,
      oosSharpe: oos?.sharpe,
    };
  }).reverse();

  return (
    <div className="bg-[#1a1d27] rounded-xl border border-[#2a2d3a] p-4">
      <h3 className="text-xs text-gray-500 uppercase tracking-wide mb-3">
        In-sample vs Out-of-sample Return (%)
      </h3>
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={data} margin={{ top: 5, right: 20, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#2a2d3a" />
          <XAxis dataKey="label" tick={{ fill: "#6b7280", fontSize: 11 }} tickLine={false} axisLine={false} />
          <YAxis tick={{ fill: "#6b7280", fontSize: 11 }} tickLine={false} axisLine={false}
            tickFormatter={(v) => `${v}%`} />
          <Tooltip
            contentStyle={{ background: "#1a1d27", border: "1px solid #2a2d3a", borderRadius: 8, fontSize: 12 }}
            formatter={(v: number, name: string) => [`${v >= 0 ? "+" : ""}${v}%`, name]}
          />
          <Legend wrapperStyle={{ fontSize: 11, color: "#6b7280" }} />
          <ReferenceLine y={0} stroke="#2a2d3a" />
          <Bar dataKey="In-sample" fill="#6366f1" radius={[4, 4, 0, 0]} />
          <Bar dataKey="Out-of-sample" fill="#10b981" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
