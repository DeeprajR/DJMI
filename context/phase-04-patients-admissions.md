# Phase 4 — Patient and admission management

**Status:** Complete · 2026-09-06

## Goal

Give clinicians a way to record and find patients and admissions in-app, since there is no
HIS integration.

## What was built

- `/patients` — create and search patients by name and blood group
- `/admissions` — create and search admissions, entry point to a new blood request
- `POST /api/patients` and `POST /api/admissions`, both authenticated and Zod-validated

Server-side rules:

- Admission creation verifies the referenced patient exists before insert
- `ip_no` uniqueness is enforced by the primary key; a duplicate returns
  `error=duplicate_ip` rather than a stack trace
- Age is stored as a number plus a unit (`days` / `months` / `years`), not derived from a
  date of birth

## Files changed

`README.md`, `PHASE_CHECKLIST.md`, `src/proxy.ts`, `src/app/dashboard/page.tsx`,
`src/app/patients/page.tsx`, `src/app/admissions/page.tsx`,
`src/app/api/patients/route.ts`, `src/app/api/admissions/route.ts`

## Verification

`npm run lint`, `npm run typecheck`, `npm run build` passed.

## Decisions

- **App-owned patient tables, no HIS integration.** Keeps the MVP self-contained; an
  integration can later populate the same tables.
- **Age as a number with a unit.** Neonatal and paediatric records need days and months.
  A date of birth would force a precision the source data often lacks.
- **Errors surface as redirect query codes.** Keeps the forms plain HTML POSTs that work
  without JavaScript, matching the app-shell-only PWA posture.
