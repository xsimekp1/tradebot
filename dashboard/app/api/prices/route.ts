import { NextResponse } from "next/server";
import getDb from "@/lib/db";

export const dynamic = "force-dynamic";

export async function GET() {
  // Fetch prices (Coinbase public API, no auth)
  let prices: unknown[] = [];
  try {
    const res = await fetch(
      "https://api.exchange.coinbase.com/products/BTC-USD/candles?granularity=300",
      { cache: "no-store" }
    );
    const klines: number[][] = await res.json();
    // Coinbase returns [time_sec, low, high, open, close, volume], newest first
    prices = klines
      .reverse()
      .slice(-120)
      .map((k) => ({
        time: k[0] * 1000,
        open: k[3],
        high: k[2],
        low: k[1],
        close: k[4],
        volume: k[5],
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
