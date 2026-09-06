import { NextRequest } from "next/server";
import { and, eq } from "drizzle-orm";
import { db } from "@/db/client";
import { donorDemandConfirmations } from "@/db/schema";
import { writeAuditLogSafe } from "@/lib/audit/log";
import { guardedFormPost } from "@/lib/bank/route-helpers";
import { markConfirmationSchema } from "@/lib/bank/schema";

/**
 * The counter's mark on a confirmed donor: donated / no-show / cancelled. The bot
 * picks the change up on its next tick, updates the donor's cooldown and thanks them.
 * Only a `confirmed` row can be marked, so a double-click cannot flip a completed one.
 */
export async function POST(request: NextRequest) {
  return guardedFormPost(request, "/bank/demand", markConfirmationSchema, async (data, user) => {
    const donatedAt =
      data.status === "completed" ? data.donatedAt || new Date().toISOString().slice(0, 10) : null;

    const [updated] = await db
      .update(donorDemandConfirmations)
      .set({
        status: data.status,
        donatedAt,
        bagRfidTag: data.status === "completed" && data.bagRfidTag ? data.bagRfidTag : null,
        markedBy: user.id,
        updatedAt: new Date(),
      })
      .where(
        and(
          eq(donorDemandConfirmations.id, data.confirmationId),
          eq(donorDemandConfirmations.status, "confirmed")
        )
      )
      .returning({ id: donorDemandConfirmations.id, demandId: donorDemandConfirmations.demandId });

    if (!updated) {
      return "error=invalid";
    }
    await writeAuditLogSafe({
      actorType: "doctor",
      actorDoctorId: user.id,
      action: `bank.donor_${data.status}`,
      entityType: "donor_demand_confirmation",
      entityId: updated.id,
      metadata: { demandId: updated.demandId, donatedAt, bagRfidTag: data.bagRfidTag || null },
    });
    return "notice=marked";
  });
}
