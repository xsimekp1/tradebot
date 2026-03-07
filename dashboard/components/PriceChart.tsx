"use client";

import { useMemo } from "react";
import {
  ComposedChart, Line, Area, XAxis, YAxis, Tooltip,
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

// Result of optimized resistance line search
type ResistanceLine = {
  slope: number;           // Price change per millisecond
  intercept: number;       // Price at t=0 (reference time)
  refTime: number;         // Reference time (start of data)
  score: number;           // Lower is better
  breakthroughs: number[]; // Indices of points that broke through
  avgDistance: number;     // Average distance from line to price
};

/**
 * Find optimal resistance line above price data.
 * Uses grid search with 20x penalty for breakthroughs.
 */
function findOptimalResistanceLine(
  data: { time: number; close: number }[]
): ResistanceLine | null {
  if (data.length < 10) return null;

  let maxIdx = 0;
  let maxPrice = data[0].close;
  for (let i = 1; i < data.length; i++) {
    if (data[i].close > maxPrice) {
      maxPrice = data[i].close;
      maxIdx = i;
    }
  }

  const maxPoint = data[maxIdx];
  const refTime = data[0].time;
  const timeRange = data[data.length - 1].time - refTime;
  const priceRange = maxPrice - Math.min(...data.map(d => d.close));

  function evaluateLine(slope: number, intercept: number): { score: number; breakthroughs: number[]; avgDist: number } {
    let score = 0;
    let totalDist = 0;
    const breakthroughs: number[] = [];

    for (let i = 0; i < data.length; i++) {
      const p = data[i];
      const linePrice = intercept + slope * (p.time - refTime);
      const d = linePrice - p.close;

      if (d >= 0) {
        score += d;
        totalDist += d;
      } else {
        score += Math.abs(d) * 20;
        totalDist += Math.abs(d);
        breakthroughs.push(i);
      }
    }

    return { score, breakthroughs, avgDist: totalDist / data.length };
  }

  const slopeStep = (priceRange / timeRange) * 0.05;
  const slopeMin = -priceRange / timeRange * 0.5;
  const slopeMax = priceRange / timeRange * 0.5;
  const offsetStep = priceRange * 0.01;
  const offsetMin = -priceRange * 0.1;
  const offsetMax = priceRange * 0.2;

  let bestResult: ResistanceLine = {
    slope: 0,
    intercept: maxPrice,
    refTime,
    score: Infinity,
    breakthroughs: [],
    avgDistance: 0,
  };

  for (let slope = slopeMin; slope <= slopeMax; slope += slopeStep) {
    const baseInt = maxPrice - slope * (maxPoint.time - refTime);

    for (let offset = offsetMin; offset <= offsetMax; offset += offsetStep) {
      const intercept = baseInt + offset;
      const { score, breakthroughs, avgDist } = evaluateLine(slope, intercept);

      if (score < bestResult.score) {
        bestResult = { slope, intercept, refTime, score, breakthroughs, avgDistance: avgDist };
      }
    }
  }

  const fineSlope = slopeStep * 0.2;
  const fineOffset = offsetStep * 0.2;

  for (let ds = -slopeStep; ds <= slopeStep; ds += fineSlope) {
    for (let doff = -offsetStep * 2; doff <= offsetStep * 2; doff += fineOffset) {
      const slope = bestResult.slope + ds;
      const intercept = bestResult.intercept + doff;
      const { score, breakthroughs, avgDist } = evaluateLine(slope, intercept);

      if (score < bestResult.score) {
        bestResult = { slope, intercept, refTime, score, breakthroughs, avgDistance: avgDist };
      }
    }
  }

  return bestResult;
}

/**
 * Find optimal support line below price data.
 * Mirror of resistance line with 20x penalty for breakthroughs.
 */
function findOptimalSupportLine(
  data: { time: number; close: number }[]
): ResistanceLine | null {
  if (data.length < 10) return null;

  let minIdx = 0;
  let minPrice = data[0].close;
  for (let i = 1; i < data.length; i++) {
    if (data[i].close < minPrice) {
      minPrice = data[i].close;
      minIdx = i;
    }
  }

  const minPoint = data[minIdx];
  const refTime = data[0].time;
  const timeRange = data[data.length - 1].time - refTime;
  const priceRange = Math.max(...data.map(d => d.close)) - minPrice;

  function evaluateLine(slope: number, intercept: number): { score: number; breakthroughs: number[]; avgDist: number } {
    let score = 0;
    let totalDist = 0;
    const breakthroughs: number[] = [];

    for (let i = 0; i < data.length; i++) {
      const p = data[i];
      const linePrice = intercept + slope * (p.time - refTime);
      const d = p.close - linePrice;

      if (d >= 0) {
        score += d;
        totalDist += d;
      } else {
        score += Math.abs(d) * 20;
        totalDist += Math.abs(d);
        breakthroughs.push(i);
      }
    }

    return { score, breakthroughs, avgDist: totalDist / data.length };
  }

  const slopeStep = (priceRange / timeRange) * 0.05;
  const slopeMin = -priceRange / timeRange * 0.5;
  const slopeMax = priceRange / timeRange * 0.5;
  const offsetStep = priceRange * 0.01;
  const offsetMin = -priceRange * 0.2;
  const offsetMax = priceRange * 0.1;

  let bestResult: ResistanceLine = {
    slope: 0,
    intercept: minPrice,
    refTime,
    score: Infinity,
    breakthroughs: [],
    avgDistance: 0,
  };

  for (let slope = slopeMin; slope <= slopeMax; slope += slopeStep) {
    const baseInt = minPrice - slope * (minPoint.time - refTime);

    for (let offset = offsetMin; offset <= offsetMax; offset += offsetStep) {
      const intercept = baseInt + offset;
      const { score, breakthroughs, avgDist } = evaluateLine(slope, intercept);

      if (score < bestResult.score) {
        bestResult = { slope, intercept, refTime, score, breakthroughs, avgDistance: avgDist };
      }
    }
  }

  const fineSlope = slopeStep * 0.2;
  const fineOffset = offsetStep * 0.2;

  for (let ds = -slopeStep; ds <= slopeStep; ds += fineSlope) {
    for (let doff = -offsetStep * 2; doff <= offsetStep * 2; doff += fineOffset) {
      const slope = bestResult.slope + ds;
      const intercept = bestResult.intercept + doff;
      const { score, breakthroughs, avgDist } = evaluateLine(slope, intercept);

      if (score < bestResult.score) {
        bestResult = { slope, intercept, refTime, score, breakthroughs, avgDistance: avgDist };
      }
    }
  }

  return bestResult;
}

export function PriceChart({ prices, trades }: Props) {
  const { resistanceLine, supportLine, yMin, yMax } = useMemo(() => {
    if (!prices || prices.length === 0) {
      return { resistanceLine: null, supportLine: null, yMin: 0, yMax: 0 };
    }

    const closes = prices.map((p) => p.close);
    const resistanceLine = findOptimalResistanceLine(prices);
    const supportLine = findOptimalSupportLine(prices);

    let yMinBase = Math.min(...closes);
    let yMaxBase = Math.max(...closes);

    if (resistanceLine) {
      const endPrice = resistanceLine.intercept + resistanceLine.slope * (prices[prices.length - 1].time - resistanceLine.refTime);
      const startPrice = resistanceLine.intercept;
      yMaxBase = Math.max(yMaxBase, startPrice, endPrice);
    }
    if (supportLine) {
      const endPrice = supportLine.intercept + supportLine.slope * (prices[prices.length - 1].time - supportLine.refTime);
      const startPrice = supportLine.intercept;
      yMinBase = Math.min(yMinBase, startPrice, endPrice);
    }

    return {
      resistanceLine,
      supportLine,
      yMin: yMinBase * 0.9995,
      yMax: yMaxBase * 1.0005,
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

  const snapClose = (ms: number) =>
    prices.reduce((a, b) => (Math.abs(b.time - ms) < Math.abs(a.time - ms) ? b : a));

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

  // Calculate gradient zone thickness (avgDistance / 5)
  const resistanceGradientHeight = resistanceLine ? resistanceLine.avgDistance / 5 : 0;
  const supportGradientHeight = supportLine ? supportLine.avgDistance / 5 : 0;

  // Build data with line values and gradient zones
  const data = prices.map((p) => {
    const row: Record<string, number | null> = { time: p.time, close: p.close };
    if (resistanceLine) {
      const linePrice = resistanceLine.intercept + resistanceLine.slope * (p.time - resistanceLine.refTime);
      row.resistance = linePrice;
      row.resistanceGradientTop = linePrice;
      row.resistanceGradientBottom = linePrice - resistanceGradientHeight;
    }
    if (supportLine) {
      const linePrice = supportLine.intercept + supportLine.slope * (p.time - supportLine.refTime);
      row.support = linePrice;
      row.supportGradientBottom = linePrice;
      row.supportGradientTop = linePrice + supportGradientHeight;
    }
    return row;
  });

  // Current distance to lines
  const currentPrice = prices[prices.length - 1].close;
  const currentTime = prices[prices.length - 1].time;

  let resistanceInfo: { price: number; distPct: number } | null = null;
  if (resistanceLine) {
    const linePrice = resistanceLine.intercept + resistanceLine.slope * (currentTime - resistanceLine.refTime);
    resistanceInfo = {
      price: linePrice,
      distPct: ((linePrice - currentPrice) / currentPrice) * 100,
    };
  }

  let supportInfo: { price: number; distPct: number } | null = null;
  if (supportLine) {
    const linePrice = supportLine.intercept + supportLine.slope * (currentTime - supportLine.refTime);
    supportInfo = {
      price: linePrice,
      distPct: ((currentPrice - linePrice) / currentPrice) * 100,
    };
  }

  return (
    <div>
      {/* Line info indicators */}
      {(resistanceInfo || supportInfo) && (
        <div className="text-xs mb-2 px-1 space-y-1">
          <div className="text-gray-500 text-[10px] uppercase tracking-wide">Optimized Trend Lines</div>
          <div className="flex flex-wrap gap-2">
            {resistanceInfo && (
              <div className={`flex items-center gap-1.5 px-2 py-1 rounded border bg-rose-500/15 border-rose-500/40 ${resistanceInfo.distPct < 0.3 ? "ring-1 ring-yellow-500/50" : ""}`}>
                <span className="text-rose-400 font-bold">↘</span>
                <span className="text-rose-400">Resistance</span>
                <span className="text-gray-500">|</span>
                <span className="text-rose-400">${(resistanceInfo.price / 1000).toFixed(2)}k</span>
                <span className="text-gray-500">|</span>
                <span className={resistanceInfo.distPct < 0.3 ? "text-yellow-400" : "text-gray-400"}>
                  {resistanceInfo.distPct >= 0 ? "+" : ""}{resistanceInfo.distPct.toFixed(2)}% {resistanceInfo.distPct >= 0 ? "above" : "BREACH"}
                </span>
                {resistanceLine && resistanceLine.breakthroughs.length > 0 && (
                  <span className="text-orange-500 text-[10px]">
                    ({resistanceLine.breakthroughs.length} breaks)
                  </span>
                )}
              </div>
            )}
            {supportInfo && (
              <div className={`flex items-center gap-1.5 px-2 py-1 rounded border bg-emerald-500/15 border-emerald-500/40 ${supportInfo.distPct < 0.3 ? "ring-1 ring-yellow-500/50" : ""}`}>
                <span className="text-emerald-400 font-bold">↗</span>
                <span className="text-emerald-400">Support</span>
                <span className="text-gray-500">|</span>
                <span className="text-emerald-400">${(supportInfo.price / 1000).toFixed(2)}k</span>
                <span className="text-gray-500">|</span>
                <span className={supportInfo.distPct < 0.3 ? "text-yellow-400" : "text-gray-400"}>
                  {supportInfo.distPct >= 0 ? "+" : ""}{supportInfo.distPct.toFixed(2)}% {supportInfo.distPct >= 0 ? "above" : "BREACH"}
                </span>
                {supportLine && supportLine.breakthroughs.length > 0 && (
                  <span className="text-orange-500 text-[10px]">
                    ({supportLine.breakthroughs.length} breaks)
                  </span>
                )}
              </div>
            )}
          </div>
        </div>
      )}
      <ResponsiveContainer width="100%" height={312}>
        <ComposedChart data={data} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="resistanceGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#f43f5e" stopOpacity={0.4} />
              <stop offset="100%" stopColor="#f43f5e" stopOpacity={0.05} />
            </linearGradient>
            <linearGradient id="supportGradient" x1="0" y1="1" x2="0" y2="0">
              <stop offset="0%" stopColor="#10b981" stopOpacity={0.4} />
              <stop offset="100%" stopColor="#10b981" stopOpacity={0.05} />
            </linearGradient>
          </defs>
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
            formatter={(v: number, name: string) => {
              if (name.includes("Gradient")) return null;
              const label = name === "close" ? "BTC/USD" : name === "resistance" ? "Resistance" : "Support";
              return [`$${v.toLocaleString("en", { minimumFractionDigits: 2 })}`, label];
            }}
          />
          {/* Resistance gradient zone (below line) */}
          {resistanceLine && (
            <Area
              type="linear"
              dataKey="resistanceGradientTop"
              stroke="none"
              fill="url(#resistanceGradient)"
              fillOpacity={1}
              baseLine={data.map(d => d.resistanceGradientBottom as number)}
              isAnimationActive={false}
            />
          )}
          {/* Support gradient zone (above line) */}
          {supportLine && (
            <Area
              type="linear"
              dataKey="supportGradientTop"
              stroke="none"
              fill="url(#supportGradient)"
              fillOpacity={1}
              baseLine={data.map(d => d.supportGradientBottom as number)}
              isAnimationActive={false}
            />
          )}
          <Line type="monotone" dataKey="close" stroke="#6366f1" strokeWidth={1.5} dot={false} activeDot={{ r: 3 }} />
          {/* Resistance line */}
          {resistanceLine && (
            <Line
              type="linear"
              dataKey="resistance"
              stroke="#f43f5e"
              strokeWidth={2}
              strokeOpacity={0.9}
              dot={false}
              connectNulls={true}
            />
          )}
          {/* Support line */}
          {supportLine && (
            <Line
              type="linear"
              dataKey="support"
              stroke="#10b981"
              strokeWidth={2}
              strokeOpacity={0.9}
              dot={false}
              connectNulls={true}
            />
          )}
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
