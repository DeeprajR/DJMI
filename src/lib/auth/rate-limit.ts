import "server-only";

import { and, eq } from "drizzle-orm";
import { db } from "@/db/client";
import { authRateLimits } from "@/db/schema";
import {
  LOGIN_BLOCK_MS,
  LOGIN_IP_ATTEMPT_LIMIT,
  LOGIN_IP_WINDOW_MS,
  LOGIN_ACCOUNT_ATTEMPT_LIMIT,
  LOGIN_ACCOUNT_WINDOW_MS,
} from "./constants";

type RateLimitScope = "login_ip" | "login_account";

type RateLimitConfig = {
  windowMs: number;
  maxAttempts: number;
  blockMs: number;
};

const RATE_LIMIT_CONFIG: Record<RateLimitScope, RateLimitConfig> = {
  login_ip: {
    windowMs: LOGIN_IP_WINDOW_MS,
    maxAttempts: LOGIN_IP_ATTEMPT_LIMIT,
    blockMs: LOGIN_BLOCK_MS,
  },
  login_account: {
    windowMs: LOGIN_ACCOUNT_WINDOW_MS,
    maxAttempts: LOGIN_ACCOUNT_ATTEMPT_LIMIT,
    blockMs: LOGIN_BLOCK_MS,
  },
};

export class LoginRateLimitError extends Error {
  constructor(public readonly retryAfterSeconds: number) {
    super("Too many login attempts.");
  }
}

async function consumeLimit(scope: RateLimitScope, key: string): Promise<void> {
  const normalizedKey = key.trim().toLowerCase();
  const cfg = RATE_LIMIT_CONFIG[scope];
  const now = new Date();

  const existing = await db.query.authRateLimits.findFirst({
    where: and(eq(authRateLimits.scope, scope), eq(authRateLimits.key, normalizedKey)),
  });

  if (!existing) {
    await db.insert(authRateLimits).values({
      scope,
      key: normalizedKey,
      attempts: 1,
      windowStartedAt: now,
      blockedUntil: null,
      updatedAt: now,
    });
    return;
  }

  if (existing.blockedUntil && existing.blockedUntil > now) {
    const retryAfter = Math.ceil(
      (existing.blockedUntil.getTime() - now.getTime()) / 1000
    );
    throw new LoginRateLimitError(retryAfter);
  }

  const windowAgeMs = now.getTime() - existing.windowStartedAt.getTime();
  if (windowAgeMs > cfg.windowMs) {
    await db
      .update(authRateLimits)
      .set({
        attempts: 1,
        windowStartedAt: now,
        blockedUntil: null,
        updatedAt: now,
      })
      .where(
        and(eq(authRateLimits.scope, scope), eq(authRateLimits.key, normalizedKey))
      );
    return;
  }

  const nextAttempt = existing.attempts + 1;
  const shouldBlock = nextAttempt > cfg.maxAttempts;
  const blockedUntil = shouldBlock ? new Date(now.getTime() + cfg.blockMs) : null;

  await db
    .update(authRateLimits)
    .set({
      attempts: nextAttempt,
      blockedUntil,
      updatedAt: now,
    })
    .where(and(eq(authRateLimits.scope, scope), eq(authRateLimits.key, normalizedKey)));

  if (shouldBlock && blockedUntil) {
    const retryAfter = Math.ceil((blockedUntil.getTime() - now.getTime()) / 1000);
    throw new LoginRateLimitError(retryAfter);
  }
}

export async function assertLoginAttemptAllowed(
  ipAddress: string,
  accountEmail: string
): Promise<void> {
  await consumeLimit("login_ip", ipAddress || "unknown");
  await consumeLimit("login_account", accountEmail || "unknown");
}

export async function clearLoginRateLimit(
  ipAddress: string,
  accountEmail: string
): Promise<void> {
  const now = new Date();
  const ip = (ipAddress || "unknown").trim().toLowerCase();
  const email = (accountEmail || "unknown").trim().toLowerCase();

  await db
    .update(authRateLimits)
    .set({ attempts: 0, blockedUntil: null, windowStartedAt: now, updatedAt: now })
    .where(and(eq(authRateLimits.scope, "login_ip"), eq(authRateLimits.key, ip)));

  await db
    .update(authRateLimits)
    .set({ attempts: 0, blockedUntil: null, windowStartedAt: now, updatedAt: now })
    .where(and(eq(authRateLimits.scope, "login_account"), eq(authRateLimits.key, email)));
}
