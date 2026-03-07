"use client";

type Run = Record<string, unknown>;

export function ResearchTable({
  runs,
  onSelect,
  selected,
}: {
  runs: Run[];
  onSelect: (r: Run) => void;
  selected: Run | null;
}) {
  return (
    <div className="bg-[#1a1d27] rounded-xl border border-[#2a2d3a] overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-gray-500 border-b border-[#2a2d3a]">
            <th className="text-left p-3">Date</th>
            <th className="text-left p-3">Symbol</th>
            <th className="text-left p-3">Strategy</th>
            <th className="text-right p-3">Train</th>
            <th className="text-right p-3">Test</th>
            <th className="text-right p-3">Return (IS)</th>
            <th className="text-right p-3">Sharpe (IS)</th>
            <th className="text-right p-3">WR (IS)</th>
            <th className="text-right p-3">Return (OOS)</th>
            <th className="text-right p-3">Sharpe (OOS)</th>
            <th className="text-right p-3">Verdict</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => {
            const ins = r.in_sample as Record<string, number> | null;
            const oos = r.out_of_sample as Record<string, number> | null;
            const isSelected = selected?.id === r.id;

            const inReturn = ins?.return_pct ?? ins?.total_return_pct ?? null;
            const inSharpe = ins?.sharpe ?? null;
            const inWR = ins?.win_rate ?? null;
            const oosReturn = oos?.return_pct ?? null;
            const oosSharpe = oos?.sharpe ?? null;

            const verdict = oos
              ? oosSharpe != null && oosSharpe > 1 && oosReturn != null && oosReturn > 0
                ? { label: "PASS", color: "text-green-400" }
                : oosReturn != null && oosReturn > 0
                ? { label: "PARTIAL", color: "text-yellow-400" }
                : { label: "FAIL", color: "text-red-400" }
              : null;

            const strategyLabel: Record<string, string> = {
              walk_forward: "Walk-Forward",
              multi_signal_optimize: "Optimize",
              multi_signal: "Multi-Signal",
              rsi_single: "RSI Single",
            };

            return (
              <tr
                key={String(r.id)}
                className={`border-b border-[#2a2d3a]/50 cursor-pointer transition-colors ${
                  isSelected ? "bg-indigo-500/10 border-indigo-500/30" : "hover:bg-[#2a2d3a]/30"
                }`}
                onClick={() => onSelect(r)}
              >
                <td className="p-3 text-gray-500">
                  {new Date(String(r.created_at)).toLocaleString([], { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" })}
                </td>
                <td className="p-3 font-mono text-gray-200">{String(r.symbol)}</td>
                <td className="p-3 text-indigo-300">{strategyLabel[String(r.strategy)] ?? String(r.strategy)}</td>
                <td className="p-3 text-right text-gray-400">{String(r.train_days)}d</td>
                <td className="p-3 text-right text-gray-400">{r.test_days ? `${String(r.test_days)}d` : "—"}</td>
                <td className={`p-3 text-right font-mono ${inReturn != null && inReturn >= 0 ? "text-green-400" : "text-red-400"}`}>
                  {inReturn != null ? `${inReturn >= 0 ? "+" : ""}${inReturn.toFixed(2)}%` : "—"}
                </td>
                <td className="p-3 text-right font-mono text-gray-300">
                  {inSharpe != null ? inSharpe.toFixed(2) : "—"}
                </td>
                <td className="p-3 text-right font-mono text-gray-300">
                  {inWR != null ? `${inWR.toFixed(1)}%` : "—"}
                </td>
                <td className={`p-3 text-right font-mono ${oosReturn != null && oosReturn >= 0 ? "text-green-400" : oosReturn != null ? "text-red-400" : "text-gray-600"}`}>
                  {oosReturn != null ? `${oosReturn >= 0 ? "+" : ""}${oosReturn.toFixed(2)}%` : "—"}
                </td>
                <td className={`p-3 text-right font-mono ${oosSharpe != null && oosSharpe > 1 ? "text-green-400" : oosSharpe != null ? "text-yellow-400" : "text-gray-600"}`}>
                  {oosSharpe != null ? oosSharpe.toFixed(2) : "—"}
                </td>
                <td className={`p-3 text-right font-semibold ${verdict?.color ?? "text-gray-600"}`}>
                  {verdict?.label ?? "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
