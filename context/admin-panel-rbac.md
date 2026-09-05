# Admin panel and RBAC

**Status:** Complete · 2026-09-06

## Goal

Let an admin provision doctor accounts and manage role-based access, without weakening any
existing guarantee.

## Roles

| Role | Access |
|---|---|
| `doctor` | Patients, admissions, blood requests, samples, own profile |
| `admin` | Everything a doctor can do, plus account administration |

## What was built

- `/admin` — create accounts, list all accounts, change roles, activate/deactivate
- `POST /api/admin/doctors` — create a doctor or admin account
- `POST /api/admin/doctors/role` — change a role
- `POST /api/admin/doctors/status` — activate or deactivate
- `src/lib/auth/admin-guard.ts` — `requireAdminApi()`, the route-handler counterpart to
  `requireAdmin()`; returns a result instead of redirecting
- `src/lib/admin/schema.ts` — Zod schemas and user-facing messages

## Layered enforcement

Authorisation is checked at three independent levels, so no single mistake grants access:

1. `src/proxy.ts` blocks unauthenticated requests to `/admin`
2. The page calls `requireAdmin()`, redirecting non-admins to the dashboard
3. **Every** POST handler independently re-checks the admin role, in addition to the
   existing same-origin CSRF check

## Safeguards

| Rule | Reason |
|---|---|
| Cannot change your own role | Prevents accidental self-lockout |
| Cannot deactivate yourself | Same |
| Last active admin cannot be demoted or deactivated | Guarantees at least one admin always remains |
| Password minimum 12 characters | Stronger than the legacy seed-script default |
| Duplicate email or provisional registration rejected | Enforced by unique indexes |

Every admin action writes to `audit_log`: `admin.account_create`, `admin.role_update`,
`admin.account_activate`, `admin.account_deactivate`.

## Files changed

**Added:** `src/app/admin/page.tsx`, `src/app/api/admin/doctors/route.ts`,
`src/app/api/admin/doctors/role/route.ts`, `src/app/api/admin/doctors/status/route.ts`,
`src/lib/auth/admin-guard.ts`, `src/lib/admin/schema.ts`

**Modified:** `src/proxy.ts`, `src/app/dashboard/page.tsx`,
`src/components/app-shell.tsx`, `package.json`

## Verification

Tested against the running application:

| Test | Result |
|---|---|
| Anonymous → `/admin` | Redirected to sign-in |
| Doctor → `/admin` | Redirected; zero account data in the response body |
| Doctor → role-change API | Blocked |
| POST without valid origin | Rejected as `invalid_origin` |
| Admin creates account | Succeeded |
| Duplicate email / registration | Rejected |
| Password under 12 characters | Rejected |
| Admin changes own role | Blocked |
| Role change and deactivation | Succeeded and audited |

Lint, typecheck, all tests, and the production build passed.

## Notes

The dashboard shortcut to the admin panel was later removed at the user's request. The
route remains reachable directly at `/admin` for admins; RBAC enforcement is unchanged.

The seed scripts previously crashed with a `server-only` import error when run under plain
Node. Fixed by running them with `tsx --conditions=react-server`.

**Known rough edge:** `npm run seed:doctor` resets an existing account's role to `doctor`,
so using it to change an admin's password also demotes them.
