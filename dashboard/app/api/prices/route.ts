import { NextResponse } from "next/server";
import getDb from "@/lib/db";

export const dynamic = "force-dynamic";

// Get current symbol from DB
async function getCurrentSymbol(): Promise<string> {
  try {
    const sql = getDb();
    const [row] = await sql`
      SELECT symbol FROM trading_signals ORDER BY timestamp DESC LIMIT 1
    `;
    return row?.symbol ?? "AAPL";
  } catch {
    return "AAPL";
  }
}

// Fetch trades for markers
async function getTrades(symbol: string): Promise<Record<string, unknown>[]> {
  try {
    const sql = getDb();
    const rows = await sql`
      SELECT side, entry_price, exit_price, opened_at, closed_at
      FROM trades
      WHERE symbol = ${symbol}
      ORDER BY opened_at DESC
      LIMIT 50
    `;
    return rows as Record<string, unknown>[];
  } catch {
    return [];
  }
}

// Yahoo Finance chart API (public, no auth needed)
async function fetchFromYahoo(symbol: string) {
  let prices: unknown[] = [];
  try {
    // Get 1-day of 1-minute data
    const url = `https://query1.finance.yahoo.com/v8/finance/chart/${symbol}?interval=1m&range=1d`;
    const res = await fetch(url, {
      cache: "no-store",
      headers: { "User-Agent": "Mozilla/5.0" },
    });

    if (!res.ok) {
      console.error(`Yahoo API error: ${res.status}`);
      return null;
    }

    const data = await res.json();
    const result = data.chart?.result?.[0];
    if (!result) return null;

    const timestamps = result.timestamp ?? [];
    const quote = result.indicators?.quote?.[0] ?? {};

    prices = timestamps.map((t: number, i: number) => ({
      time: t * 1000,
      open: quote.open?.[i] ?? 0,
      high: quote.high?.[i] ?? 0,
      low: quote.low?.[i] ?? 0,
      close: quote.close?.[i] ?? 0,
      volume: quote.volume?.[i] ?? 0,
    })).filter((p: { close: number }) => p.close > 0);  // Filter out nulls

    return prices;
  } catch (e) {
    console.error("Yahoo fetch error:", e);
    return null;
  }
}

// Alpaca Crypto Data API
async function fetchFromAlpaca(symbol: string) {
  const apiKey = process.env.ALPACA_API_KEY;
  const secretKey = process.env.ALPACA_SECRET_KEY;

  if (!apiKey || !secretKey) return null;

  try {
    const params = new URLSearchParams({
      symbols: symbol,
      timeframe: "1Min",
      limit: "120",
    });

    const res = await fetch(`https://data.alpaca.markets/v1beta3/crypto/us/bars?${params}`, {
      headers: {
        "APCA-API-KEY-ID": apiKey,
        "APCA-API-SECRET-KEY": secretKey,
      },
      cache: "no-store",
    });

    if (!res.ok) return null;

    const data = await res.json();
    const bars = data.bars?.[symbol] ?? [];

    return bars.map((bar: { t: string; o: number; h: number; l: number; c: number; v: number }) => ({
      time: new Date(bar.t).getTime(),
      open: bar.o,
      high: bar.h,
      low: bar.l,
      close: bar.c,
      volume: bar.v,
    }));
  } catch {
    return null;
  }
}

// Fallback to Coinbase for BTC
async function fetchFromCoinbase() {
  try {
    const res = await fetch(
      "https://api.exchange.coinbase.com/products/BTC-USD/candles?granularity=300",
      { cache: "no-store" }
    );
    const klines: number[][] = await res.json();
    return klines
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
  } catch {
    return [];
  }
}

export async function GET() {
  const symbol = await getCurrentSymbol();
  const isCrypto = symbol.includes("/") || symbol === "BTC" || symbol === "ETH";

  let prices: unknown[] = [];
  let source = "unknown";

  if (isCrypto) {
    // Try Alpaca first, then Coinbase
    prices = await fetchFromAlpaca(symbol) ?? [];
    source = prices.length > 0 ? "alpaca" : "unknown";

    if (prices.length === 0) {
      prices = await fetchFromCoinbase();
      source = prices.length > 0 ? "coinbase-fallback" : "unknown";
    }
  } else {
    // For stocks, use Yahoo Finance
    prices = await fetchFromYahoo(symbol) ?? [];
    source = prices.length > 0 ? "yahoo" : "unknown";
  }

  const trades = await getTrades(symbol);

  return NextResponse.json({ prices, trades, source, symbol });
}
