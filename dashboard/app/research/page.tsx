"use client";

import React from "react";
import useSWR from "swr";
import { WeightsComparison } from "@/components/WeightsComparison";
import { WalkForwardChart } from "@/components/WalkForwardChart";
import { ScoreGauge } from "@/components/ScoreGauge";
import { SignalEvolutionGrid } from "@/components/SignalEvolutionGrid";
import { ThresholdHistoryChart } from "@/components/ThresholdHistoryChart";
import { BacktestMiniChart } from "@/components/BacktestMiniChart";
import { TradeStateViewer } from "@/components/TradeStateViewer";

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
  const { data: evolProgress } = useSWR("/api/evolution-progress", fetcher, { refreshInterval: 3_000 });
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

      {/* Evolution Log */}
      {evolStats?.recentLog && evolStats.recentLog.length > 0 && (
        <div className="bg-[#1a1d27] rounded-xl border border-[#2a2d3a] p-4">
          <h2 className="text-sm font-semibold text-gray-400 mb-3 uppercase tracking-wide">
            Evolution Log
          </h2>
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {evolStats.recentLog.map((entry: {
              versionBefore: number;
              versionAfter: number | null;
              currentSharpe: number | null;
              bestSharpe: number | null;
              mutationsTried: number;
              modelChanged: boolean;
              improvement: number | null;
              createdAt: string;
              channelPosition: number | null;
              channelTrend: number | null;
              threshold: number | null;
              entryBias: number | null;
            }, i: number) => (
              <div
                key={i}
                className={`flex items-center gap-3 p-2 rounded-lg text-xs ${
                  entry.modelChanged
                    ? "bg-green-500/10 border border-green-500/20"
                    : "bg-gray-500/10 border border-gray-500/20"
                }`}
              >
                <span className="text-gray-500 w-16 shrink-0">
                  {new Date(entry.createdAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                </span>
                <span className={`font-medium ${entry.modelChanged ? "text-green-400" : "text-gray-400"}`}>
                  {entry.modelChanged
                    ? `v${entry.versionBefore} -> v${entry.versionAfter}`
                    : `v${entry.versionBefore} kept`}
                </span>
                <span className="text-gray-500">
                  Sharpe: {entry.currentSharpe?.toFixed(2) ?? "—"}
                  {entry.modelChanged && entry.improvement != null && (
                    <span className="text-green-400"> (+{entry.improvement.toFixed(3)})</span>
                  )}
                </span>
                {entry.channelPosition != null && (
                  <span className="text-indigo-400">
                    ch_pos: {(entry.channelPosition * 100).toFixed(1)}%
                  </span>
                )}
                {entry.channelTrend != null && (
                  <span className="text-cyan-400">
                    ch_trend: {(entry.channelTrend * 100).toFixed(1)}%
                  </span>
                )}
                {entry.threshold != null && (
                  <span className="text-amber-400">
                    thr: {entry.threshold.toFixed(3)}
                  </span>
                )}
                <span className="text-gray-600 ml-auto">
                  {entry.mutationsTried} mutations
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Evolution Progress Bar or Trigger Button */}
      {evolProgress?.phase && evolProgress.phase !== "idle" ? (
        <div className="bg-[#1a1d27] rounded-xl border border-[#2a2d3a] p-4">
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide">
              Evolution in Progress
            </h2>
            <span className="text-xs text-indigo-400 animate-pulse">
              {evolProgress.phase}
            </span>
          </div>
          <div className="relative h-3 rounded-full bg-[#2a2d3a] overflow-hidden">
            <div
              className="absolute top-0 left-0 h-full bg-gradient-to-r from-indigo-600 to-indigo-400 transition-all duration-500"
              style={{ width: `${evolProgress.progress_pct ?? 0}%` }}
            />
          </div>
          <p className="text-xs text-gray-500 mt-2">{evolProgress.message || "Working..."}</p>
        </div>
      ) : (
        <TriggerEvolutionButton />
      )}

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

      {/* Trade state viewer */}
      {backtestData?.trades && backtestData.trades.length > 0 && (
        <TradeStateViewer trades={backtestData.trades} />
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

function TriggerEvolutionButton() {
  const [loading, setLoading] = React.useState(false);
  const [result, setResult] = React.useState<string | null>(null);

  const handleTrigger = async () => {
    if (!confirm("Spustit novou evoluci modelu?\n\nToto spusti mutacni cyklus a porovnani s aktualnim modelem.")) {
      return;
    }
    setLoading(true);
    setResult(null);
    try {
      const res = await fetch("/api/trigger-evolution", { method: "POST" });
      const data = await res.json();
      if (data.success) {
        setResult("Evolution triggered!");
        setTimeout(() => setResult(null), 3000);
      } else {
        setResult(`Error: ${data.error}`);
      }
    } catch (e) {
      setResult(`Error: ${String(e)}`);
    }
    setLoading(false);
  };

  return (
    <div className="bg-[#1a1d27] rounded-xl border border-[#2a2d3a] p-4 flex items-center justify-between">
      <div>
        <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide">Evolution Control</h2>
        <p className="text-xs text-gray-600 mt-0.5">No evolution running. Trigger manually or wait for scheduler.</p>
      </div>
      <div className="flex items-center gap-3">
        {result && (
          <span className={`text-xs ${result.startsWith("Error") ? "text-red-400" : "text-green-400"}`}>
            {result}
          </span>
        )}
        <button
          onClick={handleTrigger}
          disabled={loading}
          className="text-sm px-4 py-2 rounded-lg border border-indigo-500/50 bg-indigo-500/10 text-indigo-300 hover:bg-indigo-500/20 disabled:opacity-50 font-medium"
        >
          {loading ? "Starting..." : "Run Evolution"}
        </button>
      </div>
    </div>
  );
}
