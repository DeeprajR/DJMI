# Phase 10 — Hardening, audit, and test coverage

**Status:** Complete · 2026-09-06

## Goal

Close the remaining gaps before the app could be considered evaluation-ready: CSRF,
audit trail, and automated tests for security-critical logic.

## What was built

### CSRF protection

`src/lib/security/csrf.ts` — `isTrustedPostOrigin()` validates the `Origin` header against
the request host and protocol, honouring `x-forwarded-host` / `x-forwarded-proto` for
proxied deployments. A missing or mismatched origin is rejected.

Applied to **every** mutating route: sign-in, sign-out, patients, admissions, seal upload,
draft create/update, submit, and sample association.

### Audit logging

`src/lib/audit/log.ts` — `writeAuditLog()` and `writeAuditLogSafe()`. The `Safe` variant
swallows failures deliberately: an audit write must never block a clinical action.

Events recorded: login success, login failure, login rate-limit, logout, patient create,
admission create, seal update, draft create, draft update, submit, sample association.

### Tests

`npm run test` using the built-in `node:test` runner — no new dependency.

| Test | Covers |
|---|---|
| `isTrustedPostOrigin` accepts same-origin | CSRF happy path |
| rejects host mismatch | Cross-site POST |
| rejects missing origin | Stripped-header attack |
| respects forwarded headers | Proxy deployment |
| `sanitizeNextPath` defaults | Open-redirect guard |
| rejects absolute / protocol-relative | `//evil.site`, `https://evil.site` |
| accepts local paths | Normal navigation |

## Files changed

`README.md`, `PHASE_CHECKLIST.md`, `package.json`, `src/lib/security/csrf.ts`,
`src/lib/security/csrf.test.ts`, `src/lib/auth/redirect.ts`,
`src/lib/auth/redirect.test.ts`, `src/lib/audit/log.ts`,
`src/app/api/auth/sign-in/route.ts`, `src/app/api/auth/sign-out/route.ts`,
`src/app/api/patients/route.ts`, `src/app/api/admissions/route.ts`,
`src/app/api/doctor/seal/route.ts`, `src/app/api/requests/drafts/route.ts`,
`src/app/api/requests/drafts/[id]/route.ts`, `src/app/api/requests/submit/[id]/route.ts`,
`src/app/api/requests/[id]/samples/route.ts`

## Verification

`npm run test`, `npm run lint`, `npm run typecheck`, `npm run build` all passed.

## Related: migration runtime resolved

The Phase 1 blocker — no way to apply migrations without Docker or system PostgreSQL — was
resolved by `scripts/apply-migrations-local.ts`, which runs a rootless embedded PostgreSQL
instance. Exposed as `npm run db:migrate:local`.

Files: `.gitignore`, `package.json`, `package-lock.json`,
`scripts/apply-migrations-local.ts`, `README.md`, `PHASE_CHECKLIST.md`

## Decisions

- **Origin-header CSRF over token CSRF.** The forms are plain HTML POSTs with no client
  JavaScript. Origin validation adds no client complexity and no token storage.
- **Best-effort audit writes.** A failed audit insert must not prevent a doctor from
  submitting a blood request. Availability wins; the failure mode is a missing log line,
  not a blocked clinical action.
- **`node:test` over Vitest or Jest.** The suite covers pure functions. A test framework
  would add dependency weight for no gain here.
