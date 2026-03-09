import { NextResponse } from "next/server";
import getDb from "@/lib/db";

export const dynamic = "force-dynamic";

// Read channel info from database cache table
async function getChannelInfoFromDb(sql: ReturnType<typeof getDb>): Promise<Record<string, number> | null> {
  try {
    const [row] = await sql`
      SELECT value FROM bot_cache WHERE key = 'channel_info'
    `;
    return row?.value ?? null;
  } catch {
    return null;
  }
}

export async function GET() {
  try {
    const sql = getDb();
    const [latestSignal] = await sql`
      SELECT timestamp FROM equity_curve ORDER BY timestamp DESC LIMIT 1
    `;
    const [latestEquity] = await sql`
      SELECT total_equity, daily_pnl, timestamp FROM equity_curve ORDER BY timestamp DESC LIMIT 1
    `;
    const [tradeCount] = await sql`
      SELECT COUNT(*) AS total,
             COUNT(*) FILTER (WHERE pnl > 0) AS winners
      FROM trades WHERE closed_at IS NOT NULL
    `;
    const [totalPnlRow] = await sql`
      SELECT COALESCE(SUM(pnl), 0) AS total_pnl
      FROM trades WHERE closed_at IS NOT NULL
    `;

    // Current composite score = sum of score_contributions at latest bar
    const [scoreRow] = await sql`
      SELECT
        COALESCE(SUM(score_contribution), 0) AS score,
        jsonb_object_agg(signal_name, value) AS signal_values
      FROM trading_signals
      WHERE timestamp = (SELECT MAX(timestamp) FROM trading_signals)
    `;

    // Get current weights and thresholds
    const [weightsRow] = await sql`
      SELECT weights, performance FROM signal_weights WHERE is_active = TRUE ORDER BY created_at DESC LIMIT 1
    `;
    const weights = weightsRow?.weights ?? null;
    const performance = weightsRow?.performance ?? {};
    const threshold = performance?.threshold ?? 0.15;
    const entryBias = performance?.entry_bias ?? 0.03;

    // Current open position
    const [openPos] = await sql`
      SELECT side, entry_price, score FROM trades WHERE closed_at IS NULL ORDER BY opened_at DESC LIMIT 1
    `;

    // Get current symbol from latest signal or trade
    const [symbolRow] = await sql`
      SELECT symbol FROM trading_signals ORDER BY timestamp DESC LIMIT 1
    `;
    const symbol = symbolRow?.symbol ?? "AAPL";

    const lastHeartbeat = latestSignal?.timestamp ?? null;
    const nowMs = Date.now();
    const lastMs = lastHeartbeat ? new Date(lastHeartbeat).getTime() : 0;
    const secondsAgo = Math.floor((nowMs - lastMs) / 1000);
    const isLive = secondsAgo < 180; // consider live if signal within 3 min

    return NextResponse.json({
      symbol,
      isLive,
      secondsAgo,
      lastHeartbeat,
      equity: latestEquity?.total_equity ?? null,
      dailyPnl: latestEquity?.daily_pnl ?? null,
      equityTimestamp: latestEquity?.timestamp ?? null,
      totalTrades: Number(tradeCount?.total ?? 0),
      winners: Number(tradeCount?.winners ?? 0),
      totalPnl: Number(totalPnlRow?.total_pnl ?? 0),
      currentScore: scoreRow?.score != null ? Number(scoreRow.score) : null,
      signalValues: scoreRow?.signal_values ?? null,
      weights,
      threshold,
      entryBias,
      openPosition: openPos ? { side: openPos.side, entryPrice: Number(openPos.entry_price) } : null,
      channelInfo: await getChannelInfoFromDb(sql),
    });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
