import { NextRequest } from "next/server";
import { eq } from "drizzle-orm";
import { db } from "@/db/client";
import { bloodBags } from "@/db/schema";
import { writeAuditLogSafe } from "@/lib/audit/log";
import { guardedFormPost } from "@/lib/bank/route-helpers";
import { addBagSchema } from "@/lib/bank/schema";

/** Add a bag typed in by hand on the inventory page. */
export async function POST(request: NextRequest) {
  return guardedFormPost(request, "/bank/inventory", addBagSchema, async (data, user) => {
    const existing = await db.query.bloodBags.findFirst({
      where: eq(bloodBags.rfidTag, data.rfidTag),
      columns: { id: true },
    });
    if (existing) {
      return "error=bag_exists";
    }

    const [created] = await db
      .insert(bloodBags)
      .values({
        rfidTag: data.rfidTag,
        bloodGroup: data.bloodGroup,
        product: data.product,
        collectedAt: data.collectedAt,
        expiresAt: data.expiresAt,
        addedBy: user.id,
      })
      .returning({ id: bloodBags.id });

    await writeAuditLogSafe({
      actorType: "doctor",
      actorDoctorId: user.id,
      action: "bank.bag_add",
      entityType: "blood_bag",
      entityId: created.id,
      metadata: { rfidTag: data.rfidTag, bloodGroup: data.bloodGroup },
    });
    return `notice=bag_added&group=${encodeURIComponent(data.bloodGroup)}`;
  });
}
