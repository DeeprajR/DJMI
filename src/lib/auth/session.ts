import "server-only";

import { createHash, randomBytes } from "node:crypto";
import { and, eq, gt, isNull } from "drizzle-orm";
import { cookies } from "next/headers";
import { db } from "@/db/client";
import { doctors, sessions } from "@/db/schema";
import { SESSION_COOKIE_NAME, SESSION_TTL_SECONDS } from "./constants";

type SessionDoctor = Pick<
  typeof doctors.$inferSelect,
  "id" | "role" | "email" | "doctorName" | "doctorProvisionalReg" | "doctorSealPath" | "isActive"
>;

export type AuthSession = {
  id: string;
  doctor: SessionDoctor;
};

function readSessionSecret(): string {
  const secret = process.env.SESSION_SECRET;
  if (!secret || secret.length < 32) {
    throw new Error("SESSION_SECRET must be set and at least 32 characters long.");
  }
  return secret;
}

function hashSessionToken(token: string): string {
  return createHash("sha256").update(`${token}:${readSessionSecret()}`).digest("hex");
}

export async function createSession(doctorId: string): Promise<void> {
  const token = randomBytes(32).toString("base64url");
  const tokenHash = hashSessionToken(token);
  const expiresAt = new Date(Date.now() + SESSION_TTL_SECONDS * 1000);

  await db.insert(sessions).values({
    doctorId,
    tokenHash,
    expiresAt,
  });

  const cookieStore = await cookies();
  cookieStore.set({
    name: SESSION_COOKIE_NAME,
    value: token,
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: SESSION_TTL_SECONDS,
  });
}

export async function getAuthSession(): Promise<AuthSession | null> {
  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE_NAME)?.value;
  if (!token) {
    return null;
  }

  const tokenHash = hashSessionToken(token);
  const now = new Date();

  const session = await db.query.sessions.findFirst({
    where: and(
      eq(sessions.tokenHash, tokenHash),
      gt(sessions.expiresAt, now),
      isNull(sessions.revokedAt)
    ),
    with: {
      doctor: true,
    },
  });

  if (!session || !session.doctor.isActive) {
    return null;
  }

  return {
    id: session.id,
    doctor: {
      id: session.doctor.id,
      role: session.doctor.role,
      email: session.doctor.email,
      doctorName: session.doctor.doctorName,
      doctorProvisionalReg: session.doctor.doctorProvisionalReg,
      doctorSealPath: session.doctor.doctorSealPath,
      isActive: session.doctor.isActive,
    },
  };
}

export async function revokeCurrentSession(): Promise<void> {
  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE_NAME)?.value;
  cookieStore.delete(SESSION_COOKIE_NAME);

  if (!token) {
    return;
  }

  const now = new Date();
  await db
    .update(sessions)
    .set({ revokedAt: now })
    .where(eq(sessions.tokenHash, hashSessionToken(token)));
}
