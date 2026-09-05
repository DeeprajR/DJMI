import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { db } from "@/db/client";
import { patients } from "@/db/schema";
import { writeAuditLogSafe } from "@/lib/audit/log";
import { getAuthSession } from "@/lib/auth/session";
import { isTrustedPostOrigin } from "@/lib/security/csrf";

const bloodGroups = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"] as const;
const ageUnits = ["days", "months", "years"] as const;

const createPatientSchema = z.object({
  patientName: z.string().trim().min(1).max(200),
  patientAge: z.coerce.number().int().min(0).max(130),
  patientAgeUnit: z.enum(ageUnits),
  patientBloodGroup: z.enum(bloodGroups),
});

function errorRedirect(request: NextRequest, code: string): NextResponse {
  return NextResponse.redirect(new URL(`/patients?error=${code}`, request.url), 303);
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
  const parsed = createPatientSchema.safeParse({
    patientName: formData.get("patientName"),
    patientAge: formData.get("patientAge"),
    patientAgeUnit: formData.get("patientAgeUnit"),
    patientBloodGroup: formData.get("patientBloodGroup"),
  });

  if (!parsed.success) {
    return errorRedirect(request, "invalid_patient");
  }

  const [created] = await db
    .insert(patients)
    .values({
      patientName: parsed.data.patientName,
      patientAge: parsed.data.patientAge,
      patientAgeUnit: parsed.data.patientAgeUnit,
      patientBloodGroup: parsed.data.patientBloodGroup,
    })
    .returning({ id: patients.id });

  await writeAuditLogSafe({
    actorType: "doctor",
    actorDoctorId: session.doctor.id,
    action: "patient.create",
    entityType: "patient",
    entityId: created.id,
    metadata: {
      patientBloodGroup: parsed.data.patientBloodGroup,
      patientAgeUnit: parsed.data.patientAgeUnit,
    },
  });

  return NextResponse.redirect(
    new URL(`/patients?created=1&patientId=${created.id}`, request.url),
    303
  );
}
