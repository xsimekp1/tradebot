import { NextResponse } from "next/server";
import getDb from "@/lib/db";

export const dynamic = "force-dynamic";

// Alpaca Crypto Data API - same source as Python backend
const ALPACA_DATA_URL = "https://data.alpaca.markets/v1beta3/crypto/us/bars";

type AlpacaBar = {
  t: string;  // timestamp ISO
  o: number;  // open
  h: number;  // high
  l: number;  // low
  c: number;  // close
  v: number;  // volume
};

type AlpacaResponse = {
  bars: {
    "BTC/USD": AlpacaBar[];
  };
  next_page_token?: string;
};

export async function GET() {
  const apiKey = process.env.ALPACA_API_KEY;
  const secretKey = process.env.ALPACA_SECRET_KEY;

  if (!apiKey || !secretKey) {
    // Fallback to Coinbase if Alpaca not configured
    return fetchFromCoinbase();
  }

  // Fetch 1-minute bars from Alpaca (same as backend)
  let prices: unknown[] = [];
  try {
    const params = new URLSearchParams({
      symbols: "BTC/USD",
      timeframe: "1Min",
      limit: "120",
    });

    const res = await fetch(`${ALPACA_DATA_URL}?${params}`, {
      headers: {
        "APCA-API-KEY-ID": apiKey,
        "APCA-API-SECRET-KEY": secretKey,
      },
      cache: "no-store",
    });

    if (!res.ok) {
      console.error(`Alpaca API error: ${res.status} ${res.statusText}`);
      return fetchFromCoinbase();
    }

    const data: AlpacaResponse = await res.json();
    const bars = data.bars?.["BTC/USD"] ?? [];

    prices = bars.map((bar) => ({
      time: new Date(bar.t).getTime(),
      open: bar.o,
      high: bar.h,
      low: bar.l,
      close: bar.c,
      volume: bar.v,
    }));
  } catch (e) {
    console.error("Alpaca fetch error:", e);
    return fetchFromCoinbase();
  }

  // Fetch trades for markers
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

  return NextResponse.json({ prices, trades, source: "alpaca" });
}

// Fallback to Coinbase public API (no auth needed)
async function fetchFromCoinbase() {
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

  // Fetch trades for markers
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
  } catch { /* DB unavailable */ }

  return NextResponse.json({ prices, trades, source: "coinbase-fallback" });
}
