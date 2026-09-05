import "server-only";

import { sql } from "drizzle-orm";
import { db } from "@/db/client";

type DbTx = Parameters<Parameters<typeof db.transaction>[0]>[0];

type CounterRow = {
  current_value: number;
};

export async function allocateBloodRequestId(
  tx: DbTx,
  at: Date
): Promise<string> {
  const year = at.getUTCFullYear();

  const result = await tx.execute<CounterRow>(sql`
    INSERT INTO blood_request_counters (request_year, current_value, updated_at)
    VALUES (${year}, 1, ${at})
    ON CONFLICT (request_year)
    DO UPDATE SET
      current_value = blood_request_counters.current_value + 1,
      updated_at = ${at}
    RETURNING current_value;
  `);

  const current = result.rows[0]?.current_value;
  if (!current || current < 1) {
    throw new Error("Failed to allocate blood request counter.");
  }

  return `BR-${year}-${String(current).padStart(6, "0")}`;
}
