import "server-only";

import { and, eq, inArray, sql } from "drizzle-orm";
import { db } from "@/db/client";
import { bankDecisions, bloodBags, bloodRequests, donorDemand } from "@/db/schema";
import { writeAuditLogSafe } from "@/lib/audit/log";
import { getBankSettings, getStockSummary, type BloodGroup } from "./stock";

type DbTx = Parameters<Parameters<typeof db.transaction>[0]>[0];

/** Products a donor can be recruited for. Platelets, plasma and cryo are not. */
export const DONOR_RECRUITABLE_PRODUCTS = new Set(["whole_blood", "packed_rbc"]);

type DemandInput = {
  trigger: "request_shortfall" | "stock_floor";
  bloodRequestId?: string | null;
  bloodGroup: BloodGroup;
  product?: string;
  units: number;
  dateNeeded: string; // YYYY-MM-DD
  notes?: string | null;
  createdBy: string;
};

/**
 * Hand demand to the donor bot. The bot polls this table; nothing else needs to happen.
 * Hospital identity is snapshotted from settings so a later edit does not rewrite what
 * donors were told.
 */
export async function createDonorDemand(tx: DbTx, input: DemandInput) {
  const settings = await getBankSettings();
  const [row] = await tx
    .insert(donorDemand)
    .values({
      trigger: input.trigger,
      bloodRequestId: input.bloodRequestId ?? null,
      bloodGroup: input.bloodGroup,
      product: (input.product as "whole_blood" | "packed_rbc") ?? "whole_blood",
      units: input.units,
      dateNeeded: input.dateNeeded,
      hospitalName: settings.hospitalName,
      hospitalAddress: settings.hospitalAddress,
      district: settings.district,
      city: settings.city,
      notes: input.notes ?? null,
      createdBy: input.createdBy,
    })
    .returning();
  return row;
}

export type DecisionInput = {
  bloodRequestId: string;
  decision: "approved" | "partial" | "declined";
  unitsToIssue: number;
  note?: string | null;
  recruitDonorsForShortfall: boolean;
  decidedBy: string;
};

export type DecisionResult =
  | { ok: true; unitsIssued: number; demandId: string | null }
  | { ok: false; reason: "not_found" | "not_submitted" | "already_decided" | "insufficient_stock" };

/**
 * Decide a doctor's request: issue bags from stock (oldest expiry first) and, when the
 * request cannot be fully met, raise donor demand for the shortfall.
 *
 * Everything happens in one transaction so a crash halfway cannot issue bags without
 * recording the decision, or record a decision that issued nothing.
 */
export async function decideRequest(input: DecisionInput): Promise<DecisionResult> {
  return db.transaction(async (tx) => {
    const request = await tx.query.bloodRequests.findFirst({
      where: eq(bloodRequests.id, input.bloodRequestId),
      columns: {
        id: true,
        status: true,
        requestedBloodGroup: true,
        product: true,
        units: true,
        dateNeeded: true,
        requestId: true,
      },
    });
    if (!request) return { ok: false, reason: "not_found" as const };
    if (request.status !== "submitted") return { ok: false, reason: "not_submitted" as const };

    const existing = await tx.query.bankDecisions.findFirst({
      where: eq(bankDecisions.bloodRequestId, request.id),
      columns: { id: true },
    });
    if (existing) return { ok: false, reason: "already_decided" as const };

    const group = request.requestedBloodGroup as BloodGroup;
    const unitsRequested = request.units ?? 0;
    const toIssue = input.decision === "declined" ? 0 : Math.min(input.unitsToIssue, unitsRequested);

    let issued: { id: string }[] = [];
    if (toIssue > 0) {
      const bags = await tx
        .select({ id: bloodBags.id })
        .from(bloodBags)
        .where(and(eq(bloodBags.bloodGroup, group), eq(bloodBags.status, "available")))
        .orderBy(bloodBags.expiresAt)
        .limit(toIssue)
        .for("update", { skipLocked: true });
      if (bags.length < toIssue) {
        return { ok: false, reason: "insufficient_stock" as const };
      }
      issued = await tx
        .update(bloodBags)
        .set({
          status: "issued",
          issuedToRequestId: request.id,
          issuedAt: new Date(),
          updatedAt: new Date(),
        })
        .where(
          inArray(
            bloodBags.id,
            bags.map((b) => b.id)
          )
        )
        .returning({ id: bloodBags.id });
    }

    const shortfall = unitsRequested - issued.length;
    let demandId: string | null = null;
    if (
      shortfall > 0 &&
      input.recruitDonorsForShortfall &&
      request.product &&
      DONOR_RECRUITABLE_PRODUCTS.has(request.product)
    ) {
      const demand = await createDonorDemand(tx, {
        trigger: "request_shortfall",
        bloodRequestId: request.id,
        bloodGroup: group,
        product: request.product,
        units: shortfall,
        dateNeeded: request.dateNeeded ?? new Date().toISOString().slice(0, 10),
        notes: request.requestId ? `For request ${request.requestId}` : null,
        createdBy: input.decidedBy,
      });
      demandId = demand.id;
    }

    await tx.insert(bankDecisions).values({
      bloodRequestId: request.id,
      decision: input.decision,
      unitsRequested,
      unitsIssued: issued.length,
      note: input.note ?? null,
      decidedBy: input.decidedBy,
    });

    await writeAuditLogSafe({
      actorType: "doctor",
      actorDoctorId: input.decidedBy,
      action: `bank.decision_${input.decision}`,
      entityType: "blood_request",
      entityId: request.id,
      metadata: { unitsIssued: issued.length, shortfall, demandId },
    });

    return { ok: true as const, unitsIssued: issued.length, demandId };
  });
}

/**
 * Keep every group at the floor (the "25 units always" rule). For each group below
 * it with no open floor demand already, raise demand for the difference.
 */
export async function raiseFloorDemand(createdBy: string, daysAhead = 3): Promise<number> {
  const summary = await getStockSummary();
  const short = summary.filter((line) => line.shortfall > 0);
  if (short.length === 0) return 0;

  const openFloor = await db
    .select({ bloodGroup: donorDemand.bloodGroup })
    .from(donorDemand)
    .where(and(eq(donorDemand.trigger, "stock_floor"), eq(donorDemand.status, "open")));
  const alreadyOpen = new Set(openFloor.map((r) => r.bloodGroup));

  const needed = new Date();
  needed.setDate(needed.getDate() + daysAhead);
  const dateNeeded = needed.toISOString().slice(0, 10);

  let raised = 0;
  await db.transaction(async (tx) => {
    for (const line of short) {
      if (alreadyOpen.has(line.bloodGroup)) continue;
      await createDonorDemand(tx, {
        trigger: "stock_floor",
        bloodGroup: line.bloodGroup,
        units: line.shortfall,
        dateNeeded,
        notes: `Restocking to the ${line.floor}-unit floor`,
        createdBy,
      });
      raised += 1;
    }
  });
  return raised;
}

/** Withdraw a demand the bot may already be working on. The bot notices on its next tick. */
export async function cancelDemand(demandId: string, byUser: string): Promise<boolean> {
  const result = await db
    .update(donorDemand)
    .set({ status: "cancelled", closedAt: new Date(), updatedAt: new Date() })
    .where(and(eq(donorDemand.id, demandId), inArray(donorDemand.status, ["open", "fulfilled"])))
    .returning({ id: donorDemand.id });
  if (result.length) {
    await writeAuditLogSafe({
      actorType: "doctor",
      actorDoctorId: byUser,
      action: "bank.demand_cancel",
      entityType: "donor_demand",
      entityId: demandId,
      metadata: null,
    });
  }
  return result.length > 0;
}

export const demandStatusLabel: Record<string, string> = {
  open: "Recruiting",
  fulfilled: "Donors confirmed",
  completed: "Collected",
  cancelled: "Withdrawn",
  expired: "Expired",
};

export function pendingRequestsWhere() {
  return sql`${bloodRequests.status} = 'submitted' AND NOT EXISTS (
    SELECT 1 FROM bank_decisions bd WHERE bd.blood_request_id = ${bloodRequests.id}
  )`;
}
