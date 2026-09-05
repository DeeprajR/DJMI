import { eq } from "drizzle-orm";
import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { db } from "@/db/client";
import { admissions, patients } from "@/db/schema";
import { writeAuditLogSafe } from "@/lib/audit/log";
import { getAuthSession } from "@/lib/auth/session";
import { isTrustedPostOrigin } from "@/lib/security/csrf";

const createAdmissionSchema = z.object({
  ipNo: z.string().trim().min(1).max(64),
  patientId: z.string().uuid(),
  wardNo: z.string().trim().min(1).max(64),
});

function errorRedirect(request: NextRequest, code: string): NextResponse {
  return NextResponse.redirect(new URL(`/admissions?error=${code}`, request.url), 303);
}

export async function POST(request: NextRequest) {
  if (!isTrustedPostOrigin(request)) {
    return errorRedirect(request, "invalid_origin");
  }

  const session = await getAuthSession();
  if (!session) {
    return NextResponse.redirect(new URL("/sign-in", request.url), 303);
  }

  const formData = await request.formData();
  const parsed = createAdmissionSchema.safeParse({
    ipNo: formData.get("ipNo"),
    patientId: formData.get("patientId"),
    wardNo: formData.get("wardNo"),
  });

  if (!parsed.success) {
    return errorRedirect(request, "invalid_admission");
  }

  const existingPatient = await db.query.patients.findFirst({
    where: eq(patients.id, parsed.data.patientId),
    columns: { id: true },
  });
  if (!existingPatient) {
    return errorRedirect(request, "patient_not_found");
  }

  try {
    await db.insert(admissions).values({
      ipNo: parsed.data.ipNo,
      patientId: parsed.data.patientId,
      wardNo: parsed.data.wardNo,
      admissionStatus: "active",
    });
  } catch {
    return errorRedirect(request, "duplicate_ip");
  }

  await writeAuditLogSafe({
    actorType: "doctor",
    actorDoctorId: session.doctor.id,
    action: "admission.create",
    entityType: "admission",
    entityId: parsed.data.ipNo,
    metadata: {
      patientId: parsed.data.patientId,
      wardNo: parsed.data.wardNo,
    },
  });

  return NextResponse.redirect(new URL(`/admissions?created=1&ipNo=${encodeURIComponent(parsed.data.ipNo)}`, request.url), 303);
}
