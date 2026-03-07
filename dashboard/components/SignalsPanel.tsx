"use client";

type SignalRow = {
  signal_name: string;
  value: string;
  weight: string;
  score_contribution: string;
  timestamp: string;
};

function SignalBar({ value }: { value: number }) {
  const pct = Math.abs(value) * 50; // max 50% width per side
  const isPos = value >= 0;
  return (
    <div className="flex items-center gap-1 w-24">
      <div className="flex-1 h-3 bg-[#2a2d3a] rounded-full overflow-hidden flex">
        {/* Left side (negative) */}
        <div className="flex-1 flex justify-end">
          {!isPos && (
            <div
              className="h-full bg-red-500 rounded-l-full"
              style={{ width: `${pct}%` }}
            />
          )}
        </div>
        {/* Center divider */}
        <div className="w-px bg-gray-600" />
        {/* Right side (positive) */}
        <div className="flex-1">
          {isPos && (
            <div
              className="h-full bg-green-500 rounded-r-full"
              style={{ width: `${pct}%` }}
            />
          )}
        </div>
      </div>
    </div>
  );
}

export function SignalsPanel({ data }: { data: SignalRow[] }) {
  if (!data || data.length === 0) {
    return (
      <div className="text-sm text-gray-600 text-center py-8">
        No signal data yet
      </div>
    );
  }

  // Get the latest timestamp's signals
  const latestTs = data[0]?.timestamp;
  const latestSignals = data.filter((r) => r.timestamp === latestTs);

  // Group remaining into recent history (last 10 unique timestamps)
  const allTs = [...new Set(data.map((r) => r.timestamp))].slice(0, 10);

  return (
    <div className="space-y-4">
      {/* Latest bar */}
      <div>
        <p className="text-xs text-gray-600 mb-2">
          Latest: {new Date(latestTs).toLocaleTimeString()}
        </p>
        <div className="space-y-1.5">
          {latestSignals.map((s) => {
            const val = Number(s.value);
            const contrib = Number(s.score_contribution);
            return (
              <div key={s.signal_name} className="flex items-center gap-3">
                <span className="w-20 text-xs capitalize text-gray-400">{s.signal_name}</span>
                <SignalBar value={val} />
                <span className={`text-xs w-12 text-right font-mono ${val >= 0 ? "text-green-400" : "text-red-400"}`}>
                  {val >= 0 ? "+" : ""}{val.toFixed(2)}
                </span>
                <span className={`text-xs w-12 text-right font-mono text-gray-600`}>
                  {contrib >= 0 ? "+" : ""}{contrib.toFixed(3)}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Mini history heatmap */}
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-gray-600">
              <th className="text-left py-1 pr-2">Signal</th>
              {allTs.slice(0, 8).map((ts) => (
                <th key={ts} className="text-center px-0.5 w-8">
                  {new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {[...new Set(data.map((r) => r.signal_name))].map((name) => (
              <tr key={name}>
                <td className="capitalize text-gray-400 py-0.5 pr-2">{name}</td>
                {allTs.slice(0, 8).map((ts) => {
                  const cell = data.find((r) => r.signal_name === name && r.timestamp === ts);
                  const val = cell ? Number(cell.value) : 0;
                  const intensity = Math.min(Math.abs(val), 1);
                  const bg = val > 0
                    ? `rgba(74, 222, 128, ${intensity * 0.7})`
                    : val < 0
                    ? `rgba(248, 113, 113, ${intensity * 0.7})`
                    : "transparent";
                  return (
                    <td key={ts} className="text-center px-0.5">
                      <div
                        className="w-7 h-5 rounded text-center leading-5 mx-auto font-mono"
                        style={{ backgroundColor: bg, fontSize: 9 }}
                        title={`${name} @ ${new Date(ts).toLocaleTimeString()}: ${val.toFixed(2)}`}
                      >
                        {val !== 0 ? (val > 0 ? "+" : "") + val.toFixed(1) : "·"}
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
