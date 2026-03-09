import { NextResponse } from "next/server";
import getDb from "@/lib/db";

export const dynamic = "force-dynamic";

export async function POST() {
  try {
    const sql = getDb();

    // Check if evolution is already running
    const [progress] = await sql`
      SELECT value FROM bot_cache WHERE key = 'evolution_progress'
    `;

    const status = progress?.value;
    if (status && typeof status === "object" && "phase" in status) {
      if (status.phase !== "idle") {
        return NextResponse.json({
          success: false,
          error: "Evolution already in progress",
          phase: status.phase
        }, { status: 409 });
      }
    }

    // Set trigger flag in bot_cache
    const triggerValue = JSON.stringify({
      requested: true,
      requested_at: new Date().toISOString()
    });
    await sql`
      INSERT INTO bot_cache (key, value, updated_at)
      VALUES ('evolution_trigger', ${triggerValue}::jsonb, NOW())
      ON CONFLICT (key) DO UPDATE SET
        value = ${triggerValue}::jsonb,
        updated_at = NOW()
    `;

    return NextResponse.json({
      success: true,
      message: "Evolution triggered. Check progress bar for status."
    });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
