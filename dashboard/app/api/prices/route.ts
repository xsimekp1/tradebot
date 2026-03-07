import { NextResponse } from "next/server";
import getDb from "@/lib/db";

export const dynamic = "force-dynamic";

export async function GET() {
  // Fetch prices (Binance public API, no auth)
  let prices: unknown[] = [];
  try {
    const res = await fetch(
      "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=5m&limit=120",
      { cache: "no-store" }
    );
    const klines = await res.json();
    prices = klines.map((k: unknown[]) => ({
      time: k[0] as number,
      close: parseFloat(k[4] as string),
    }));
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }

  // Fetch trades for markers (best-effort, return empty array if DB fails)
  let trades: Record<string, unknown>[] = [];
  try {
    const sql = getDb();
    const rows = await sql`
      SELECT side, entry_price, exit_price, opened_at, closed_at
      FROM trades
      WHERE symbol = 'BTC/USD'
      ORDER BY opened_at DESC
      LIMIT 50
    `;
    trades = rows as Record<string, unknown>[];
  } catch { /* DB unavailable, show chart without markers */ }

  return NextResponse.json({ prices, trades });
}
