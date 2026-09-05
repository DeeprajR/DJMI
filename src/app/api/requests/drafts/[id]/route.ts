import { and, eq } from "drizzle-orm";
import { NextRequest, NextResponse } from "next/server";
import { db } from "@/db/client";
import { bloodRequests } from "@/db/schema";
import { writeAuditLogSafe } from "@/lib/audit/log";
import { getAuthSession } from "@/lib/auth/session";
import { getAdmissionContext } from "@/lib/blood-request/context";
import { draftRequestSchema } from "@/lib/blood-request/draft";
import { isTrustedPostOrigin } from "@/lib/security/csrf";

type RouteParams = {
  params: Promise<{
    id: string;
  }>;
};

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

export async function POST(request: NextRequest, { params }: RouteParams) {
  if (!isTrustedPostOrigin(request)) {
    const { id } = await params;
    return NextResponse.redirect(new URL(`/requests/${id}?error=invalid_origin`, request.url), 303);
  }

  const session = await getAuthSession();
  if (!session) {
    return NextResponse.redirect(new URL("/sign-in", request.url), 303);
  }

  const { id } = await params;
  const existing = await db.query.bloodRequests.findFirst({
    where: eq(bloodRequests.id, id),
    columns: {
      id: true,
      ipNo: true,
      doctorId: true,
      status: true,
    },
  });

  if (!existing) {
    return NextResponse.redirect(new URL("/dashboard", request.url), 303);
  }

  const canEdit = session.doctor.role === "admin" || existing.doctorId === session.doctor.id;
  if (!canEdit || existing.status !== "draft") {
    return NextResponse.redirect(
      new URL(`/requests/${existing.id}/review?error=already_submitted`, request.url),
      303
    );
  }

  if (existing.doctorId !== session.doctor.id) {
    return NextResponse.redirect(new URL("/dashboard", request.url), 303);
  }

  const formData = await request.formData();
  const payload = toFormPayload(formData);
  const parsed = draftRequestSchema.safeParse({
    ...payload,
    ipNo: existing.ipNo,
  });
  if (!parsed.success) {
    return NextResponse.redirect(new URL(`/requests/${existing.id}?error=invalid`, request.url), 303);
  }

  const admission = await getAdmissionContext(existing.ipNo);
  if (!admission) {
    return NextResponse.redirect(new URL(`/requests/${existing.id}?error=admission_not_found`, request.url), 303);
  }

  await db
    .update(bloodRequests)
    .set({
      ipNo: admission.ipNo,
      reasonForTransfusion: parsed.data.reasonForTransfusion,
      dateNeeded: parsed.data.dateNeeded,
      requestedBloodGroup: parsed.data.requestedBloodGroup,
      product: parsed.data.product,
      units: parsed.data.units,
      patientNameSnapshot: admission.patient.patientName,
      patientAgeSnapshot: admission.patient.patientAge,
      patientAgeUnitSnapshot: admission.patient.patientAgeUnit,
      patientBloodGroupSnapshot: admission.patient.patientBloodGroup,
      wardNoSnapshot: admission.wardNo,
      doctorNameSnapshot: session.doctor.doctorName,
      doctorProvisionalRegSnapshot: session.doctor.doctorProvisionalReg,
      doctorSealPathSnapshot: session.doctor.doctorSealPath,
      updatedAt: new Date(),
    })
    .where(and(eq(bloodRequests.id, existing.id), eq(bloodRequests.status, "draft")));

  await writeAuditLogSafe({
    actorType: "doctor",
    actorDoctorId: session.doctor.id,
    action: "blood_request.draft_update",
    entityType: "blood_request",
    entityId: existing.id,
    metadata: {
      ipNo: existing.ipNo,
      product: parsed.data.product,
      units: parsed.data.units,
    },
  });

  return NextResponse.redirect(new URL(`/requests/${existing.id}?saved=1`, request.url), 303);
}
