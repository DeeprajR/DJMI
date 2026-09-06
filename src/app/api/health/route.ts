import { NextResponse } from "next/server";
import { sql } from "drizzle-orm";
import { db } from "@/db/client";

export const dynamic = "force-dynamic";
export const maxDuration = 15;

/**
 * Deployment diagnostics. Answers "is this instance configured and can it reach the
 * database?" without exposing anything: variables are reported as present/absent plus
 * a length, and the connection string only as its host.
 *
 * Safe to leave enabled -- it reveals no secret and performs no write.
 */
export async function GET() {
  const started = Date.now();
  const url = process.env.DATABASE_URL ?? "";

  let host = "(unset)";
  let scheme = "(unset)";
  if (url) {
    try {
      const parsed = new URL(url);
      host = parsed.hostname;
      scheme = parsed.protocol.replace(":", "");
    } catch {
      host = "(unparseable)";
    }
  }

  const env = {
    DATABASE_URL: { present: !!url, scheme, host, length: url.length },
    SESSION_SECRET: {
      present: !!process.env.SESSION_SECRET,
      length: process.env.SESSION_SECRET?.length ?? 0,
      longEnough: (process.env.SESSION_SECRET?.length ?? 0) >= 32,
    },
    RFID_READER_TOKEN: { present: !!process.env.RFID_READER_TOKEN },
    NEXT_PUBLIC_BOT_USERNAME: { value: process.env.NEXT_PUBLIC_BOT_USERNAME ?? null },
    SEAL_STORAGE_DIR: { value: process.env.SEAL_STORAGE_DIR ?? null },
    runtime: { node: process.version, region: process.env.VERCEL_REGION ?? "local" },
  };

  let database: Record<string, unknown>;
  try {
    const t = Date.now();
    const result = await db.execute<{ doctors: number }>(
      sql`select (select count(*)::int from doctors) as doctors`
    );
    database = {
      ok: true,
      connectMs: Date.now() - t,
      doctors: result.rows[0]?.doctors ?? null,
    };
  } catch (error) {
    database = {
      ok: false,
      error: error instanceof Error ? error.message : String(error),
      code: (error as { code?: string })?.code ?? null,
    };
  }

  return NextResponse.json(
    { ok: (database as { ok: boolean }).ok, totalMs: Date.now() - started, env, database },
    { status: (database as { ok: boolean }).ok ? 200 : 503 }
  );
}
