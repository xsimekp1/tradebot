"use client";

import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";

type EquityRow = {
  timestamp: string;
  total_equity: string;
  daily_pnl: string;
};

export function EquityChart({ data }: { data: EquityRow[] }) {
  if (!data || data.length === 0) {
    return (
      <div className="h-52 flex items-center justify-center text-gray-600 text-sm">
        No equity data yet — bot hasn't run yet
      </div>
    );
  }

  const baseline = Number(data[0]?.total_equity ?? 100000);
  const chartData = data.map((r) => ({
    time: new Date(r.timestamp).getTime(),
    equity: Number(r.total_equity),
    pnl: Number(r.total_equity) - baseline,
  }));

  const latest = chartData[chartData.length - 1]?.equity ?? 0;
  const isUp = latest >= baseline;
  const color = isUp ? "#4ade80" : "#f87171";

  const domainPad = (latest - baseline) * 0.3 || 100;
  const yMin = Math.min(baseline, latest) - Math.abs(domainPad);
  const yMax = Math.max(baseline, latest) + Math.abs(domainPad);

  return (
    <ResponsiveContainer width="100%" height={220}>
      <AreaChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="eqGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={color} stopOpacity={0.3} />
            <stop offset="95%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#2a2d3a" />
        <XAxis
          dataKey="time"
          type="number"
          scale="time"
          domain={["dataMin", "dataMax"]}
          tick={{ fill: "#6b7280", fontSize: 11 }}
          tickLine={false}
          axisLine={false}
          tickFormatter={(v) => new Date(v).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
          tickCount={6}
        />
        <YAxis
          tick={{ fill: "#6b7280", fontSize: 11 }}
          tickLine={false}
          axisLine={false}
          tickFormatter={(v) => `$${(v / 1000).toFixed(1)}k`}
          domain={[yMin, yMax]}
          width={55}
        />
        <Tooltip
          contentStyle={{ background: "#1a1d27", border: "1px solid #2a2d3a", borderRadius: 8, fontSize: 12 }}
          formatter={(v: number, name: string) => [
            name === "equity" ? `$${v.toLocaleString("en", { minimumFractionDigits: 2 })}` : `$${v >= 0 ? "+" : ""}${v.toFixed(2)}`,
            name === "equity" ? "Equity" : "P&L",
          ]}
        />
        <Area
          type="monotone"
          dataKey="equity"
          stroke={color}
          strokeWidth={2}
          fill="url(#eqGrad)"
          dot={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
