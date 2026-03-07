"use client";

const COLORS: Record<string, string> = {
  momentum: "#6366f1",
  rsi: "#8b5cf6",
  bollinger: "#06b6d4",
  vwap: "#0ea5e9",
  atr: "#f59e0b",
  volume: "#10b981",
  breakout: "#f43f5e",
};

export function WeightsComparison({ weights }: { weights: Record<string, number> | null }) {
  if (!weights) return <p className="text-gray-600 text-sm">No weights data</p>;

  const entries = Object.entries(weights)
    .map(([k, v]) => [k, Number(v)] as [string, number])
    .filter(([, v]) => v > 0.005)
    .sort((a, b) => b[1] - a[1]);

  const total = entries.reduce((s, [, v]) => s + v, 0);

  return (
    <div className="space-y-2">
      {entries.map(([name, weight]) => {
        const pct = total > 0 ? (weight / total) * 100 : 0;
        const color = COLORS[name] ?? "#6b7280";
        return (
          <div key={name}>
            <div className="flex justify-between text-xs mb-1">
              <span className="capitalize text-gray-300">{name}</span>
              <span className="text-gray-400 font-mono">{pct.toFixed(1)}%</span>
            </div>
            <div className="h-4 bg-[#2a2d3a] rounded-full overflow-hidden flex items-center">
              <div
                className="h-full rounded-full transition-all"
                style={{ width: `${pct}%`, backgroundColor: color }}
              />
              <span className="text-xs ml-2 font-mono" style={{ color }}>
                {weight.toFixed(3)}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
