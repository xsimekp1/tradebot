"use client";

const DEFAULT_WEIGHTS: Record<string, number> = {
  momentum: 0.25,
  rsi: 0.20,
  bollinger: 0.15,
  vwap: 0.15,
  atr: 0.05,
  volume: 0.10,
  breakout: 0.10,
};

const SIGNAL_COLORS: Record<string, string> = {
  momentum: "#6366f1",
  rsi: "#8b5cf6",
  bollinger: "#06b6d4",
  vwap: "#0ea5e9",
  atr: "#f59e0b",
  volume: "#10b981",
  breakout: "#f43f5e",
};

export function WeightsBar({ weights }: { weights: Record<string, number> | null }) {
  const w = weights ?? DEFAULT_WEIGHTS;
  const entries = Object.entries(w).sort((a, b) => b[1] - a[1]);

  return (
    <div className="space-y-3">
      {entries.map(([name, weight]) => {
        const pct = (Number(weight) * 100).toFixed(1);
        const color = SIGNAL_COLORS[name] ?? "#6b7280";
        return (
          <div key={name}>
            <div className="flex justify-between text-xs mb-1">
              <span className="capitalize text-gray-300">{name}</span>
              <span className="text-gray-500">{pct}%</span>
            </div>
            <div className="h-2 bg-[#2a2d3a] rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{ width: `${pct}%`, backgroundColor: color }}
              />
            </div>
          </div>
        );
      })}
      {!weights && (
        <p className="text-xs text-gray-600 mt-2">Using default weights</p>
      )}
    </div>
  );
}
