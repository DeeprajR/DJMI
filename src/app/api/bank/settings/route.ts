import { NextRequest } from "next/server";
import { db } from "@/db/client";
import { bankSettings } from "@/db/schema";
import { writeAuditLogSafe } from "@/lib/audit/log";
import { guardedFormPost } from "@/lib/bank/route-helpers";
import { settingsSchema } from "@/lib/bank/schema";

export async function POST(request: NextRequest) {
  return guardedFormPost(request, "/bank/settings", settingsSchema, async (data, user) => {
    await db
      .insert(bankSettings)
      .values({ id: 1, ...data, updatedBy: user.id, updatedAt: new Date() })
      .onConflictDoUpdate({
        target: bankSettings.id,
        set: { ...data, updatedBy: user.id, updatedAt: new Date() },
      });

    await writeAuditLogSafe({
      actorType: "doctor",
      actorDoctorId: user.id,
      action: "bank.settings_update",
      entityType: "bank_settings",
      entityId: "1",
      metadata: { district: data.district, minUnitsPerGroup: data.minUnitsPerGroup },
    });
    return "notice=settings_saved";
  });
}
