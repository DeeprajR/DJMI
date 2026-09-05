# Phase 2 — Authentication and session security

**Status:** Complete · 2026-09-06

## Goal

Provide backend-enforced authentication with no self-registration, and make the signed-in
account the only source of clinical identity.

## What was built

- **Password hashing:** Argon2id via `@node-rs/argon2` (memory cost 19456, time cost 2,
  parallelism 1)
- **Sessions:** opaque random token in a `br_session` cookie — `httpOnly`, `sameSite=lax`,
  `secure` in production. Only a SHA-256 hash of the token is stored in `sessions`, so a
  database leak does not yield usable session tokens.
- **Rate limiting:** persisted in `auth_rate_limits` for both IP and account scope, with
  windowed attempts and temporary blocks
- **Guards:** `requireDoctor()` and `requireAdmin()` for server components
- **Route protection:** `src/proxy.ts` (Next.js 16 replaces `middleware.ts` with `proxy.ts`)
- **Redirect safety:** `sanitizeNextPath()` rejects absolute and protocol-relative URLs to
  prevent open redirects after sign-in

## Files changed

`package.json`, `package-lock.json`, `README.md`, `src/proxy.ts`,
`src/app/sign-in/page.tsx`, `src/app/dashboard/page.tsx`,
`src/app/api/auth/sign-in/route.ts`, `src/app/api/auth/sign-out/route.ts`,
`src/lib/auth/constants.ts`, `src/lib/auth/password.ts`, `src/lib/auth/rate-limit.ts`,
`src/lib/auth/session.ts`, `src/lib/auth/guard.ts`, `src/db/schema/tables.ts`,
`drizzle/0001_new_stone_men.sql`, `drizzle/meta/0001_snapshot.json`,
`drizzle/meta/_journal.json`, `scripts/create-admin.ts`, `scripts/create-doctor.ts`

## Verification

`npm run db:generate`, `npm run lint`, `npm run typecheck`, `npm run build` passed.

## Notes

Runtime migration apply remained environment-dependent at this point; no accessible
PostgreSQL runtime existed in the session.

## Decisions

- **Opaque tokens over JWTs.** Sessions must be revocable server-side. A stolen JWT stays
  valid until expiry; a database row can be revoked immediately.
- **Rate limits in the database, not memory.** Survives restarts and works across
  instances.
- **`sameSite=lax`, not `strict`.** The app relies on top-level POST form navigations;
  `strict` would break the sign-in redirect flow. CSRF is covered separately by
  same-origin checks in Phase 10.
