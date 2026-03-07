import { NextResponse } from "next/server";
import getDb from "@/lib/db";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    // Fetch recent BTC/USD 5m candles from Binance (public, no auth)
    const res = await fetch(
      "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=5m&limit=120",
      { next: { revalidate: 0 } }
    );
    const klines = await res.json();

    const prices = klines.map((k: unknown[]) => ({
      time: k[0] as number,           // open time ms
      open: parseFloat(k[1] as string),
      high: parseFloat(k[2] as string),
      low: parseFloat(k[3] as string),
      close: parseFloat(k[4] as string),
    }));

    // Fetch trades from DB for markers
    const sql = getDb();
    const trades = await sql`
      SELECT side, entry_price, exit_price, opened_at, closed_at, pnl
      FROM trades
      WHERE symbol = 'BTC/USD'
      ORDER BY opened_at DESC
      LIMIT 50
    `;

    return NextResponse.json({ prices, trades });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
