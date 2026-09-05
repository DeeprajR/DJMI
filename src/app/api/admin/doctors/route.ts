import { NextRequest, NextResponse } from "next/server";
import { db } from "@/db/client";
import { doctors } from "@/db/schema";
import { writeAuditLogSafe } from "@/lib/audit/log";
import { requireAdminApi } from "@/lib/auth/admin-guard";
import { hashPassword } from "@/lib/auth/password";
import { createDoctorSchema } from "@/lib/admin/schema";
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
  const parsed = createDoctorSchema.safeParse({
    email: formData.get("email"),
    password: formData.get("password"),
    doctorName: formData.get("doctorName"),
    doctorProvisionalReg: formData.get("doctorProvisionalReg"),
    role: formData.get("role"),
  });

  if (!parsed.success) {
    return redirectTo(request, "error=invalid_account");
  }

  const passwordHash = await hashPassword(parsed.data.password);

  let createdId: string;
  try {
    const [created] = await db
      .insert(doctors)
      .values({
        email: parsed.data.email,
        passwordHash,
        role: parsed.data.role,
        doctorName: parsed.data.doctorName,
        doctorProvisionalReg: parsed.data.doctorProvisionalReg,
        isActive: true,
      })
      .returning({ id: doctors.id });
    createdId = created.id;
  } catch {
    return redirectTo(request, "error=duplicate_account");
  }

  await writeAuditLogSafe({
    actorType: "admin",
    actorDoctorId: guard.admin.id,
    action: "admin.account_create",
    entityType: "doctor",
    entityId: createdId,
    metadata: { email: parsed.data.email, role: parsed.data.role },
  });

  return redirectTo(request, "created=1");
}
