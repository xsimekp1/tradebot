"use client";

export function StatusBar({ status }: { status?: Record<string, unknown> }) {
  if (!status) return <div className="h-6 w-24 bg-[#2a2d3a] rounded animate-pulse" />;

  const isLive = status.isLive as boolean;
  const secondsAgo = status.secondsAgo as number;

  const label = isLive
    ? "LIVE"
    : secondsAgo < 3600
    ? `${Math.floor(secondsAgo / 60)}m ago`
    : "OFFLINE";

  return (
    <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full border text-sm font-medium ${
      isLive
        ? "border-green-500/40 bg-green-500/10 text-green-400"
        : "border-red-500/40 bg-red-500/10 text-red-400"
    }`}>
      <span className={`w-2 h-2 rounded-full ${isLive ? "bg-green-400 animate-pulse" : "bg-red-400"}`} />
      {label}
      {isLive && secondsAgo > 0 && (
        <span className="text-xs text-green-600">{secondsAgo}s</span>
      )}
    </div>
  );
}
