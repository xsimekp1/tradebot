import { NextResponse } from "next/server";
import getDb from "@/lib/db";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const sql = getDb();
    const rows = await sql`
      SELECT
        timestamp,
        total_equity,
        cash,
        portfolio_value,
        daily_pnl,
        cumulative_pnl
      FROM equity_curve
      ORDER BY timestamp DESC
      LIMIT 1000
    `;
    // Reverse to chronological order for charts
    return NextResponse.json(rows.reverse());
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
