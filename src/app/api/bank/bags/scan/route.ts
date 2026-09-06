import { NextRequest, NextResponse } from "next/server";
import { eq } from "drizzle-orm";
import { db } from "@/db/client";
import { bloodBags } from "@/db/schema";
import { writeAuditLogSafe } from "@/lib/audit/log";
import { scanSchema } from "@/lib/bank/schema";

/**
 * The RFID reader's endpoint. A reader has no browser session, so it authenticates
 * with a shared token in `X-Reader-Token` (RFID_READER_TOKEN in .env). JSON in, JSON out.
 *
 *   POST /api/bank/bags/scan
 *   { "rfidTag": "E2000017221101441890A1B2", "action": "lookup" }
 *   { "rfidTag": "...", "action": "stock", "bloodGroup": "O+", "collectedAt": "2026-09-06", "expiresAt": "2026-10-11" }
 *   { "rfidTag": "...", "action": "discard" }
 *
 * `lookup` answers what the bag is; `stock` adds a new bag (or returns the existing
 * one); `discard` removes an available bag from stock. The hardware side is out of
 * scope; this is the contract it will talk to.
 */
export async function POST(request: NextRequest) {
  const expected = process.env.RFID_READER_TOKEN;
  const provided = request.headers.get("x-reader-token");
  if (!expected || !provided || provided !== expected) {
    return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ ok: false, error: "invalid_json" }, { status: 400 });
  }
  const parsed = scanSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      { ok: false, error: "invalid", issues: parsed.error.issues },
      { status: 422 }
    );
  }
  const data = parsed.data;

  const existing = await db.query.bloodBags.findFirst({ where: eq(bloodBags.rfidTag, data.rfidTag) });

  if (data.action === "lookup") {
    return existing
      ? NextResponse.json({ ok: true, found: true, bag: existing })
      : NextResponse.json({ ok: true, found: false });
  }

  if (data.action === "discard") {
    if (!existing) {
      return NextResponse.json({ ok: false, error: "not_found" }, { status: 404 });
    }
    if (existing.status !== "available" && existing.status !== "reserved") {
      return NextResponse.json({ ok: false, error: `bag is ${existing.status}` }, { status: 409 });
    }
    const [updated] = await db
      .update(bloodBags)
      .set({ status: "discarded", updatedAt: new Date() })
      .where(eq(bloodBags.id, existing.id))
      .returning();
    await writeAuditLogSafe({
      actorType: "system",
      action: "bank.bag_discarded",
      entityType: "blood_bag",
      entityId: existing.id,
      metadata: { via: "rfid_reader" },
    });
    return NextResponse.json({ ok: true, bag: updated });
  }

  // action === "stock"
  if (existing) {
    return NextResponse.json({ ok: true, created: false, bag: existing });
  }
  if (!data.bloodGroup || !data.collectedAt || !data.expiresAt) {
    return NextResponse.json(
      { ok: false, error: "bloodGroup, collectedAt and expiresAt are required to stock a new bag" },
      { status: 422 }
    );
  }
  if (data.expiresAt < data.collectedAt) {
    return NextResponse.json({ ok: false, error: "expiresAt before collectedAt" }, { status: 422 });
  }
  const [created] = await db
    .insert(bloodBags)
    .values({
      rfidTag: data.rfidTag,
      bloodGroup: data.bloodGroup,
      product: data.product ?? "whole_blood",
      collectedAt: data.collectedAt,
      expiresAt: data.expiresAt,
    })
    .returning();
  await writeAuditLogSafe({
    actorType: "system",
    action: "bank.bag_add",
    entityType: "blood_bag",
    entityId: created.id,
    metadata: { via: "rfid_reader", rfidTag: data.rfidTag, bloodGroup: data.bloodGroup },
  });
  return NextResponse.json({ ok: true, created: true, bag: created }, { status: 201 });
}
