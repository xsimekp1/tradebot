"use client";

import {
  ComposedChart, Line, XAxis, YAxis, Tooltip,
  ResponsiveContainer, ReferenceDot, CartesianGrid,
} from "recharts";

type EquityPoint = { ts: string; eq: number };
type TradeEvent = { type: "buy" | "sell"; price: number; ts: string; pnl?: number };

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
  };
  version: number;
};

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

  // Map trade timestamps to equity curve indices
  const tsToEq = new Map(equityCurve.map(p => [p.ts.slice(0, 16), p.eq]));
  const tradeMarkers = trades
    .map(t => {
      const key = t.ts.slice(0, 16);
      const eq = tsToEq.get(key);
      if (eq === undefined) return null;
      return { ...t, eq };
    })
    .filter(Boolean) as (TradeEvent & { eq: number })[];

  return (
    <div className="bg-[#1a1d27] rounded-xl border border-[#2a2d3a] p-4">
      <div className="flex items-start justify-between mb-3">
        <div>
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide">
            Best Backtest — OOS (v{version})
          </h2>
          <p className="text-xs text-gray-600 mt-0.5">7-day out-of-sample simulation · ▲ buy &nbsp; ▼ sell</p>
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
        </div>
      </div>

      <ResponsiveContainer width="100%" height={200}>
        <ComposedChart data={equityCurve} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
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
          {tradeMarkers.map((t, i) =>
            t.type === "buy" ? (
              <ReferenceDot key={`b${i}`} x={t.ts} y={t.eq} r={0} shape={<BuyShape />} />
            ) : (
              <ReferenceDot key={`s${i}`} x={t.ts} y={t.eq} r={0} shape={<SellShape />} />
            )
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
