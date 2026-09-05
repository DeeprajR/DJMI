import "server-only";

import { redirect } from "next/navigation";
import { getAuthSession, type AuthSession } from "./session";
import { getRequiredSession } from "./guard";

/**
 * Blood bank staff. Admins are allowed through as well so a single-person deployment
 * does not need two accounts; doctors are not, because the bank decides on their
 * requests and must not be able to approve their own.
 */
export function isBankRole(role: string): boolean {
  return role === "blood_bank" || role === "admin";
}

export async function requireBank() {
  const session = await getRequiredSession();
  if (!isBankRole(session.doctor.role)) {
    redirect("/dashboard");
  }
  return session.doctor;
}

export type BankApiGuardResult =
  | { ok: true; user: AuthSession["doctor"] }
  | { ok: false; reason: "unauthenticated" | "forbidden" };

/** Route-handler counterpart of requireBank(); returns a result instead of redirecting. */
export async function requireBankApi(): Promise<BankApiGuardResult> {
  const session = await getAuthSession();
  if (!session) {
    return { ok: false, reason: "unauthenticated" };
  }
  if (!isBankRole(session.doctor.role)) {
    return { ok: false, reason: "forbidden" };
  }
  return { ok: true, user: session.doctor };
}
