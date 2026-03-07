"use client";

import useSWR from "swr";
import { useState } from "react";
import { EquityChart } from "@/components/EquityChart";
import { SignalsPanel } from "@/components/SignalsPanel";
import { TradesTable } from "@/components/TradesTable";
import { WeightsBar } from "@/components/WeightsBar";
import { StatusBar } from "@/components/StatusBar";
import { WeightHistoryChart } from "@/components/WeightHistoryChart";
import { ScoreGauge } from "@/components/ScoreGauge";

const fetcher = (url: string) => fetch(url).then((r) => r.json());
const REFRESH = 30_000;

export default function Dashboard() {
  const { data: status } = useSWR("/api/status", fetcher, { refreshInterval: REFRESH });
  const { data: equity } = useSWR("/api/equity", fetcher, { refreshInterval: REFRESH });
  const { data: signals } = useSWR("/api/signals", fetcher, { refreshInterval: REFRESH });
  const { data: trades } = useSWR("/api/trades", fetcher, { refreshInterval: REFRESH });
  const { data: weights } = useSWR("/api/weights", fetcher, { refreshInterval: REFRESH });

  const activeWeights = Array.isArray(weights) ? weights.find((w: { is_active: boolean }) => w.is_active) : null;
  const [showHistory, setShowHistory] = useState(false);

  return (
    <div className="min-h-screen bg-[#0f1117] text-gray-100 p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white tracking-tight">TradeBot</h1>
          <p className="text-xs text-gray-500">BTC/USD · Paper Trading · Refreshes every 30s</p>
        </div>
        <div className="flex items-center gap-3">
          <a href="/research" className="text-xs text-indigo-400 hover:text-indigo-300 border border-indigo-500/30 px-3 py-1.5 rounded-lg">
            Research Lab
          </a>
          <StatusBar status={status} />
        </div>
      </div>

      {/* Stat cards row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard
          label="Equity"
          value={status?.equity != null ? `$${Number(status.equity).toLocaleString("en", { minimumFractionDigits: 2 })}` : "—"}
          sub={status?.equityTimestamp ? new Date(status.equityTimestamp).toLocaleTimeString() : ""}
        />
        <StatCard
          label="Daily P&L"
          value={status?.dailyPnl != null ? `$${Number(status.dailyPnl) >= 0 ? "+" : ""}${Number(status.dailyPnl).toFixed(2)}` : "—"}
          positive={Number(status?.dailyPnl ?? 0) >= 0}
          sub="vs yesterday close"
        />
        <StatCard
          label="Total Trades"
          value={status?.totalTrades ?? "—"}
          sub={status?.totalTrades > 0 ? `${status.winners} winners · ${(status.winners / status.totalTrades * 100).toFixed(0)}% WR` : "no closed trades"}
        />
        <StatCard
          label="Total P&L"
          value={status?.totalPnl != null ? `$${Number(status.totalPnl) >= 0 ? "+" : ""}${Number(status.totalPnl).toFixed(2)}` : "—"}
          positive={Number(status?.totalPnl ?? 0) >= 0}
          sub="all closed trades"
        />
      </div>

      {/* Equity chart + Score + Weights */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 bg-[#1a1d27] rounded-xl border border-[#2a2d3a] p-4">
          <h2 className="text-sm font-semibold text-gray-400 mb-3 uppercase tracking-wide">Equity Curve</h2>
          <EquityChart data={equity ?? []} />
        </div>

        {/* Right column: score gauge + active model */}
        <div className="space-y-4">
          {/* Live score gauge */}
          <div className="bg-[#1a1d27] rounded-xl border border-[#2a2d3a] p-4">
            <h2 className="text-sm font-semibold text-gray-400 mb-3 uppercase tracking-wide">Live Score</h2>
            <ScoreGauge
              score={status?.currentScore ?? null}
              openPosition={status?.openPosition ?? null}
              signalValues={status?.signalValues ?? null}
            />
          </div>

          {/* Active model weights */}
          <div className="bg-[#1a1d27] rounded-xl border border-[#2a2d3a] p-4">
            <div className="flex items-center justify-between mb-3">
              <div>
                <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide">
                  Active Model
                </h2>
                <p className="text-xs text-gray-600 mt-0.5">
                  {activeWeights
                    ? `v${activeWeights.version} — weights used for scoring`
                    : "defaults — no evolved model yet"}
                </p>
              </div>
              {Array.isArray(weights) && weights.length > 0 && (
                <button
                  onClick={() => setShowHistory(true)}
                  className="text-xs text-indigo-400 hover:text-indigo-300 border border-indigo-500/30 px-2 py-1 rounded-lg shrink-0"
                >
                  History
                </button>
              )}
            </div>
            <WeightsBar weights={activeWeights?.weights ?? null} />
          </div>
        </div>
      </div>

      {/* Signals + Trades */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-[#1a1d27] rounded-xl border border-[#2a2d3a] p-4">
          <h2 className="text-sm font-semibold text-gray-400 mb-3 uppercase tracking-wide">Live Signals (last 10 bars)</h2>
          <SignalsPanel data={signals ?? []} />
        </div>
        <div className="bg-[#1a1d27] rounded-xl border border-[#2a2d3a] p-4">
          <h2 className="text-sm font-semibold text-gray-400 mb-3 uppercase tracking-wide">Recent Trades</h2>
          <TradesTable trades={trades ?? []} />
        </div>
      </div>

      <p className="text-center text-xs text-gray-600 pb-2" suppressHydrationWarning>
        Auto-refresh every 30s · {new Date().toLocaleString()}
      </p>

      {/* Weight history modal */}
      {showHistory && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
          onClick={() => setShowHistory(false)}
        >
          <div
            className="bg-[#1a1d27] border border-[#2a2d3a] rounded-2xl p-6 w-full max-w-3xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-base font-semibold text-white">Signal Weight History</h2>
                <p className="text-xs text-gray-500 mt-0.5">
                  How each signal&apos;s weight changed across evolution generations
                </p>
              </div>
              <button
                onClick={() => setShowHistory(false)}
                className="text-gray-500 hover:text-gray-200 text-xl leading-none"
              >
                ×
              </button>
            </div>
            <WeightHistoryChart rows={Array.isArray(weights) ? weights : []} />
          </div>
        </div>
      )}
    </div>
  );
}

function StatCard({
  label,
  value,
  sub,
  positive,
}: {
  label: string;
  value: string | number;
  sub?: string;
  positive?: boolean;
}) {
  const valueColor =
    positive === undefined
      ? "text-white"
      : positive
      ? "text-green-400"
      : "text-red-400";

  return (
    <div className="bg-[#1a1d27] rounded-xl border border-[#2a2d3a] p-4">
      <p className="text-xs text-gray-500 uppercase tracking-wide">{label}</p>
      <p className={`text-2xl font-bold mt-1 ${valueColor}`}>{value}</p>
      {sub && <p className="text-xs text-gray-600 mt-1 truncate">{sub}</p>}
    </div>
  );
}
