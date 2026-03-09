import { NextResponse } from "next/server";
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

export async function POST() {
  try {
    const sql = getDb();

    // Get current active model
    const [current] = await sql`
      SELECT id, version, weights, performance
      FROM signal_weights
      WHERE is_active = TRUE
      ORDER BY created_at DESC
      LIMIT 1
    `;

    if (!current) {
      // No active model - create the first one with target weights
      const [inserted] = await sql`
        INSERT INTO signal_weights (version, weights, performance, is_active)
        VALUES (1, ${JSON.stringify(TARGET_WEIGHTS)}::jsonb, ${JSON.stringify({ source: "force-weights-init" })}::jsonb, TRUE)
        RETURNING version
      `;

      return NextResponse.json({
        success: true,
        version: inserted.version,
        oldWeights: null,
        newWeights: TARGET_WEIGHTS,
        created: true,
      });
    }

    const oldWeights = current.weights as Record<string, number>;
    const version = current.version as number;

    // Update weights
    await sql`
      UPDATE signal_weights
      SET weights = ${JSON.stringify(TARGET_WEIGHTS)}::jsonb
      WHERE id = ${current.id}
    `;

    return NextResponse.json({
      success: true,
      version,
      oldWeights,
      newWeights: TARGET_WEIGHTS,
      changes: Object.keys(TARGET_WEIGHTS).map(k => ({
        signal: k,
        old: oldWeights[k] ?? 0,
        new: TARGET_WEIGHTS[k as keyof typeof TARGET_WEIGHTS],
      })),
    });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
