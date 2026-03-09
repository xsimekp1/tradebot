import { NextResponse } from "next/server";
import getDb from "@/lib/db";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const sql = getDb();
    const [row] = await sql`
      SELECT value FROM bot_cache WHERE key = 'evolution_progress'
    `;

    if (!row?.value) {
      return NextResponse.json({
        phase: "idle",
        progress_pct: 0,
        message: "No evolution running",
        updated_at: null,
      });
    }

    return NextResponse.json(row.value);
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
