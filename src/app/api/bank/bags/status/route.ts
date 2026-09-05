import { NextRequest } from "next/server";
import { and, eq, inArray } from "drizzle-orm";
import { db } from "@/db/client";
import { bloodBags } from "@/db/schema";
import { writeAuditLogSafe } from "@/lib/audit/log";
import { guardedFormPost } from "@/lib/bank/route-helpers";
import { bagStatusSchema } from "@/lib/bank/schema";

/** Discard, expire, or restore a bag. Issued bags are immutable here -- they left. */
export async function POST(request: NextRequest) {
  return guardedFormPost(request, "/bank/inventory", bagStatusSchema, async (data, user) => {
    const from =
      data.status === "available" ? ["discarded", "expired"] : ["available", "reserved"];
    const [updated] = await db
      .update(bloodBags)
      .set({ status: data.status, updatedAt: new Date() })
      .where(
        and(
          eq(bloodBags.id, data.bagId),
          inArray(bloodBags.status, from as ("available" | "reserved" | "discarded" | "expired")[])
        )
      )
      .returning({ id: bloodBags.id, bloodGroup: bloodBags.bloodGroup });

    if (!updated) {
      return "error=invalid";
    }
    await writeAuditLogSafe({
      actorType: "doctor",
      actorDoctorId: user.id,
      action: `bank.bag_${data.status}`,
      entityType: "blood_bag",
      entityId: updated.id,
      metadata: null,
    });
    return `notice=bag_updated&group=${encodeURIComponent(updated.bloodGroup)}`;
  });
}
