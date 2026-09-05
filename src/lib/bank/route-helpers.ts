import "server-only";

import { NextRequest, NextResponse } from "next/server";
import type { ZodType } from "zod";
import { requireBankApi } from "@/lib/auth/bank-guard";
import type { AuthSession } from "@/lib/auth/session";
import { isTrustedPostOrigin } from "@/lib/security/csrf";

/**
 * The shape every blood-bank form POST shares: same-origin check, bank-role guard,
 * form parsing through a Zod schema, then a redirect back to the page with a status
 * code in the query string. Keeps each route handler to the part that differs.
 */
export async function guardedFormPost<T>(
  request: NextRequest,
  backTo: string,
  schema: ZodType<T>,
  handler: (data: T, user: AuthSession["doctor"]) => Promise<string>
): Promise<NextResponse> {
  const redirectTo = (query: string) =>
    NextResponse.redirect(new URL(`${backTo}?${query}`, request.url), 303);

  if (!isTrustedPostOrigin(request)) {
    return redirectTo("error=invalid_origin");
  }
  const guard = await requireBankApi();
  if (!guard.ok) {
    return guard.reason === "unauthenticated"
      ? NextResponse.redirect(new URL("/sign-in", request.url), 303)
      : NextResponse.redirect(new URL("/dashboard", request.url), 303);
  }

  const formData = await request.formData();
  const raw: Record<string, unknown> = {};
  formData.forEach((value, key) => {
    raw[key] = typeof value === "string" ? value : undefined;
  });
  const parsed = schema.safeParse(raw);
  if (!parsed.success) {
    return redirectTo("error=invalid");
  }

  const outcome = await handler(parsed.data, guard.user);
  return redirectTo(outcome);
}

export function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

export function addDaysIso(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}
