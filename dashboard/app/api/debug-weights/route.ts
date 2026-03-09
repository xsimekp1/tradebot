import { NextResponse } from "next/server";
import getDb from "@/lib/db";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const sql = getDb();
    const rows = await sql`
      SELECT id, version, weights, performance, is_active, created_at
      FROM signal_weights
      WHERE is_active = TRUE
      ORDER BY created_at DESC
      LIMIT 1
    `;

    if (rows.length === 0) {
      return NextResponse.json({ error: "No active weights", rows: [] });
    }

    const row = rows[0];
    return NextResponse.json({
      raw: row,
      weightsType: typeof row.weights,
      weightsKeys: row.weights ? Object.keys(row.weights) : null,
      weightsValues: row.weights ? Object.values(row.weights) : null,
      weightsStringified: JSON.stringify(row.weights),
    });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
