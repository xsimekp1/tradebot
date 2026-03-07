"use client";

import useSWR from "swr";
import { WeightsComparison } from "@/components/WeightsComparison";
import { WalkForwardChart } from "@/components/WalkForwardChart";
import { ScoreGauge } from "@/components/ScoreGauge";
import { SignalEvolutionGrid } from "@/components/SignalEvolutionGrid";

const fetcher = (url: string) => fetch(url).then((r) => r.json());

type WeightRow = {
  id: string;
  version: number;
  weights: Record<string, number>;
  performance: Record<string, unknown> | null;
  is_active: boolean;
  created_at: string;
};

export default function ResearchPage() {
  const { data: weightsRaw } = useSWR("/api/weights", fetcher, { refreshInterval: 15_000 });
  const { data: status } = useSWR("/api/status", fetcher, { refreshInterval: 15_000 });
  const weightHistory: WeightRow[] = Array.isArray(weightsRaw) ? weightsRaw : [];
  const activeWeights = weightHistory.find((w) => w.is_active);

  return (
    <div className="min-h-screen bg-[#0f1117] text-gray-100 p-4 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white tracking-tight">Research Lab</h1>
          <p className="text-xs text-gray-500">Strategy evolution history · auto-refresh 15s</p>
        </div>
        <a href="/" className="text-xs text-indigo-400 hover:text-indigo-300 border border-indigo-500/30 px-3 py-1.5 rounded-lg">
          Live Dashboard
        </a>
      </div>

      {/* Same stat cards as main dashboard */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <MiniStat label="Equity" value={status?.equity != null ? `$${Number(status.equity).toLocaleString("en", { minimumFractionDigits: 2 })}` : "—"} />
        <MiniStat label="Daily P&L" value={status?.dailyPnl != null ? `${Number(status.dailyPnl) >= 0 ? "+" : ""}$${Number(status.dailyPnl).toFixed(2)}` : "—"} positive={Number(status?.dailyPnl ?? 0) >= 0} />
        <MiniStat label="Total Trades" value={status?.totalTrades ?? "—"} />
        <MiniStat label="Total P&L" value={status?.totalPnl != null ? `${Number(status.totalPnl) >= 0 ? "+" : ""}$${Number(status.totalPnl).toFixed(2)}` : "—"} positive={Number(status?.totalPnl ?? 0) >= 0} />
      </div>

      {/* Live score + active model side by side */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-[#1a1d27] rounded-xl border border-[#2a2d3a] p-4">
          <h2 className="text-sm font-semibold text-gray-400 mb-3 uppercase tracking-wide">Live Score</h2>
          <ScoreGauge
            score={status?.currentScore ?? null}
            openPosition={status?.openPosition ?? null}
            signalValues={status?.signalValues ?? null}
          />
        </div>
        <div className="bg-[#1a1d27] rounded-xl border border-[#2a2d3a] p-4">
          <div className="mb-3">
            <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide">Active Model</h2>
            <p className="text-xs text-gray-600 mt-0.5">
              {activeWeights ? `v${activeWeights.version} — weights currently used for scoring` : "defaults"}
            </p>
          </div>
          {activeWeights ? (
            <WeightsComparison weights={activeWeights.weights} />
          ) : (
            <p className="text-sm text-gray-600">No evolved model yet</p>
          )}
        </div>
      </div>

      {/* Evolution performance chart */}
      {weightHistory.length > 0 && (
        <div className="space-y-4">
          <WalkForwardChart rows={weightHistory} />
        </div>
      )}

      {/* Per-signal evolution sparklines */}
      {weightHistory.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide">
            Signal Coefficient Evolution
          </h2>
          <SignalEvolutionGrid rows={weightHistory} />
        </div>
      )}

      {/* Evolution history */}
      {weightHistory.length > 0 && (
        <div className="space-y-4">
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide">
            Strategy Evolution ({weightHistory.length} versions)
          </h2>
          <div className="space-y-3">
            {weightHistory.map((row) => {
              const oos = (row.performance as Record<string, Record<string, number>> | null)?.out_of_sample;
              const sigma = (row.performance as Record<string, number> | null)?.sigma;
              return (
                <div
                  key={row.id}
                  className={`bg-[#1a1d27] rounded-xl border p-4 ${row.is_active ? "border-indigo-500/50" : "border-[#2a2d3a]"}`}
                >
                  <div className="flex items-start justify-between mb-3">
                    <div>
                      <span className="text-sm font-semibold text-white">
                        v{row.version}
                      </span>
                      {row.is_active && (
                        <span className="ml-2 text-xs bg-indigo-500/20 text-indigo-300 px-2 py-0.5 rounded-full">active</span>
                      )}
                      <span className="ml-3 text-xs text-gray-500">
                        {new Date(row.created_at).toLocaleString([], { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" })}
                      </span>
                      {sigma != null && (
                        <span className="ml-2 text-xs text-gray-600">σ={sigma}</span>
                      )}
                    </div>
                    {oos && (
                      <div className="flex gap-4 text-xs font-mono">
                        <span className={oos.return_pct >= 0 ? "text-green-400" : "text-red-400"}>
                          {oos.return_pct >= 0 ? "+" : ""}{Number(oos.return_pct).toFixed(2)}% OOS
                        </span>
                        <span className="text-gray-400">Sharpe {Number(oos.sharpe).toFixed(2)}</span>
                        <span className="text-gray-400">WR {Number(oos.win_rate).toFixed(1)}%</span>
                      </div>
                    )}
                  </div>
                  <WeightsComparison weights={row.weights} />
                </div>
              );
            })}
          </div>
        </div>
      )}

    </div>
  );
}

function MiniStat({ label, value, positive }: { label: string; value: string | number; positive?: boolean }) {
  const color = positive === undefined ? "text-white" : positive ? "text-green-400" : "text-red-400";
  return (
    <div className="bg-[#1a1d27] rounded-xl border border-[#2a2d3a] p-3">
      <p className="text-xs text-gray-500 uppercase tracking-wide">{label}</p>
      <p className={`text-xl font-bold mt-1 ${color}`}>{value}</p>
    </div>
  );
}
