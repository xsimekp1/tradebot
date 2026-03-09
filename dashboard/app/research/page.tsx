"use client";

import React from "react";
import useSWR from "swr";
import { WeightsComparison } from "@/components/WeightsComparison";
import { WalkForwardChart } from "@/components/WalkForwardChart";
import { ScoreGauge } from "@/components/ScoreGauge";
import { SignalEvolutionGrid } from "@/components/SignalEvolutionGrid";
import { ThresholdHistoryChart } from "@/components/ThresholdHistoryChart";
import { BacktestMiniChart } from "@/components/BacktestMiniChart";

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
  const { data: evolStats } = useSWR("/api/evolution-stats", fetcher, { refreshInterval: 15_000 });
  const { data: backtestData } = useSWR("/api/backtest-chart", fetcher, { refreshInterval: 60_000 });
  const weightHistory: WeightRow[] = Array.isArray(weightsRaw) ? weightsRaw : [];
  const activeWeights = weightHistory.find((w) => w.is_active);

  // Format relative time
  const formatRelativeTime = (dateStr: string | null) => {
    if (!dateStr) return "—";
    const diff = Date.now() - new Date(dateStr).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    return `${Math.floor(hours / 24)}d ago`;
  };

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

      {/* Evolution stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <MiniStat
          label="Mutation Success"
          value={evolStats?.successRate != null ? `${evolStats.successRate}%` : "—"}
          sub={evolStats?.totalRuns ? `${evolStats.successfulMutations}/${evolStats.totalRuns} cycles` : undefined}
        />
        <MiniStat
          label="Current Streak"
          value={evolStats?.currentStreak ?? "—"}
          sub={evolStats?.streakType === "wins" ? "consecutive wins" : evolStats?.streakType === "no_change" ? "no change" : undefined}
          positive={evolStats?.streakType === "wins"}
        />
        <MiniStat
          label="Last Model Change"
          value={formatRelativeTime(evolStats?.lastChangeAt)}
        />
        <MiniStat
          label="Avg Improvement"
          value={evolStats?.avgImprovement != null ? `+${evolStats.avgImprovement} Sharpe` : "—"}
          positive={evolStats?.avgImprovement > 0}
        />
      </div>

      {/* Live score + active model side by side */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-[#1a1d27] rounded-xl border border-[#2a2d3a] p-4">
          <h2 className="text-sm font-semibold text-gray-400 mb-3 uppercase tracking-wide">Live Score</h2>
          <ScoreGauge
            score={status?.currentScore ?? null}
            openPosition={status?.openPosition ?? null}
            signalValues={status?.signalValues ?? null}
            weights={activeWeights?.weights ?? null}
          />
        </div>
        <div className="bg-[#1a1d27] rounded-xl border border-[#2a2d3a] p-4">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide">Active Model</h2>
              <p className="text-xs text-gray-600 mt-0.5">
                {activeWeights ? `v${activeWeights.version} — weights currently used for scoring` : "defaults"}
              </p>
            </div>
            <ForceWeightsButton />
          </div>
          {activeWeights ? (
            <WeightsComparison weights={activeWeights.weights} />
          ) : (
            <p className="text-sm text-gray-600">No evolved model yet</p>
          )}
        </div>
      </div>

      {/* Last evolution timing */}
      {activeWeights?.performance && (
        <div className="bg-[#1a1d27] rounded-xl border border-[#2a2d3a] p-4">
          <h2 className="text-sm font-semibold text-gray-400 mb-3 uppercase tracking-wide">Last Evolution</h2>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
            <div>
              <p className="text-gray-500 text-xs uppercase">Total Duration</p>
              <p className="text-white font-medium">
                {(activeWeights.performance as Record<string, number>).evolution_duration_sec != null
                  ? `${(activeWeights.performance as Record<string, number>).evolution_duration_sec}s`
                  : "—"}
              </p>
            </div>
            <div>
              <p className="text-gray-500 text-xs uppercase">Signal Computation</p>
              <p className="text-white font-medium">
                {(activeWeights.performance as Record<string, number>).signal_computation_sec != null
                  ? `${(activeWeights.performance as Record<string, number>).signal_computation_sec}s`
                  : "—"}
              </p>
            </div>
            <div>
              <p className="text-gray-500 text-xs uppercase">Mutations Tried</p>
              <p className="text-white font-medium">
                {(activeWeights.performance as Record<string, number>).mutations_tried ?? "—"}
              </p>
            </div>
            <div>
              <p className="text-gray-500 text-xs uppercase">Evolved At</p>
              <p className="text-white font-medium">
                {new Date(activeWeights.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Evolution performance chart */}
      {weightHistory.length > 0 && (
        <div className="space-y-4">
          <WalkForwardChart rows={weightHistory} />
        </div>
      )}

      {/* Per-signal evolution sparklines + threshold history */}
      {weightHistory.length > 0 && (
        <div className="space-y-4">
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide">
            Signal Coefficient Evolution
          </h2>
          <SignalEvolutionGrid rows={weightHistory} />
          <div className="bg-[#1a1d27] rounded-xl border border-[#2a2d3a] p-4">
            <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-3">Threshold History</h3>
            <ThresholdHistoryChart rows={weightHistory} />
          </div>
        </div>
      )}

      {/* Best backtest OOS chart */}
      {backtestData?.equityCurve && (
        <BacktestMiniChart
          equityCurve={backtestData.equityCurve}
          trades={backtestData.trades ?? []}
          stats={backtestData.stats}
          version={backtestData.version}
        />
      )}

    </div>
  );
}

function MiniStat({ label, value, positive, sub }: { label: string; value: string | number; positive?: boolean; sub?: string }) {
  const color = positive === undefined ? "text-white" : positive ? "text-green-400" : "text-red-400";
  return (
    <div className="bg-[#1a1d27] rounded-xl border border-[#2a2d3a] p-3">
      <p className="text-xs text-gray-500 uppercase tracking-wide">{label}</p>
      <p className={`text-xl font-bold mt-1 ${color}`}>{value}</p>
      {sub && <p className="text-xs text-gray-600 mt-0.5">{sub}</p>}
    </div>
  );
}

function ForceWeightsButton() {
  const [loading, setLoading] = React.useState(false);
  const [result, setResult] = React.useState<string | null>(null);

  const handleForce = async (reset: boolean = false) => {
    const msg = reset
      ? "RESET: Smazat VŠECHNA historická data vah a začít od v1?\n\n• channel_position: 40%\n• channel_trend: 20%\n• ostatní proporčně\n\nTOTO SMAŽE HISTORII EVOLUCE!"
      : "Přepsat váhy na:\n• channel_position: 40%\n• channel_trend: 20%\n• ostatní proporčně snížené\n\nPokračovat?";
    if (!confirm(msg)) {
      return;
    }
    setLoading(true);
    setResult(null);
    try {
      const url = reset ? "/api/force-weights?reset=true" : "/api/force-weights";
      const res = await fetch(url, { method: "POST" });
      const data = await res.json();
      if (data.success) {
        setResult(`✓ ${reset ? "Reset" : "Aktualizováno"} (v${data.version})`);
        setTimeout(() => window.location.reload(), 2000);
      } else {
        setResult(`✗ ${data.error}`);
      }
    } catch (e) {
      setResult(`✗ ${String(e)}`);
    }
    setLoading(false);
  };

  return (
    <div className="flex items-center gap-2">
      {result && <span className={`text-xs ${result.startsWith("✓") ? "text-green-400" : "text-red-400"}`}>{result}</span>}
      <button
        onClick={() => handleForce(false)}
        disabled={loading}
        className="text-xs px-2 py-1 rounded border border-amber-500/50 bg-amber-500/10 text-amber-300 hover:bg-amber-500/20 disabled:opacity-50"
      >
        {loading ? "..." : "Force Weights"}
      </button>
      <button
        onClick={() => handleForce(true)}
        disabled={loading}
        className="text-xs px-2 py-1 rounded border border-red-500/50 bg-red-500/10 text-red-300 hover:bg-red-500/20 disabled:opacity-50"
      >
        Reset All
      </button>
    </div>
  );
}
