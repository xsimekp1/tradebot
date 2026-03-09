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

    // Get recent evolution results with weights info
    const recentResults = await sql`
      SELECT
        er.version_before,
        er.version_after,
        er.current_sharpe,
        er.best_sharpe,
        er.mutations_tried,
        er.model_changed,
        er.improvement,
        er.created_at,
        sw.weights,
        sw.performance
      FROM evolution_results er
      LEFT JOIN signal_weights sw ON sw.version = COALESCE(er.version_after, er.version_before)
      ORDER BY er.created_at DESC
      LIMIT 10
    `;

    const totalRuns = Number(counts?.total_runs ?? 0);
    const successfulMutations = Number(counts?.successful_mutations ?? 0);
    const successRate = totalRuns > 0 ? (successfulMutations / totalRuns) * 100 : 0;

    // Format recent results for frontend
    const recentLog = recentResults.map((r) => {
      const weights = typeof r.weights === "string" ? JSON.parse(r.weights) : r.weights;
      const perf = typeof r.performance === "string" ? JSON.parse(r.performance) : r.performance;
      return {
        versionBefore: r.version_before,
        versionAfter: r.version_after,
        currentSharpe: r.current_sharpe != null ? Number(r.current_sharpe) : null,
        bestSharpe: r.best_sharpe != null ? Number(r.best_sharpe) : null,
        mutationsTried: r.mutations_tried,
        modelChanged: r.model_changed,
        improvement: r.improvement != null ? Number(r.improvement) : null,
        createdAt: r.created_at,
        channelPosition: weights?.channel_position != null ? Number(weights.channel_position) : null,
        channelTrend: weights?.channel_trend != null ? Number(weights.channel_trend) : null,
        threshold: perf?.threshold != null ? Number(perf.threshold) : null,
        entryBias: perf?.entry_bias != null ? Number(perf.entry_bias) : null,
      };
    });

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
      recentLog,
    });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
