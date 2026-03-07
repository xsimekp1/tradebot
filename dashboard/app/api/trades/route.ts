import { NextResponse } from "next/server";
import getDb from "@/lib/db";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const sql = getDb();
    const rows = await sql`
      SELECT
        id,
        symbol,
        side,
        quantity,
        entry_price,
        exit_price,
        pnl,
        score,
        opened_at,
        closed_at,
        alpaca_order_id
      FROM trades
      ORDER BY opened_at DESC
      LIMIT 30
    `;
    return NextResponse.json(rows);
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
