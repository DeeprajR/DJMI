import { eq } from "drizzle-orm";
import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { db } from "@/db/client";
import { doctors } from "@/db/schema";
import {
  LoginRateLimitError,
  assertLoginAttemptAllowed,
  clearLoginRateLimit,
} from "@/lib/auth/rate-limit";
import { verifyPassword } from "@/lib/auth/password";
import { sanitizeNextPath } from "@/lib/auth/redirect";
import { createSession } from "@/lib/auth/session";
import { writeAuditLogSafe } from "@/lib/audit/log";
import { isTrustedPostOrigin } from "@/lib/security/csrf";

const signInSchema = z.object({
  email: z.string().trim().email().max(320),
  password: z.string().min(1).max(200),
  next: z.string().optional(),
});

function getClientIp(request: NextRequest): string {
  const xff = request.headers.get("x-forwarded-for");
  if (!xff) {
    return "unknown";
  }
  return xff.split(",")[0]?.trim() || "unknown";
}

export async function POST(request: NextRequest) {
  if (!isTrustedPostOrigin(request)) {
    return NextResponse.redirect(new URL("/sign-in?error=invalid_origin", request.url), 303);
  }

  const formData = await request.formData();
  const parsed = signInSchema.safeParse({
    email: formData.get("email"),
    password: formData.get("password"),
    next: formData.get("next") ?? undefined,
  });

  const fallbackRedirect = new URL("/sign-in?error=invalid", request.url);
  if (!parsed.success) {
    return NextResponse.redirect(fallbackRedirect, 303);
  }

  const email = parsed.data.email.toLowerCase();
  const nextPath = sanitizeNextPath(parsed.data.next);
  const ipAddress = getClientIp(request);

  try {
    await assertLoginAttemptAllowed(ipAddress, email);
  } catch (error) {
    if (error instanceof LoginRateLimitError) {
      await writeAuditLogSafe({
        actorType: "system",
        action: "auth.login_rate_limited",
        entityType: "auth",
        entityId: email,
        metadata: {
          ipAddress,
          retryAfterSeconds: error.retryAfterSeconds,
        },
      });

      const blocked = new URL(
        `/sign-in?error=rate_limited&retry_after=${error.retryAfterSeconds}`,
        request.url
      );
      return NextResponse.redirect(blocked, 303);
    }
    throw error;
  }

  const doctor = await db.query.doctors.findFirst({
    where: eq(doctors.email, email),
  });

  const isValid =
    !!doctor &&
    doctor.isActive &&
    (await verifyPassword(parsed.data.password, doctor.passwordHash));

  if (!isValid) {
    await writeAuditLogSafe({
      actorType: "system",
      action: "auth.login_failed",
      entityType: "auth",
      entityId: email,
      metadata: {
        ipAddress,
      },
    });

    const invalid = new URL("/sign-in?error=invalid", request.url);
    return NextResponse.redirect(invalid, 303);
  }

  await clearLoginRateLimit(ipAddress, email);
  await createSession(doctor.id);
  await writeAuditLogSafe({
    actorType: "doctor",
    actorDoctorId: doctor.id,
    action: "auth.login_success",
    entityType: "doctor",
    entityId: doctor.id,
    metadata: {
      ipAddress,
    },
  });

  return NextResponse.redirect(new URL(nextPath, request.url), 303);
}
