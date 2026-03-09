import { NextResponse } from "next/server";
import { randomUUID } from "crypto";
import getDb from "@/lib/db";

export const dynamic = "force-dynamic";

// New target weights - channel signals dominant
const TARGET_WEIGHTS = {
  channel_position: 0.40,
  channel_trend: 0.20,
  momentum: 0.08,
  rsi: 0.06,
  bollinger: 0.06,
  channel_slope: 0.06,
  vwap: 0.04,
  volume: 0.04,
  breakout: 0.04,
  atr: 0.02,
};

export async function POST(request: Request) {
  try {
    const sql = getDb();

    // Check for reset mode (deletes all corrupted data)
    const url = new URL(request.url);
    const reset = url.searchParams.get("reset") === "true";

    if (reset) {
      // Delete ALL signal_weights - nuclear option for corrupted DB
      await sql`DELETE FROM signal_weights`;

      // Create fresh v1 with clean target weights
      const newId = randomUUID();
      await sql`
        INSERT INTO signal_weights (id, version, weights, performance, is_active)
        VALUES (
          ${newId},
          1,
          ${JSON.stringify(TARGET_WEIGHTS)}::jsonb,
          ${JSON.stringify({ source: "force-weights-reset" })}::jsonb,
          TRUE
        )
      `;

      return NextResponse.json({
        success: true,
        version: 1,
        reset: true,
        newWeights: TARGET_WEIGHTS,
      });
    }

    // Normal mode: just create new version
    const [current] = await sql`
      SELECT id, version, weights, performance
      FROM signal_weights
      WHERE is_active = TRUE
      ORDER BY created_at DESC
      LIMIT 1
    `;

    const oldVersion = (current?.version as number) ?? 0;

    // Deactivate all existing weights
    await sql`UPDATE signal_weights SET is_active = FALSE WHERE is_active = TRUE`;

    // Create fresh new version with clean target weights
    const newVersion = oldVersion + 1;
    const newId = randomUUID();
    await sql`
      INSERT INTO signal_weights (id, version, weights, performance, is_active)
      VALUES (
        ${newId},
        ${newVersion},
        ${JSON.stringify(TARGET_WEIGHTS)}::jsonb,
        ${JSON.stringify({ source: "force-weights", previous_version: oldVersion })}::jsonb,
        TRUE
      )
    `;

    return NextResponse.json({
      success: true,
      version: newVersion,
      oldVersion,
      newWeights: TARGET_WEIGHTS,
    });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
