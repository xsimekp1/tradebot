import { NextResponse } from "next/server";
import getDb from "@/lib/db";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const sql = getDb();

    // Get total counts
    const [counts] = await sql`
      SELECT
        COUNT(*) AS total_runs,
        COUNT(*) FILTER (WHERE model_changed = true) AS successful_mutations
      FROM evolution_results
    `;

    // Get current streak (consecutive same outcomes)
    const streakRows = await sql`
      SELECT model_changed, created_at
      FROM evolution_results
      ORDER BY created_at DESC
      LIMIT 50
    `;

    let currentStreak = 0;
    let streakType: "wins" | "no_change" | null = null;
    if (streakRows.length > 0) {
      const firstOutcome = streakRows[0].model_changed;
      streakType = firstOutcome ? "wins" : "no_change";
      for (const row of streakRows) {
        if (row.model_changed === firstOutcome) {
          currentStreak++;
        } else {
          break;
        }
      }
    }

    // Get last change timestamp
    const [lastChange] = await sql`
      SELECT created_at
      FROM evolution_results
      WHERE model_changed = true
      ORDER BY created_at DESC
      LIMIT 1
    `;

    // Get average improvement when model changed
    const [avgImprove] = await sql`
      SELECT AVG(improvement) AS avg_improvement
      FROM evolution_results
      WHERE model_changed = true AND improvement IS NOT NULL
    `;

    const totalRuns = Number(counts?.total_runs ?? 0);
    const successfulMutations = Number(counts?.successful_mutations ?? 0);
    const successRate = totalRuns > 0 ? (successfulMutations / totalRuns) * 100 : 0;

    return NextResponse.json({
      totalRuns,
      successfulMutations,
      successRate: Math.round(successRate * 10) / 10,
      currentStreak,
      streakType,
      lastChangeAt: lastChange?.created_at ?? null,
      avgImprovement: avgImprove?.avg_improvement != null
        ? Math.round(Number(avgImprove.avg_improvement) * 1000) / 1000
        : null,
    });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
