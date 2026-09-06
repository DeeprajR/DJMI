import { drizzle } from "drizzle-orm/node-postgres";
import { Pool } from "pg";
import * as schema from "./schema";

if (!process.env.DATABASE_URL) {
  throw new Error("DATABASE_URL is not configured.");
}

/**
 * Serverless-friendly pool settings.
 *
 * Every function instance gets its own pool, so keep it small and let idle
 * connections go quickly -- Neon's pooler is what actually multiplexes. The two
 * timeouts matter more than they look: without them a connection that never
 * completes hangs until the platform kills the function, which surfaces as a blank
 * 500 with nothing in the logs. With them it fails in seconds with a real message.
 */
const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  max: 3,
  idleTimeoutMillis: 10_000,
  connectionTimeoutMillis: 8_000,
  statement_timeout: 10_000,
  query_timeout: 10_000,
  keepAlive: true,
});

pool.on("error", (error) => {
  // An idle client dropped by the server; the pool replaces it. Log so it is visible.
  console.error("[db] idle client error:", error.message);
});

export const db = drizzle({ client: pool, schema });
