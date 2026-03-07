"use client";

import {
  ComposedChart, Line, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, ReferenceLine,
} from "recharts";

type Candle = { time: number; close: number };
type Trade = {
  side: string;
  entry_price: string;
  exit_price: string | null;
  opened_at: string;
  closed_at: string | null;
};

type Props = { prices: Candle[]; trades: Trade[] };

type DotProps = { cx?: number; cy?: number; payload?: { buy?: number; sell?: number } };

function BuyDot({ cx = 0, cy = 0, payload }: DotProps) {
  if (!payload?.buy) return null;
  return <polygon points={`${cx},${cy - 8} ${cx - 6},${cy + 4} ${cx + 6},${cy + 4}`} fill="#4ade80" opacity={0.95} />;
}

function SellDot({ cx = 0, cy = 0, payload }: DotProps) {
  if (!payload?.sell) return null;
  return <polygon points={`${cx},${cy + 8} ${cx - 6},${cy - 4} ${cx + 6},${cy - 4}`} fill="#f87171" opacity={0.95} />;
}

export function PriceChart({ prices, trades }: Props) {
  if (!prices || prices.length === 0) {
    return (
      <div className="h-64 flex items-center justify-center text-gray-600 text-sm">
        Loading price data...
      </div>
    );
  }

  const snapToCandle = (ts: number) => {
    const times = prices.map((p) => p.time);
    return times.reduce((a, b) => (Math.abs(b - ts) < Math.abs(a - ts) ? b : a));
  };

  const buyMap = new Map<number, number>();
  const sellMap = new Map<number, number>();

  trades.forEach((t) => {
    const snap = snapToCandle(new Date(t.opened_at).getTime());
    if (Number(t.entry_price) > 0) buyMap.set(snap, Number(t.entry_price));
    if (t.closed_at && t.exit_price) {
      const snapClose = snapToCandle(new Date(t.closed_at).getTime());
      sellMap.set(snapClose, Number(t.exit_price));
    }
  });

  const data = prices.map((p) => ({
    time: p.time,
    close: p.close,
    buy: buyMap.get(p.time) ?? null,
    sell: sellMap.get(p.time) ?? null,
  }));

  const closes = prices.map((p) => p.close);
  const yMin = Math.min(...closes) * 0.9994;
  const yMax = Math.max(...closes) * 1.0006;

  const openTrades = trades.filter((t) => !t.closed_at && Number(t.entry_price) > 0);

  return (
    <ResponsiveContainer width="100%" height={260}>
      <ComposedChart data={data} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#2a2d3a" />
        <XAxis
          dataKey="time"
          type="number"
          scale="time"
          domain={["dataMin", "dataMax"]}
          tick={{ fill: "#6b7280", fontSize: 10 }}
          tickLine={false}
          axisLine={false}
          tickFormatter={(v) => new Date(v).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
          tickCount={6}
        />
        <YAxis
          tick={{ fill: "#6b7280", fontSize: 10 }}
          tickLine={false}
          axisLine={false}
          tickFormatter={(v) => `$${(v / 1000).toFixed(1)}k`}
          domain={[yMin, yMax]}
          width={52}
        />
        <Tooltip
          contentStyle={{ background: "#1a1d27", border: "1px solid #2a2d3a", borderRadius: 8, fontSize: 11 }}
          labelFormatter={(v) => new Date(v as number).toLocaleTimeString()}
          formatter={(v: number, name: string) => [
            `$${v.toLocaleString("en", { minimumFractionDigits: 2 })}`,
            name === "close" ? "BTC/USD" : name === "buy" ? "BUY" : "SELL",
          ]}
        />
        {openTrades.map((t, i) => (
          <ReferenceLine
            key={i}
            y={Number(t.entry_price)}
            stroke="#4ade80"
            strokeDasharray="4 4"
            strokeOpacity={0.6}
            label={{ value: `open $${Number(t.entry_price).toFixed(0)}`, fill: "#4ade80", fontSize: 9, position: "insideTopLeft" }}
          />
        ))}
        <Line type="monotone" dataKey="close" stroke="#6366f1" strokeWidth={1.5} dot={false} activeDot={{ r: 3 }} />
        <Line type="monotone" dataKey="buy" stroke="transparent" dot={<BuyDot />} activeDot={false} legendType="none" connectNulls={false} />
        <Line type="monotone" dataKey="sell" stroke="transparent" dot={<SellDot />} activeDot={false} legendType="none" connectNulls={false} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
