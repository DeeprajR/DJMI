import { NextRequest, NextResponse } from "next/server";
import { db } from "@/db/client";
import { bloodRequests } from "@/db/schema";
import { writeAuditLogSafe } from "@/lib/audit/log";
import { getAuthSession } from "@/lib/auth/session";
import { getAdmissionContext } from "@/lib/blood-request/context";
import { draftRequestSchema } from "@/lib/blood-request/draft";
import { isTrustedPostOrigin } from "@/lib/security/csrf";

function toFormPayload(formData: FormData) {
  return {
    ipNo: formData.get("ipNo"),
    reasonForTransfusion: formData.get("reasonForTransfusion"),
    dateNeeded: formData.get("dateNeeded"),
    requestedBloodGroup: formData.get("requestedBloodGroup"),
    product: formData.get("product"),
    units: formData.get("units"),
  };
}

export async function POST(request: NextRequest) {
  if (!isTrustedPostOrigin(request)) {
    return NextResponse.redirect(new URL("/requests/new?error=invalid_origin", request.url), 303);
  }

  const session = await getAuthSession();
  if (!session) {
    return NextResponse.redirect(new URL("/sign-in", request.url), 303);
  }

  const formData = await request.formData();
  const rawIpNo = String(formData.get("ipNo") ?? "").trim();
  const parsed = draftRequestSchema.safeParse(toFormPayload(formData));
  if (!parsed.success) {
    return NextResponse.redirect(
      new URL(`/requests/new?ipNo=${encodeURIComponent(rawIpNo)}&error=invalid`, request.url),
      303
    );
  }

  const admission = await getAdmissionContext(parsed.data.ipNo);
  if (!admission) {
    return NextResponse.redirect(new URL(`/requests/new?ipNo=${encodeURIComponent(parsed.data.ipNo)}&error=admission_not_found`, request.url), 303);
  }

  const [draft] = await db
    .insert(bloodRequests)
    .values({
      ipNo: admission.ipNo,
      reasonForTransfusion: parsed.data.reasonForTransfusion,
      dateNeeded: parsed.data.dateNeeded,
      requestedBloodGroup: parsed.data.requestedBloodGroup,
      product: parsed.data.product,
      units: parsed.data.units,
      doctorId: session.doctor.id,
      patientNameSnapshot: admission.patient.patientName,
      patientAgeSnapshot: admission.patient.patientAge,
      patientAgeUnitSnapshot: admission.patient.patientAgeUnit,
      patientBloodGroupSnapshot: admission.patient.patientBloodGroup,
      wardNoSnapshot: admission.wardNo,
      doctorNameSnapshot: session.doctor.doctorName,
      doctorProvisionalRegSnapshot: session.doctor.doctorProvisionalReg,
      doctorSealPathSnapshot: session.doctor.doctorSealPath,
      status: "draft",
    })
    .returning({ id: bloodRequests.id });

  await writeAuditLogSafe({
    actorType: "doctor",
    actorDoctorId: session.doctor.id,
    action: "blood_request.draft_create",
    entityType: "blood_request",
    entityId: draft.id,
    metadata: {
      ipNo: admission.ipNo,
      product: parsed.data.product,
      units: parsed.data.units,
    },
  });

  return NextResponse.redirect(new URL(`/requests/${draft.id}?saved=1`, request.url), 303);
}
