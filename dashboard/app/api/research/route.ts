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
        strategy,
        train_days,
        test_days,
        weights,
        params,
        in_sample,
        out_of_sample,
        notes,
        created_at
      FROM backtest_results
      ORDER BY created_at DESC
      LIMIT 100
    `;
    return NextResponse.json(rows);
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
