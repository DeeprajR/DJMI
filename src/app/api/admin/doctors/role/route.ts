import { and, eq, ne } from "drizzle-orm";
import { NextRequest, NextResponse } from "next/server";
import { db } from "@/db/client";
import { doctors } from "@/db/schema";
import { writeAuditLogSafe } from "@/lib/audit/log";
import { requireAdminApi } from "@/lib/auth/admin-guard";
import { updateRoleSchema } from "@/lib/admin/schema";
import { isTrustedPostOrigin } from "@/lib/security/csrf";

function redirectTo(request: NextRequest, query: string): NextResponse {
  return NextResponse.redirect(new URL(`/admin?${query}`, request.url), 303);
}

async function countOtherActiveAdmins(excludeDoctorId: string): Promise<number> {
  const rows = await db
    .select({ id: doctors.id })
    .from(doctors)
    .where(
      and(eq(doctors.role, "admin"), eq(doctors.isActive, true), ne(doctors.id, excludeDoctorId))
    );
  return rows.length;
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
  const parsed = updateRoleSchema.safeParse({
    doctorId: formData.get("doctorId"),
    role: formData.get("role"),
  });

  if (!parsed.success) {
    return redirectTo(request, "error=invalid_role");
  }

  if (parsed.data.doctorId === guard.admin.id) {
    return redirectTo(request, "error=self_role_change");
  }

  const target = await db.query.doctors.findFirst({
    where: eq(doctors.id, parsed.data.doctorId),
    columns: { id: true, role: true, email: true },
  });

  if (!target) {
    return redirectTo(request, "error=account_not_found");
  }

  if (target.role === "admin" && parsed.data.role !== "admin") {
    const remaining = await countOtherActiveAdmins(target.id);
    if (remaining === 0) {
      return redirectTo(request, "error=last_admin");
    }
  }

  await db
    .update(doctors)
    .set({ role: parsed.data.role, updatedAt: new Date() })
    .where(eq(doctors.id, target.id));

  await writeAuditLogSafe({
    actorType: "admin",
    actorDoctorId: guard.admin.id,
    action: "admin.role_update",
    entityType: "doctor",
    entityId: target.id,
    metadata: { email: target.email, from: target.role, to: parsed.data.role },
  });

  return redirectTo(request, "roleUpdated=1");
}
