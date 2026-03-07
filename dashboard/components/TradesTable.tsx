"use client";

type Trade = {
  id: string;
  symbol: string;
  side: string;
  quantity: string;
  entry_price: string;
  exit_price: string;
  pnl: string;
  score: string;
  opened_at: string;
  closed_at: string;
};

export function TradesTable({ trades }: { trades: Trade[] }) {
  if (!Array.isArray(trades) || trades.length === 0) {
    return (
      <div className="text-sm text-gray-600 text-center py-8">
        No trades yet
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-gray-500 border-b border-[#2a2d3a]">
            <th className="text-left pb-2">Symbol</th>
            <th className="text-left pb-2">Side</th>
            <th className="text-right pb-2">Entry</th>
            <th className="text-right pb-2">Exit</th>
            <th className="text-right pb-2">PnL</th>
            <th className="text-right pb-2">Score</th>
            <th className="text-right pb-2">Opened</th>
            <th className="text-right pb-2">Status</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((t) => {
            const pnl = t.pnl != null ? Number(t.pnl) : null;
            const isOpen = t.closed_at == null;
            const pnlColor = isOpen ? "text-gray-400" : pnl != null && pnl >= 0 ? "text-green-400" : "text-red-400";
            return (
              <tr key={t.id} className="border-b border-[#2a2d3a]/50 hover:bg-[#2a2d3a]/30 transition-colors">
                <td className="py-1.5 font-mono text-gray-200">{t.symbol}</td>
                <td className={`py-1.5 font-medium ${t.side === "long" ? "text-green-400" : "text-red-400"}`}>
                  {t.side.toUpperCase()}
                </td>
                <td className="py-1.5 text-right font-mono text-gray-300">
                  {t.entry_price ? `$${Number(t.entry_price).toFixed(2)}` : "—"}
                </td>
                <td className="py-1.5 text-right font-mono text-gray-300">
                  {t.exit_price ? `$${Number(t.exit_price).toFixed(2)}` : "—"}
                </td>
                <td className={`py-1.5 text-right font-mono font-semibold ${pnlColor}`}>
                  {pnl != null ? `$${pnl >= 0 ? "+" : ""}${pnl.toFixed(2)}` : "open"}
                </td>
                <td className="py-1.5 text-right font-mono text-gray-500">
                  {t.score ? Number(t.score).toFixed(3) : "—"}
                </td>
                <td className="py-1.5 text-right text-gray-600">
                  {t.opened_at ? new Date(t.opened_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "—"}
                </td>
                <td className="py-1.5 text-right">
                  {isOpen ? (
                    <span className="px-1.5 py-0.5 bg-indigo-500/20 text-indigo-400 rounded text-xs">open</span>
                  ) : (
                    <span className="px-1.5 py-0.5 bg-gray-500/20 text-gray-400 rounded text-xs">closed</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
