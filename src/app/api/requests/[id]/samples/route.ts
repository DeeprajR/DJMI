import { and, eq } from "drizzle-orm";
import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { db } from "@/db/client";
import { bloodRequests, bloodSamples } from "@/db/schema";
import { writeAuditLogSafe } from "@/lib/audit/log";
import { getAuthSession } from "@/lib/auth/session";
import { isTrustedPostOrigin } from "@/lib/security/csrf";

type RouteParams = {
  params: Promise<{
    id: string;
  }>;
};

const createSampleSchema = z.object({
  sampleIdentifier: z.string().trim().min(1).max(120),
  collectedAt: z.string().trim().min(1),
});

function parseCollectedAt(input: string): Date | null {
  const normalized = input.includes("T") ? input : `${input}T00:00`;
  const parsed = new Date(normalized);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  return parsed;
}

function redirectToView(request: NextRequest, requestId: string, query: string): NextResponse {
  return NextResponse.redirect(new URL(`/requests/${requestId}/view?${query}`, request.url), 303);
}

export async function POST(request: NextRequest, context: RouteParams) {
  if (!isTrustedPostOrigin(request)) {
    const { id } = await context.params;
    return redirectToView(request, id, "error=invalid_origin");
  }

  const session = await getAuthSession();
  if (!session) {
    return NextResponse.redirect(new URL("/sign-in", request.url), 303);
  }

  const { id } = await context.params;

  const targetRequest = await db.query.bloodRequests.findFirst({
    where: and(eq(bloodRequests.id, id), eq(bloodRequests.doctorId, session.doctor.id)),
    columns: {
      id: true,
      status: true,
    },
  });

  if (!targetRequest) {
    return NextResponse.redirect(new URL("/dashboard", request.url), 303);
  }

  if (targetRequest.status !== "submitted") {
    return redirectToView(request, targetRequest.id, "error=requires_submitted");
  }

  const formData = await request.formData();
  const parsed = createSampleSchema.safeParse({
    sampleIdentifier: formData.get("sampleIdentifier"),
    collectedAt: formData.get("collectedAt"),
  });

  if (!parsed.success) {
    return redirectToView(request, targetRequest.id, "error=invalid_sample");
  }

  const collectedAt = parseCollectedAt(parsed.data.collectedAt);
  if (!collectedAt) {
    return redirectToView(request, targetRequest.id, "error=invalid_collected_at");
  }

  try {
    await db.insert(bloodSamples).values({
      bloodRequestId: targetRequest.id,
      sampleIdentifier: parsed.data.sampleIdentifier,
      collectedAt,
      collectedByDoctorId: session.doctor.id,
    });
  } catch {
    return redirectToView(request, targetRequest.id, "error=duplicate_sample");
  }

  await writeAuditLogSafe({
    actorType: "doctor",
    actorDoctorId: session.doctor.id,
    action: "blood_sample.add",
    entityType: "blood_request",
    entityId: targetRequest.id,
    metadata: {
      sampleIdentifier: parsed.data.sampleIdentifier,
      collectedAt: collectedAt.toISOString(),
    },
  });

  return redirectToView(request, targetRequest.id, "sampleAdded=1");
}
