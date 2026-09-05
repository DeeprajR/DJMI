import { and, eq, ne } from "drizzle-orm";
import { NextRequest, NextResponse } from "next/server";
import { db } from "@/db/client";
import { doctors } from "@/db/schema";
import { writeAuditLogSafe } from "@/lib/audit/log";
import { requireAdminApi } from "@/lib/auth/admin-guard";
import { updateStatusSchema } from "@/lib/admin/schema";
import { isTrustedPostOrigin } from "@/lib/security/csrf";

function redirectTo(request: NextRequest, query: string): NextResponse {
  return NextResponse.redirect(new URL(`/admin?${query}`, request.url), 303);
}

export async function POST(request: NextRequest) {
  if (!isTrustedPostOrigin(request)) {
    return redirectTo(request, "error=invalid_origin");
  }

  const guard = await requireAdminApi();
  if (!guard.ok) {
    const target = guard.reason === "unauthenticated" ? "/sign-in" : "/dashboard";
    return NextResponse.redirect(new URL(target, request.url), 303);
  }

  const formData = await request.formData();
  const parsed = updateStatusSchema.safeParse({
    doctorId: formData.get("doctorId"),
    isActive: formData.get("isActive"),
  });

  if (!parsed.success) {
    return redirectTo(request, "error=invalid_status");
  }

  if (parsed.data.doctorId === guard.admin.id) {
    return redirectTo(request, "error=self_deactivate");
  }

  const target = await db.query.doctors.findFirst({
    where: eq(doctors.id, parsed.data.doctorId),
    columns: { id: true, role: true, email: true, isActive: true },
  });

  if (!target) {
    return redirectTo(request, "error=account_not_found");
  }

  if (target.role === "admin" && !parsed.data.isActive) {
    const remaining = await db
      .select({ id: doctors.id })
      .from(doctors)
      .where(
        and(eq(doctors.role, "admin"), eq(doctors.isActive, true), ne(doctors.id, target.id))
      );
    if (remaining.length === 0) {
      return redirectTo(request, "error=last_admin");
    }
  }

  await db
    .update(doctors)
    .set({ isActive: parsed.data.isActive, updatedAt: new Date() })
    .where(eq(doctors.id, target.id));

  await writeAuditLogSafe({
    actorType: "admin",
    actorDoctorId: guard.admin.id,
    action: parsed.data.isActive ? "admin.account_activate" : "admin.account_deactivate",
    entityType: "doctor",
    entityId: target.id,
    metadata: { email: target.email },
  });

  return redirectTo(request, "statusUpdated=1");
}
