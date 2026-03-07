"use client";

import { useMemo } from "react";
import {
  ComposedChart, Line, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, ReferenceLine, ReferenceDot,
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

function BuyShape({ cx = 0, cy = 0 }: { cx?: number; cy?: number }) {
  return <polygon points={`${cx},${cy - 10} ${cx - 7},${cy + 5} ${cx + 7},${cy + 5}`} fill="#4ade80" opacity={0.95} />;
}

function SellShape({ cx = 0, cy = 0 }: { cx?: number; cy?: number }) {
  return <polygon points={`${cx},${cy + 10} ${cx - 7},${cy - 5} ${cx + 7},${cy - 5}`} fill="#f87171" opacity={0.95} />;
}

type TrendLine = {
  level: number;
  strength: number;  // Number of touches (1-5+)
  type: "support" | "resistance";
};

// Find support/resistance levels with strength (number of touches)
function findTrendLines(closes: number[], tolerance: number = 0.002): TrendLine[] {
  const levels: { price: number; type: "support" | "resistance"; touches: number }[] = [];
  const lookback = 5;

  // Find pivot points
  for (let i = lookback; i < closes.length - lookback; i++) {
    const window = closes.slice(i - lookback, i + lookback + 1);
    const current = closes[i];
    const min = Math.min(...window);
    const max = Math.max(...window);

    if (current === min) {
      // Check if near existing support level
      const existing = levels.find((l) => l.type === "support" && Math.abs(l.price - current) / current < tolerance);
      if (existing) {
        existing.touches++;
        existing.price = (existing.price + current) / 2; // Average the level
      } else {
        levels.push({ price: current, type: "support", touches: 1 });
      }
    }
    if (current === max) {
      const existing = levels.find((l) => l.type === "resistance" && Math.abs(l.price - current) / current < tolerance);
      if (existing) {
        existing.touches++;
        existing.price = (existing.price + current) / 2;
      } else {
        levels.push({ price: current, type: "resistance", touches: 1 });
      }
    }
  }

  // Count additional touches (price came close to level)
  for (const level of levels) {
    for (const close of closes) {
      if (Math.abs(close - level.price) / level.price < tolerance * 0.5) {
        level.touches++;
      }
    }
    level.touches = Math.min(level.touches, 10); // Cap at 10
  }

  // Sort by strength and return top levels
  return levels
    .filter((l) => l.touches >= 2) // Only levels with 2+ touches
    .sort((a, b) => b.touches - a.touches)
    .slice(0, 6) // Max 6 lines total
    .map((l) => ({
      level: l.price,
      strength: Math.min(l.touches, 5), // Strength 1-5
      type: l.type,
    }));
}

export function PriceChart({ prices, trades }: Props) {
  const { trendLines, currentPrice, nearbyLines, yMin, yMax } = useMemo(() => {
    if (!prices || prices.length === 0) {
      return { trendLines: [], currentPrice: 0, nearbyLines: [], yMin: 0, yMax: 0 };
    }

    const closes = prices.map((p) => p.close);
    const trendLines = findTrendLines(closes);
    const currentPrice = closes[closes.length - 1];

    // Find all lines within 1% of current price
    const nearbyLines = trendLines
      .map((line) => {
        const dist = Math.abs(currentPrice - line.level);
        const distPct = (dist / currentPrice) * 100;
        const position = currentPrice > line.level ? "above" : currentPrice < line.level ? "below" : "at";
        return { line, distance: dist, distancePct, position };
      })
      .filter((l) => l.distancePct < 1.5) // Only lines within 1.5%
      .sort((a, b) => a.distance - b.distance);

    return {
      trendLines,
      currentPrice,
      nearbyLines,
      yMin: Math.min(...closes) * 0.9994,
      yMax: Math.max(...closes) * 1.0006,
    };
  }, [prices]);

  if (!prices || prices.length === 0) {
    return (
      <div className="h-64 flex items-center justify-center text-gray-600 text-sm">
        Loading price data...
      </div>
    );
  }

  const openTrades = trades.filter((t) => !t.closed_at && Number(t.entry_price) > 0);

  // Snap a timestamp to nearest candle and return { time, price=close }
  const snapClose = (ms: number) =>
    prices.reduce((a, b) => (Math.abs(b.time - ms) < Math.abs(a.time - ms) ? b : a));

  // Collect buy/sell markers snapped to nearest candle close
  const buyMarkers: { time: number; price: number }[] = [];
  const sellMarkers: { time: number; price: number }[] = [];

  trades.forEach((t) => {
    if (Number(t.entry_price) > 0) {
      const c = snapClose(new Date(t.opened_at).getTime());
      buyMarkers.push({ time: c.time, price: c.close });
    }
    if (t.closed_at && t.exit_price && Number(t.exit_price) > 0) {
      const c = snapClose(new Date(t.closed_at).getTime());
      sellMarkers.push({ time: c.time, price: c.close });
    }
  });

  const data = prices.map((p) => ({ time: p.time, close: p.close }));

  return (
    <div>
      {/* Nearby lines indicator */}
      {nearbyLines.length > 0 && (
        <div className="text-xs mb-2 px-1 space-y-1">
          <div className="text-gray-500 text-[10px] uppercase tracking-wide">Nearby levels (within 1.5%)</div>
          <div className="flex flex-wrap gap-2">
            {nearbyLines.map((nl, i) => {
              const isAbove = nl.position === "above";
              const isBelow = nl.position === "below";
              const bgColor = isBelow ? "bg-green-500/10 border-green-500/30" : "bg-red-500/10 border-red-500/30";
              const textColor = isBelow ? "text-green-400" : "text-red-400";
              const arrow = isBelow ? "↓" : "↑";
              const isClose = nl.distancePct < 0.3;
              return (
                <div
                  key={i}
                  className={`flex items-center gap-1.5 px-2 py-1 rounded border ${bgColor} ${isClose ? "ring-1 ring-yellow-500/50" : ""}`}
                >
                  <span className={textColor}>{arrow}</span>
                  <span className={textColor}>${(nl.line.level / 1000).toFixed(2)}k</span>
                  <span className="text-gray-500">|</span>
                  <span className={isClose ? "text-yellow-400" : "text-gray-400"}>
                    {nl.distancePct.toFixed(2)}%
                  </span>
                  <span className="text-gray-600 text-[10px]">
                    ({nl.line.strength}/5)
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}
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
          formatter={(v: number) => [`$${v.toLocaleString("en", { minimumFractionDigits: 2 })}`, "BTC/USD"]}
        />
        <Line type="monotone" dataKey="close" stroke="#6366f1" strokeWidth={1.5} dot={false} activeDot={{ r: 3 }} />
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
        {buyMarkers.map((b, i) => (
          <ReferenceDot key={`buy-${i}`} x={b.time} y={b.price} r={0} shape={<BuyShape />} />
        ))}
        {sellMarkers.map((s, i) => (
          <ReferenceDot key={`sell-${i}`} x={s.time} y={s.price} r={0} shape={<SellShape />} />
        ))}
        {/* Support/Resistance lines with strength */}
        {trendLines.map((line, i) => {
          const isSupport = line.type === "support";
          const color = isSupport ? "#22c55e" : "#ef4444";
          const opacity = 0.3 + line.strength * 0.14; // 0.44 to 1.0 based on strength
          const strokeWidth = 1 + line.strength * 0.3; // 1.3 to 2.5
          const label = `${isSupport ? "S" : "R"} $${(line.level / 1000).toFixed(1)}k (${line.strength})`;
          return (
            <ReferenceLine
              key={`trend-${i}`}
              y={line.level}
              stroke={color}
              strokeDasharray="6 3"
              strokeOpacity={opacity}
              strokeWidth={strokeWidth}
              label={{
                value: label,
                fill: color,
                fontSize: 9,
                position: isSupport ? "insideBottomLeft" : "insideTopLeft",
              }}
            />
          );
        })}
      </ComposedChart>
    </ResponsiveContainer>
    </div>
  );
}
