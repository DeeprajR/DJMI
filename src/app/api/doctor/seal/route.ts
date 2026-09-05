import { eq } from "drizzle-orm";
import { NextRequest, NextResponse } from "next/server";
import { db } from "@/db/client";
import { doctors } from "@/db/schema";
import { writeAuditLogSafe } from "@/lib/audit/log";
import { getAuthSession } from "@/lib/auth/session";
import { isTrustedPostOrigin } from "@/lib/security/csrf";
import { storeSealImage } from "@/lib/storage/seal";

function redirectWithError(request: NextRequest, code: string): NextResponse {
  return NextResponse.redirect(new URL(`/profile?error=${code}`, request.url), 303);
}

export async function POST(request: NextRequest) {
  if (!isTrustedPostOrigin(request)) {
    return redirectWithError(request, "invalid_origin");
  }

  const session = await getAuthSession();
  if (!session) {
    return NextResponse.redirect(new URL("/sign-in", request.url), 303);
  }

  const formData = await request.formData();
  const file = formData.get("seal");

  if (!(file instanceof File)) {
    return redirectWithError(request, "missing_file");
  }

  if (file.type !== "image/png") {
    return redirectWithError(request, "invalid_type");
  }

  const fileBuffer = Buffer.from(await file.arrayBuffer());

  try {
    const storedName = await storeSealImage(
      fileBuffer,
      session.doctor.id,
      session.doctor.doctorSealPath
    );

    await db
      .update(doctors)
      .set({
        doctorSealPath: storedName,
        updatedAt: new Date(),
      })
      .where(eq(doctors.id, session.doctor.id));

    await writeAuditLogSafe({
      actorType: "doctor",
      actorDoctorId: session.doctor.id,
      action: "doctor.seal_update",
      entityType: "doctor",
      entityId: session.doctor.id,
    });
  } catch {
    return redirectWithError(request, "upload_failed");
  }

  return NextResponse.redirect(new URL("/profile?updated=1", request.url), 303);
}
