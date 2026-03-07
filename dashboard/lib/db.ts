import postgres from "postgres";

let sql: ReturnType<typeof postgres>;

// Reuse connection in dev, create new in prod (Vercel serverless)
function getDb() {
  if (!sql) {
    sql = postgres(process.env.DATABASE_URL!, {
      ssl: "require",
      max: 5,
      idle_timeout: 20,
      connect_timeout: 10,
    });
  }
  return sql;
}

export default getDb;
