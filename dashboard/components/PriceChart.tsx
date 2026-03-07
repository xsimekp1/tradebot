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

type DiagonalLine = {
  startTime: number;
  startPrice: number;
  endTime: number;
  endPrice: number;
  slope: number;  // Price change per ms
  points: number; // Number of points on line
  type: "support" | "resistance";
};

// Find diagonal trend lines connecting 3+ pivot points
function findDiagonalLines(
  data: { time: number; close: number }[],
  lookback: number = 5,  // Larger window for more significant pivots
  tolerance: number = 0.004 // 0.4% tolerance
): DiagonalLine[] {
  if (data.length < 15) return [];

  // Find local maxima and minima with significance filter
  const maxima: { time: number; price: number; idx: number }[] = [];
  const minima: { time: number; price: number; idx: number }[] = [];

  for (let i = lookback; i < data.length - lookback; i++) {
    const window = data.slice(i - lookback, i + lookback + 1).map((d) => d.close);
    const current = data[i].close;
    const min = Math.min(...window);
    const max = Math.max(...window);

    if (current === max) {
      // Avoid adding pivot too close to previous one
      const lastMax = maxima[maxima.length - 1];
      if (!lastMax || i - lastMax.idx >= 3) {
        maxima.push({ time: data[i].time, price: current, idx: i });
      }
    }
    if (current === min) {
      const lastMin = minima[minima.length - 1];
      if (!lastMin || i - lastMin.idx >= 3) {
        minima.push({ time: data[i].time, price: current, idx: i });
      }
    }
  }

  const lines: DiagonalLine[] = [];

  // Find uptrend support lines (connecting rising minima)
  const supportLines = findTrendLinesThrough(minima, data, tolerance, "support", "up");
  lines.push(...supportLines);

  // Find downtrend resistance lines (connecting falling maxima)
  const resistanceLines = findTrendLinesThrough(maxima, data, tolerance, "resistance", "down");
  lines.push(...resistanceLines);

  // Sort by points and recency, return top 3
  const currentTime = data[data.length - 1].time;
  return lines
    .filter((l) => l.points >= 3)
    .sort((a, b) => {
      // Prefer more points and more recent lines
      const scoreA = a.points + (a.endTime - a.startTime) / (currentTime - data[0].time);
      const scoreB = b.points + (b.endTime - b.startTime) / (currentTime - data[0].time);
      return scoreB - scoreA;
    })
    .slice(0, 3);
}

function findTrendLinesThrough(
  pivots: { time: number; price: number; idx: number }[],
  data: { time: number; close: number }[],
  tolerance: number,
  type: "support" | "resistance",
  direction: "up" | "down"
): DiagonalLine[] {
  const lines: DiagonalLine[] = [];
  if (pivots.length < 2) return lines;

  // Try each pair of pivots
  for (let i = 0; i < pivots.length - 1; i++) {
    for (let j = i + 1; j < pivots.length; j++) {
      const p1 = pivots[i];
      const p2 = pivots[j];

      // Calculate slope
      const slope = (p2.price - p1.price) / (p2.time - p1.time);

      // Filter by direction: support lines should go up, resistance should go down
      if (direction === "up" && slope <= 0) continue;
      if (direction === "down" && slope >= 0) continue;

      // Count points on line
      let pointsOnLine = 2;
      let lastPointTime = p2.time;

      for (let k = 0; k < pivots.length; k++) {
        if (k === i || k === j) continue;
        const p = pivots[k];
        const expectedPrice = p1.price + slope * (p.time - p1.time);
        const diff = Math.abs(p.price - expectedPrice) / p.price;
        if (diff < tolerance) {
          pointsOnLine++;
          if (p.time > lastPointTime) lastPointTime = p.time;
        }
      }

      if (pointsOnLine >= 3) {
        // Extend line to current time
        const lastTime = data[data.length - 1].time;
        const endPrice = p1.price + slope * (lastTime - p1.time);

        lines.push({
          startTime: p1.time,
          startPrice: p1.price,
          endTime: lastTime,
          endPrice: endPrice,
          slope,
          points: pointsOnLine,
          type,
        });
      }
    }
  }

  // Remove duplicates
  const unique: DiagonalLine[] = [];
  for (const line of lines) {
    const isDuplicate = unique.some(
      (u) => Math.abs(u.slope - line.slope) / Math.abs(u.slope || 0.0001) < 0.15 &&
             Math.abs(u.startPrice - line.startPrice) / u.startPrice < 0.008
    );
    if (!isDuplicate) unique.push(line);
  }

  return unique;
}

export function PriceChart({ prices, trades }: Props) {
  const { diagonalLines, nearbyDiagonals, yMin, yMax } = useMemo(() => {
    if (!prices || prices.length === 0) {
      return { diagonalLines: [], nearbyDiagonals: [], yMin: 0, yMax: 0 };
    }

    const closes = prices.map((p) => p.close);
    const diagonalLines = findDiagonalLines(prices);
    const currentPrice = closes[closes.length - 1];
    const currentTime = prices[prices.length - 1].time;

    // Find diagonal lines near current price
    const nearbyDiagonals = diagonalLines
      .map((line) => {
        const linePrice = line.startPrice + line.slope * (currentTime - line.startTime);
        const dist = Math.abs(currentPrice - linePrice);
        const distancePct = (dist / currentPrice) * 100;
        const position = currentPrice > linePrice ? "above" : "below";
        return { line, linePrice, distance: dist, distancePct, position };
      })
      .filter((l) => l.distancePct < 3)
      .sort((a, b) => a.distance - b.distance);

    return {
      diagonalLines,
      nearbyDiagonals,
      yMin: Math.min(...closes) * 0.999,
      yMax: Math.max(...closes) * 1.001,
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

  // Build data with diagonal line values
  const data = prices.map((p) => {
    const row: Record<string, number | null> = { time: p.time, close: p.close };
    // Add diagonal line values at each time point
    diagonalLines.forEach((line, i) => {
      if (p.time >= line.startTime) {
        row[`diag${i}`] = line.startPrice + line.slope * (p.time - line.startTime);
      } else {
        row[`diag${i}`] = null;
      }
    });
    return row;
  });

  return (
    <div>
      {/* Nearby diagonal lines indicator */}
      {nearbyDiagonals.length > 0 && (
        <div className="text-xs mb-2 px-1 space-y-1">
          <div className="text-gray-500 text-[10px] uppercase tracking-wide">Trend Lines</div>
          <div className="flex flex-wrap gap-2">
            {nearbyDiagonals.map((nd, i) => {
              const isSupport = nd.line.type === "support";
              const bgColor = isSupport ? "bg-emerald-500/15 border-emerald-500/40" : "bg-rose-500/15 border-rose-500/40";
              const textColor = isSupport ? "text-emerald-400" : "text-rose-400";
              const icon = isSupport ? "↗" : "↘";
              const isClose = nd.distancePct < 0.5;
              return (
                <div
                  key={`d-${i}`}
                  className={`flex items-center gap-1.5 px-2 py-1 rounded border ${bgColor} ${isClose ? "ring-1 ring-yellow-500/50" : ""}`}
                >
                  <span className={`${textColor} font-bold`}>{icon}</span>
                  <span className={textColor}>{isSupport ? "Support" : "Resistance"}</span>
                  <span className="text-gray-500">|</span>
                  <span className={textColor}>${(nd.linePrice / 1000).toFixed(2)}k</span>
                  <span className="text-gray-500">|</span>
                  <span className={isClose ? "text-yellow-400" : "text-gray-400"}>
                    {nd.distancePct.toFixed(2)}% {nd.position}
                  </span>
                  <span className="text-gray-600 text-[10px]">
                    ({nd.line.points} touches)
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}
      <ResponsiveContainer width="100%" height={312}>
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
        {/* Diagonal trend lines with distinct styles */}
        {diagonalLines.map((line, i) => {
          const isSupport = line.type === "support";
          return (
            <Line
              key={`diag-${i}`}
              type="linear"
              dataKey={`diag${i}`}
              stroke={isSupport ? "#10b981" : "#f43f5e"}
              strokeWidth={1.5 + line.points * 0.3}
              strokeDasharray={isSupport ? "12 4" : "4 4"}
              strokeOpacity={0.8}
              dot={false}
              connectNulls={false}
            />
          );
        })}
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
      </ComposedChart>
    </ResponsiveContainer>
    </div>
  );
}
