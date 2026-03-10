import { NextResponse } from "next/server";
import getDb from "@/lib/db";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const sql = getDb();
    const rows = await sql`
      SELECT id, version, weights, performance, is_active, created_at
      FROM signal_weights
      ORDER BY created_at DESC
      LIMIT 50
    `;
    // Strip _threshold from weights dict (it belongs in performance)
    const clean = rows.map((r) => ({
      ...r,
      weights: Object.fromEntries(
        Object.entries(r.weights as Record<string, number>).filter(([k]) => k !== "_threshold")
      ),
    }));
    return NextResponse.json(clean);
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
