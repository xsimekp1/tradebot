"use client";

import {
  ComposedChart, Line, XAxis, YAxis, Tooltip,
  ResponsiveContainer, ReferenceDot, CartesianGrid,
} from "recharts";

type EquityPoint = { ts: string; eq: number; pos?: number };  // pos: 0=flat, 1=long, -1=short
type TradeEvent = {
  action?: "open" | "close";
  side?: "long" | "short";
  close_reason?: "signal" | "stop_loss";
  type?: "buy" | "sell";  // Legacy format
  price: number;
  ts: string;
  pnl?: number;
};

type Props = {
  equityCurve: EquityPoint[];
  trades: TradeEvent[];
  stats: {
    return_pct: number;
    sharpe: number;
    num_trades: number;
    win_rate: number;
    max_dd: number;
    buyhold_return?: number;
    beats_buyhold?: boolean;
    time_long_pct?: number;
    time_short_pct?: number;
    time_flat_pct?: number;
  };
  version: number;
};

// Open Long - green up triangle
function OpenLongShape({ cx = 0, cy = 0 }: { cx?: number; cy?: number }) {
  return <polygon points={`${cx},${cy - 8} ${cx - 5},${cy + 4} ${cx + 5},${cy + 4}`} fill="#4ade80" opacity={0.9} />;
}

// Close Long by Signal - green down triangle
function CloseLongSignalShape({ cx = 0, cy = 0 }: { cx?: number; cy?: number }) {
  return <polygon points={`${cx},${cy + 8} ${cx - 5},${cy - 4} ${cx + 5},${cy - 4}`} fill="#4ade80" opacity={0.9} />;
}

// Close Long by Stop Loss - red X
function CloseStopLossShape({ cx = 0, cy = 0 }: { cx?: number; cy?: number }) {
  return (
    <g>
      <line x1={cx - 5} y1={cy - 5} x2={cx + 5} y2={cy + 5} stroke="#f87171" strokeWidth={2} />
      <line x1={cx + 5} y1={cy - 5} x2={cx - 5} y2={cy + 5} stroke="#f87171" strokeWidth={2} />
    </g>
  );
}

// Open Short - red down triangle
function OpenShortShape({ cx = 0, cy = 0 }: { cx?: number; cy?: number }) {
  return <polygon points={`${cx},${cy + 8} ${cx - 5},${cy - 4} ${cx + 5},${cy - 4}`} fill="#f87171" opacity={0.9} />;
}

// Close Short by Signal - red up triangle
function CloseShortSignalShape({ cx = 0, cy = 0 }: { cx?: number; cy?: number }) {
  return <polygon points={`${cx},${cy - 8} ${cx - 5},${cy + 4} ${cx + 5},${cy + 4}`} fill="#f87171" opacity={0.9} />;
}

// Legacy shapes for old format
function BuyShape({ cx = 0, cy = 0 }: { cx?: number; cy?: number }) {
  return <polygon points={`${cx},${cy - 8} ${cx - 5},${cy + 4} ${cx + 5},${cy + 4}`} fill="#4ade80" opacity={0.9} />;
}

function SellShape({ cx = 0, cy = 0 }: { cx?: number; cy?: number }) {
  return <polygon points={`${cx},${cy + 8} ${cx - 5},${cy - 4} ${cx + 5},${cy - 4}`} fill="#f87171" opacity={0.9} />;
}

export function BacktestMiniChart({ equityCurve, trades, stats, version }: Props) {
  if (!equityCurve || equityCurve.length === 0) return null;

  const capital = 10_000;
  const yMin = Math.min(...equityCurve.map(p => p.eq)) * 0.999;
  const yMax = Math.max(...equityCurve.map(p => p.eq)) * 1.001;
  const finalEq = equityCurve[equityCurve.length - 1].eq;
  const isPositive = finalEq >= capital;

  // Map trade timestamps to equity curve - find nearest point
  const eqTimes = equityCurve.map(p => new Date(p.ts).getTime());
  const tradeMarkers = trades
    .map(t => {
      const tradeTime = new Date(t.ts).getTime();
      // Find closest equity curve point
      let closestIdx = 0;
      let closestDiff = Math.abs(eqTimes[0] - tradeTime);
      for (let i = 1; i < eqTimes.length; i++) {
        const diff = Math.abs(eqTimes[i] - tradeTime);
        if (diff < closestDiff) {
          closestDiff = diff;
          closestIdx = i;
        }
      }
      // Only include if within 30 minutes of a point
      if (closestDiff > 30 * 60 * 1000) return null;
      return { ...t, ts: equityCurve[closestIdx].ts, eq: equityCurve[closestIdx].eq };
    })
    .filter(Boolean) as (TradeEvent & { eq: number })[];

  return (
    <div className="bg-[#1a1d27] rounded-xl border border-[#2a2d3a] p-4">
      <div className="flex items-start justify-between mb-3">
        <div>
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide">
            Best Backtest — OOS (v{version})
          </h2>
          <p className="text-xs text-gray-600 mt-0.5">14-day out-of-sample simulation · <span className="text-green-400">▲</span> open long &nbsp; <span className="text-red-400">▼</span> open short &nbsp; ▼ close &nbsp; ✕ stop loss</p>
        </div>
        <div className="flex gap-3 text-xs text-right">
          <div>
            <div className="text-gray-500 uppercase text-[10px]">Return</div>
            <div className={`font-bold ${isPositive ? "text-green-400" : "text-red-400"}`}>
              {stats.return_pct >= 0 ? "+" : ""}{stats.return_pct.toFixed(2)}%
            </div>
          </div>
          {stats.buyhold_return !== undefined && (
            <div>
              <div className="text-gray-500 uppercase text-[10px]">Buy&Hold</div>
              <div className={`font-bold ${stats.buyhold_return >= 0 ? "text-blue-400" : "text-blue-300"}`}>
                {stats.buyhold_return >= 0 ? "+" : ""}{stats.buyhold_return.toFixed(2)}%
              </div>
            </div>
          )}
          {stats.beats_buyhold !== undefined && (
            <div>
              <div className="text-gray-500 uppercase text-[10px]">vs Market</div>
              <div className={`font-bold ${stats.beats_buyhold ? "text-green-400" : "text-red-400"}`}>
                {stats.beats_buyhold ? "BEATING" : "LOSING"}
              </div>
            </div>
          )}
          <div>
            <div className="text-gray-500 uppercase text-[10px]">Sharpe</div>
            <div className="text-white font-bold">{stats.sharpe.toFixed(2)}</div>
          </div>
          <div>
            <div className="text-gray-500 uppercase text-[10px]">WR</div>
            <div className="text-white font-bold">{stats.win_rate.toFixed(1)}%</div>
          </div>
          <div>
            <div className="text-gray-500 uppercase text-[10px]">Trades</div>
            <div className="text-white font-bold">{stats.num_trades}</div>
          </div>
          <div>
            <div className="text-gray-500 uppercase text-[10px]">Max DD</div>
            <div className="text-red-400 font-bold">{stats.max_dd.toFixed(2)}%</div>
          </div>
          {stats.time_long_pct !== undefined && (
            <div>
              <div className="text-gray-500 uppercase text-[10px]">In Position</div>
              <div className="flex gap-1 text-[10px] font-bold">
                <span className="text-green-400">{stats.time_long_pct.toFixed(0)}%L</span>
                <span className="text-red-400">{stats.time_short_pct?.toFixed(0)}%S</span>
              </div>
            </div>
          )}
        </div>
      </div>

      <ResponsiveContainer width="100%" height={200}>
        <ComposedChart data={equityCurve} margin={{ top: 4, right: 8, left: 0, bottom: 16 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#2a2d3a" />
          <XAxis
            dataKey="ts"
            tick={{ fill: "#6b7280", fontSize: 9 }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(v) => {
              const d = new Date(v);
              return `${d.getMonth() + 1}/${d.getDate()}`;
            }}
            interval="preserveStartEnd"
            tickCount={6}
          />
          <YAxis
            tick={{ fill: "#6b7280", fontSize: 9 }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(v) => `$${v.toFixed(0)}`}
            domain={[yMin, yMax]}
            width={48}
          />
          <Tooltip
            contentStyle={{ background: "#1a1d27", border: "1px solid #2a2d3a", borderRadius: 6, fontSize: 10 }}
            labelFormatter={(v) => new Date(v as string).toLocaleString()}
            formatter={(v: number) => [`$${v.toFixed(2)}`, "Equity"]}
          />
          <Line
            type="monotone"
            dataKey="eq"
            stroke={isPositive ? "#10b981" : "#f43f5e"}
            strokeWidth={1.5}
            dot={false}
            activeDot={{ r: 2 }}
          />
          {tradeMarkers.map((t, i) => {
            // New format: action + side + close_reason
            if (t.action && t.side) {
              if (t.action === "open" && t.side === "long") {
                return <ReferenceDot key={`ol${i}`} x={t.ts} y={t.eq} r={0} shape={<OpenLongShape />} />;
              } else if (t.action === "open" && t.side === "short") {
                return <ReferenceDot key={`os${i}`} x={t.ts} y={t.eq} r={0} shape={<OpenShortShape />} />;
              } else if (t.action === "close" && t.close_reason === "stop_loss") {
                return <ReferenceDot key={`sl${i}`} x={t.ts} y={t.eq} r={0} shape={<CloseStopLossShape />} />;
              } else if (t.action === "close" && t.side === "long") {
                return <ReferenceDot key={`cl${i}`} x={t.ts} y={t.eq} r={0} shape={<CloseLongSignalShape />} />;
              } else if (t.action === "close" && t.side === "short") {
                return <ReferenceDot key={`cs${i}`} x={t.ts} y={t.eq} r={0} shape={<CloseShortSignalShape />} />;
              }
            }
            // Legacy format: type = "buy" | "sell"
            return t.type === "buy" ? (
              <ReferenceDot key={`b${i}`} x={t.ts} y={t.eq} r={0} shape={<BuyShape />} />
            ) : (
              <ReferenceDot key={`s${i}`} x={t.ts} y={t.eq} r={0} shape={<SellShape />} />
            );
          })}
        </ComposedChart>
      </ResponsiveContainer>

      {/* Position band - shows when we're long (green), short (red), or flat (gray) */}
      {equityCurve.some(p => p.pos !== undefined) && (
        <div className="mt-1 mx-12 h-2 flex rounded-sm overflow-hidden" title="Position: green=long, red=short, gray=flat">
          {equityCurve.map((p, i) => {
            const pos = p.pos ?? 0;
            const color = pos === 1 ? "#4ade80" : pos === -1 ? "#f87171" : "#374151";
            // Only render if position changed or first/last element to reduce DOM nodes
            const prevPos = i > 0 ? (equityCurve[i - 1].pos ?? 0) : null;
            if (i > 0 && i < equityCurve.length - 1 && pos === prevPos) return null;
            // Calculate width as percentage of consecutive same-position bars
            let count = 1;
            for (let j = i + 1; j < equityCurve.length && (equityCurve[j].pos ?? 0) === pos; j++) {
              count++;
            }
            const widthPct = (count / equityCurve.length) * 100;
            return (
              <div
                key={i}
                style={{ backgroundColor: color, width: `${widthPct}%` }}
                className="h-full"
              />
            );
          }).filter(Boolean)}
        </div>
      )}
    </div>
  );
}
