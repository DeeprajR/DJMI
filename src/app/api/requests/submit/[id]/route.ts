import { and, eq } from "drizzle-orm";
import { NextRequest, NextResponse } from "next/server";
import { db } from "@/db/client";
import { bloodRequests } from "@/db/schema";
import { writeAuditLogSafe } from "@/lib/audit/log";
import { getAuthSession } from "@/lib/auth/session";
import { getAdmissionContext } from "@/lib/blood-request/context";
import { allocateBloodRequestId } from "@/lib/blood-request/request-id";
import { isTrustedPostOrigin } from "@/lib/security/csrf";

type RouteParams = {
  params: Promise<{
    id: string;
  }>;
};

function isDraftComplete(
  draft: Pick<
    typeof bloodRequests.$inferSelect,
    "reasonForTransfusion" | "dateNeeded" | "requestedBloodGroup" | "product" | "units"
  >
): boolean {
  return !!(
    draft.reasonForTransfusion &&
    draft.dateNeeded &&
    draft.requestedBloodGroup &&
    draft.product &&
    draft.units &&
    draft.units > 0
  );
}

export async function POST(request: NextRequest, { params }: RouteParams) {
  if (!isTrustedPostOrigin(request)) {
    const { id } = await params;
    return NextResponse.redirect(new URL(`/requests/${id}/review?error=invalid_origin`, request.url), 303);
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
      reasonForTransfusion: true,
      dateNeeded: true,
      requestedBloodGroup: true,
      product: true,
      units: true,
    },
  });

  if (!existing) {
    return NextResponse.redirect(new URL("/dashboard", request.url), 303);
  }

  if (existing.doctorId !== session.doctor.id) {
    return NextResponse.redirect(new URL("/dashboard", request.url), 303);
  }

  if (existing.status !== "draft") {
    return NextResponse.redirect(new URL(`/requests/${existing.id}/review?error=already_submitted`, request.url), 303);
  }

  if (!isDraftComplete(existing)) {
    return NextResponse.redirect(new URL(`/requests/${existing.id}/review?error=incomplete`, request.url), 303);
  }

  const admission = await getAdmissionContext(existing.ipNo);
  if (!admission) {
    return NextResponse.redirect(new URL(`/requests/${existing.id}/review?error=admission_not_found`, request.url), 303);
  }

  const now = new Date();
  let submittedRequestId: string | null = null;

  try {
    await db.transaction(async (tx) => {
      const freshDraft = await tx.query.bloodRequests.findFirst({
        where: and(eq(bloodRequests.id, existing.id), eq(bloodRequests.status, "draft")),
        columns: {
          id: true,
        },
      });

      if (!freshDraft) {
        throw new Error("Draft no longer available for submission.");
      }

      const requestId = await allocateBloodRequestId(tx, now);
      submittedRequestId = requestId;

      await tx
        .update(bloodRequests)
        .set({
          requestId,
          status: "submitted",
          submittedAt: now,
          patientNameSnapshot: admission.patient.patientName,
          patientAgeSnapshot: admission.patient.patientAge,
          patientAgeUnitSnapshot: admission.patient.patientAgeUnit,
          patientBloodGroupSnapshot: admission.patient.patientBloodGroup,
          wardNoSnapshot: admission.wardNo,
          doctorNameSnapshot: session.doctor.doctorName,
          doctorProvisionalRegSnapshot: session.doctor.doctorProvisionalReg,
          doctorSealPathSnapshot: session.doctor.doctorSealPath,
          updatedAt: now,
        })
        .where(and(eq(bloodRequests.id, existing.id), eq(bloodRequests.status, "draft")));
    });
  } catch {
    return NextResponse.redirect(new URL(`/requests/${existing.id}/review?error=submit_failed`, request.url), 303);
  }

  await writeAuditLogSafe({
    actorType: "doctor",
    actorDoctorId: session.doctor.id,
    action: "blood_request.submit",
    entityType: "blood_request",
    entityId: existing.id,
    metadata: {
      requestId: submittedRequestId,
      ipNo: existing.ipNo,
    },
  });

  return NextResponse.redirect(new URL(`/requests/${existing.id}/review?submitted=1`, request.url), 303);
}
