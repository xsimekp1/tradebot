import { NextResponse } from "next/server";
import getDb from "@/lib/db";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const sql = getDb();
    const [row] = await sql`
      SELECT version, performance, created_at
      FROM signal_weights
      WHERE is_active = TRUE
      ORDER BY created_at DESC
      LIMIT 1
    `;

    if (!row?.performance) {
      return NextResponse.json({ equityCurve: null, trades: null, version: null });
    }

    const perf = row.performance as Record<string, unknown>;
    const oos = perf.out_of_sample as Record<string, unknown> | null;

    if (!oos?.equity_curve) {
      return NextResponse.json({ equityCurve: null, trades: null, version: row.version });
    }

    return NextResponse.json({
      version: row.version,
      createdAt: row.created_at,
      stats: {
        return_pct: oos.return_pct,
        sharpe: oos.sharpe,
        num_trades: oos.num_trades,
        win_rate: oos.win_rate,
        max_dd: oos.max_dd,
      },
      equityCurve: oos.equity_curve,
      trades: oos.trades_log,
    });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
