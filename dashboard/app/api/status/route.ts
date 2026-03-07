import { NextResponse } from "next/server";
import getDb from "@/lib/db";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const sql = getDb();
    const [latestSignal] = await sql`
      SELECT timestamp FROM trading_signals ORDER BY timestamp DESC LIMIT 1
    `;
    const [latestEquity] = await sql`
      SELECT total_equity, daily_pnl, timestamp FROM equity_curve ORDER BY timestamp DESC LIMIT 1
    `;
    const [tradeCount] = await sql`
      SELECT COUNT(*) AS total,
             COUNT(*) FILTER (WHERE pnl > 0) AS winners,
             SUM(pnl) AS total_pnl
      FROM trades WHERE closed_at IS NOT NULL
    `;

    const lastHeartbeat = latestSignal?.timestamp ?? null;
    const nowMs = Date.now();
    const lastMs = lastHeartbeat ? new Date(lastHeartbeat).getTime() : 0;
    const secondsAgo = Math.floor((nowMs - lastMs) / 1000);
    const isLive = secondsAgo < 180; // consider live if signal within 3 min

    return NextResponse.json({
      isLive,
      secondsAgo,
      lastHeartbeat,
      equity: latestEquity?.total_equity ?? null,
      dailyPnl: latestEquity?.daily_pnl ?? null,
      equityTimestamp: latestEquity?.timestamp ?? null,
      totalTrades: Number(tradeCount?.total ?? 0),
      winners: Number(tradeCount?.winners ?? 0),
      totalPnl: Number(tradeCount?.total_pnl ?? 0),
    });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
