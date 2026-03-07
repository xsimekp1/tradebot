"use client";

import useSWR from "swr";
import { useState } from "react";
import { ResearchTable } from "@/components/ResearchTable";
import { WeightsComparison } from "@/components/WeightsComparison";
import { WalkForwardChart } from "@/components/WalkForwardChart";

const fetcher = (url: string) => fetch(url).then((r) => r.json());

export default function ResearchPage() {
  const { data: results, isLoading } = useSWR("/api/research", fetcher, { refreshInterval: 15_000 });
  const [selected, setSelected] = useState<Record<string, unknown> | null>(null);

  const runs = Array.isArray(results) ? results : [];
  const walkForward = runs.filter((r) => r.strategy === "walk_forward");
  const optimized = runs.filter((r) => r.strategy !== "walk_forward");

  return (
    <div className="min-h-screen bg-[#0f1117] text-gray-100 p-4 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white tracking-tight">Research Lab</h1>
          <p className="text-xs text-gray-500">Backtest & walk-forward results · auto-refresh 15s</p>
        </div>
        <a href="/" className="text-xs text-indigo-400 hover:text-indigo-300 border border-indigo-500/30 px-3 py-1.5 rounded-lg">
          Live Dashboard
        </a>
      </div>

      {isLoading && (
        <div className="text-gray-600 text-sm">Loading results...</div>
      )}

      {!isLoading && runs.length === 0 && (
        <div className="bg-[#1a1d27] rounded-xl border border-[#2a2d3a] p-8 text-center">
          <p className="text-gray-400 text-lg mb-2">No results yet</p>
          <p className="text-gray-600 text-sm">Run a backtest with <code className="bg-[#2a2d3a] px-1 rounded">--save</code> to see results here</p>
          <div className="mt-4 text-left inline-block bg-[#0f1117] rounded-lg p-4 text-xs font-mono text-gray-400 space-y-1">
            <p>python scripts/backtest_multi.py --symbol BTC/USD --days 7 \</p>
            <p className="pl-4">--no-short --optimize --trials 300 --save</p>
            <p className="mt-2">python scripts/walk_forward.py --symbol BTC/USD \</p>
            <p className="pl-4">--train-weeks 2 3 4 --no-short --save</p>
          </div>
        </div>
      )}

      {/* Walk-forward section */}
      {walkForward.length > 0 && (
        <div className="space-y-4">
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide">
            Walk-Forward Validation ({walkForward.length} runs)
          </h2>
          <WalkForwardChart runs={walkForward} />
          <ResearchTable runs={walkForward} onSelect={setSelected} selected={selected} />
        </div>
      )}

      {/* Optimization runs */}
      {optimized.length > 0 && (
        <div className="space-y-4">
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide">
            Optimization Runs ({optimized.length} runs)
          </h2>
          <ResearchTable runs={optimized} onSelect={setSelected} selected={selected} />
        </div>
      )}

      {/* Detail panel */}
      {selected && (
        <div className="bg-[#1a1d27] rounded-xl border border-indigo-500/30 p-4 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-indigo-400 uppercase tracking-wide">
              Detail — {String(selected.symbol)} · {String(selected.strategy)} · {String(selected.train_days)}d train
            </h2>
            <button onClick={() => setSelected(null)} className="text-gray-600 hover:text-gray-300 text-xs">close ×</button>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Weights */}
            <div>
              <p className="text-xs text-gray-500 mb-3 uppercase tracking-wide">Signal Weights</p>
              <WeightsComparison weights={selected.weights as Record<string, number>} />
            </div>

            {/* Stats comparison */}
            <div>
              <p className="text-xs text-gray-500 mb-3 uppercase tracking-wide">
                {selected.out_of_sample ? "In-sample vs Out-of-sample" : "In-sample stats"}
              </p>
              <StatsComparison run={selected} />
            </div>
          </div>

          {/* Params */}
          <div>
            <p className="text-xs text-gray-500 mb-2 uppercase tracking-wide">Parameters</p>
            <pre className="text-xs text-gray-400 bg-[#0f1117] p-3 rounded-lg overflow-x-auto">
              {JSON.stringify(selected.params, null, 2)}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}

function StatsComparison({ run }: { run: Record<string, unknown> }) {
  const ins = run.in_sample as Record<string, number> | null;
  const oos = run.out_of_sample as Record<string, number> | null;

  const metrics = [
    { key: "return_pct", label: "Return", fmt: (v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(2)}%` },
    { key: "sharpe", label: "Sharpe", fmt: (v: number) => v.toFixed(2) },
    { key: "win_rate", label: "Win Rate", fmt: (v: number) => `${v.toFixed(1)}%` },
    { key: "num_trades", label: "Trades", fmt: (v: number) => v.toFixed(0) },
    { key: "profit_factor", label: "Profit Factor", fmt: (v: number) => isFinite(v) ? v.toFixed(2) : "inf" },
    { key: "max_dd", label: "Max Drawdown", fmt: (v: number) => `${v.toFixed(2)}%` },
  ];

  const val = (obj: Record<string, number> | null, key: string) => {
    if (!obj) return null;
    // backtest_multi uses slightly different key names
    return obj[key] ?? obj[key.replace("_pct", "_pct").replace("return_pct", "total_return_pct")] ?? null;
  };

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-3 text-xs text-gray-500 pb-1 border-b border-[#2a2d3a]">
        <span>Metric</span>
        <span className="text-center">In-sample</span>
        {oos && <span className="text-center">Out-of-sample</span>}
      </div>
      {metrics.map(({ key, label, fmt }) => {
        const iv = val(ins, key);
        const ov = val(oos, key);
        const isGood = (k: string, v: number) =>
          ["return_pct", "total_return_pct", "sharpe", "win_rate", "profit_factor"].includes(k) ? v > 0 : v > -5;
        return (
          <div key={key} className="grid grid-cols-3 text-xs">
            <span className="text-gray-400">{label}</span>
            <span className={`text-center font-mono ${iv != null && isGood(key, iv) ? "text-green-400" : "text-red-400"}`}>
              {iv != null ? fmt(iv) : "—"}
            </span>
            {oos && (
              <span className={`text-center font-mono ${ov != null && isGood(key, ov) ? "text-green-400" : "text-red-400"}`}>
                {ov != null ? fmt(ov) : "—"}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}
