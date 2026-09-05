import "server-only";

import { getAuthSession, type AuthSession } from "./session";

export type AdminApiGuardResult =
  | { ok: true; admin: AuthSession["doctor"] }
  | { ok: false; reason: "unauthenticated" | "forbidden" };

/** Route-handler equivalent of requireAdmin(); returns a result instead of redirecting. */
export async function requireAdminApi(): Promise<AdminApiGuardResult> {
  const session = await getAuthSession();
  if (!session) {
    return { ok: false, reason: "unauthenticated" };
  }
  if (session.doctor.role !== "admin") {
    return { ok: false, reason: "forbidden" };
  }
  return { ok: true, admin: session.doctor };
}
