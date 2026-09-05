import { NextResponse } from "next/server";
import { revokeCurrentSession, getAuthSession } from "@/lib/auth/session";
import { writeAuditLogSafe } from "@/lib/audit/log";
import { isTrustedPostOrigin } from "@/lib/security/csrf";

export async function POST(request: Request) {
  if (!isTrustedPostOrigin(request)) {
    return NextResponse.redirect(new URL("/sign-in?error=invalid_origin", request.url), 303);
  }

  const session = await getAuthSession();
  await revokeCurrentSession();

  if (session) {
    await writeAuditLogSafe({
      actorType: "doctor",
      actorDoctorId: session.doctor.id,
      action: "auth.logout",
      entityType: "doctor",
      entityId: session.doctor.id,
    });
  }

  return NextResponse.redirect(new URL("/sign-in", request.url), 303);
}
