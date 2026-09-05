# Phase 1 — Database schema and migrations

**Status:** Complete · 2026-09-06

## Goal

Model the full clinical domain in PostgreSQL with Drizzle, with constraints that make
invalid states unrepresentable at the database level.

## What was built

Nine tables: `doctors`, `sessions`, `auth_rate_limits`, `patients`, `admissions`,
`blood_requests`, `blood_samples`, `blood_request_counters`, `audit_log`.

Key modelling decisions:

- `admissions.ip_no` is the **primary key** — admission identity is the IP No. itself
- `blood_requests.id` is a UUID; `request_id` (`BR-YYYY-NNNNNN`) is nullable and only
  assigned at submit time, with a partial unique index
- Snapshot columns on `blood_requests` freeze patient and doctor details at submit time,
  so later edits to a patient record cannot rewrite history
- Enum types for blood group, product, request status, age unit, admission status,
  user role, and audit actor type

Database-level constraints:

| Constraint | Guarantee |
|---|---|
| `blood_requests_submitted_consistency` | A `submitted` row must have both `request_id` and `submitted_at` |
| `blood_requests_units_positive` | Units are `NULL` or `> 0` |
| `patients_age_non_negative` | Age cannot be negative |
| `blood_samples_identifier_uq` | Sample identifiers are globally unique |
| `auth_rate_limits_scope_check` | Scope is `login_ip` or `login_account` |

## Files changed

`package.json`, `README.md`, `.env.example`, `drizzle.config.ts`, `docker-compose.yml`,
`src/db/client.ts`, `src/db/schema/enums.ts`, `src/db/schema/tables.ts`,
`src/db/schema/index.ts`, `drizzle/0000_sleepy_living_mummy.sql`,
`drizzle/meta/0000_snapshot.json`, `drizzle/meta/_journal.json`,
`scripts/create-admin.ts`, `scripts/create-doctor.ts`

## Verification

`npm run db:generate`, `npm run lint`, `npm run typecheck`, `npm run build` passed.

## Notes

`npm run db:migrate` could not run at the time: the Docker socket was permission-denied
and no local PostgreSQL binaries were installed. Migrations were generated and reviewed
but not applied. Resolved later — see [phase-10-hardening.md](phase-10-hardening.md) and
the embedded-Postgres runner note below.

## Decisions

- **Snapshot columns over joins for submitted requests.** A submitted request is a
  clinical record. It must not change because someone later corrected a patient's age.
- **Counter table over a sequence.** `blood_request_counters` allows a per-year counter
  reset with transactional allocation, which a global sequence cannot express.
