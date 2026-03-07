import { NextResponse } from "next/server";
import getDb from "@/lib/db";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const sql = getDb();
    // Last 50 timestamps × all signals
    const rows = await sql`
      WITH recent_ts AS (
        SELECT DISTINCT timestamp
        FROM trading_signals
        ORDER BY timestamp DESC
        LIMIT 50
      )
      SELECT
        s.signal_name,
        s.value,
        s.weight,
        s.score_contribution,
        s.timestamp
      FROM trading_signals s
      JOIN recent_ts r ON s.timestamp = r.timestamp
      ORDER BY s.timestamp DESC, s.signal_name
    `;
    return NextResponse.json(rows);
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
