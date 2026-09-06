import "server-only";

import { and, asc, eq, lt, sql } from "drizzle-orm";
import { db } from "@/db/client";
import { bankSettings, bloodBags } from "@/db/schema";
import { bloodGroupValues } from "@/lib/blood-request/draft";

export type BloodGroup = (typeof bloodGroupValues)[number];

export type BankSettings = typeof bankSettings.$inferSelect;

/**
 * Seeded on first read so the dashboard works before anyone visits Settings. The
 * placeholder is deliberately obvious; every donor card carries these words.
 */
const PLACEHOLDER_SETTINGS = {
  hospitalName: "Medical College Hospital",
  hospitalAddress: "Blood Bank (set the real address in Settings)",
  district: "Kozhikode",
  city: "Kozhikode",
  minUnitsPerGroup: 25,
} as const;

export async function getBankSettings(): Promise<BankSettings> {
  const existing = await db.query.bankSettings.findFirst({ where: eq(bankSettings.id, 1) });
  if (existing) {
    return existing;
  }
  const [created] = await db
    .insert(bankSettings)
    .values({ id: 1, ...PLACEHOLDER_SETTINGS })
    .onConflictDoNothing()
    .returning();
  return created ?? (await db.query.bankSettings.findFirst({ where: eq(bankSettings.id, 1) }))!;
}

export type StockLine = {
  bloodGroup: BloodGroup;
  available: number;
  reserved: number;
  floor: number;
  /** How many units below the floor; 0 when at or above it. */
  shortfall: number;
  expiringSoon: number;
};

/** Available bags per group against the floor. One row per group, always all eight. */
export async function getStockSummary(settings?: BankSettings): Promise<StockLine[]> {
  const cfg = settings ?? (await getBankSettings());
  const soon = new Date();
  soon.setDate(soon.getDate() + 7);
  const soonIso = soon.toISOString().slice(0, 10);

  const rows = await db
    .select({
      bloodGroup: bloodBags.bloodGroup,
      status: bloodBags.status,
      count: sql<number>`count(*)::int`,
      expiringSoon: sql<number>`count(*) filter (where ${bloodBags.expiresAt} <= ${soonIso})::int`,
    })
    .from(bloodBags)
    .where(sql`${bloodBags.status} in ('available', 'reserved')`)
    .groupBy(bloodBags.bloodGroup, bloodBags.status);

  return bloodGroupValues.map((group) => {
    const available = rows.find((r) => r.bloodGroup === group && r.status === "available");
    const reserved = rows.find((r) => r.bloodGroup === group && r.status === "reserved");
    const count = available?.count ?? 0;
    return {
      bloodGroup: group,
      available: count,
      reserved: reserved?.count ?? 0,
      floor: cfg.minUnitsPerGroup,
      shortfall: Math.max(0, cfg.minUnitsPerGroup - count),
      expiringSoon: available?.expiringSoon ?? 0,
    };
  });
}

/** Available bags of one group, oldest expiry first -- the order they should be issued. */
export async function availableBags(group: BloodGroup, limit?: number) {
  const query = db
    .select()
    .from(bloodBags)
    .where(and(eq(bloodBags.bloodGroup, group), eq(bloodBags.status, "available")))
    .orderBy(asc(bloodBags.expiresAt));
  return limit ? query.limit(limit) : query;
}

/** Bags whose expiry has passed but that are still marked available. */
export async function expireStaleBags(): Promise<number> {
  const today = new Date().toISOString().slice(0, 10);
  const result = await db
    .update(bloodBags)
    .set({ status: "expired", updatedAt: new Date() })
    .where(and(eq(bloodBags.status, "available"), lt(bloodBags.expiresAt, today)))
    .returning({ id: bloodBags.id });
  return result.length;
}
