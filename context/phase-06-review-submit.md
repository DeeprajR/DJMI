# Phase 6 — Review, submit, and Request ID generation

**Status:** Complete · 2026-09-06

## Goal

Turn a draft into an immutable clinical record with a unique, human-readable identifier,
without race conditions under concurrent submits.

## What was built

- `/requests/:id/review` — read-only summary before commitment
- `POST /api/requests/submit/:id` — owner-only submit

Submit performs, inside a single transaction:

1. Re-read the row `FOR` the `draft` status — a second submit finds nothing and aborts
2. Allocate the next Request ID via an atomic upsert on `blood_request_counters`
3. Write snapshots, set `status = 'submitted'` and `submitted_at`

The counter allocation is a single statement, so concurrent submits serialise:

```sql
INSERT INTO blood_request_counters (request_year, current_value, updated_at)
VALUES ($year, 1, $now)
ON CONFLICT (request_year)
DO UPDATE SET current_value = blood_request_counters.current_value + 1
RETURNING current_value;
```

**Request ID format:** `BR-YYYY-NNNNNN` — for example `BR-2026-000001`.

Completeness is validated before submit: reason, date needed, blood group, product, and a
positive unit count must all be present.

## Immutability

After submit, the draft update endpoint refuses the write and redirects to the review
page with `error=already_submitted`. The database constraint
`blood_requests_submitted_consistency` independently guarantees a submitted row always
carries both a Request ID and a submit timestamp.

## Files changed

`README.md`, `PHASE_CHECKLIST.md`, `src/app/requests/[id]/page.tsx`,
`src/app/requests/[id]/review/page.tsx`, `src/app/api/requests/drafts/[id]/route.ts`,
`src/app/api/requests/submit/[id]/route.ts`, `src/lib/blood-request/request-id.ts`

## Verification

`npm run lint`, `npm run typecheck`, `npm run build` passed. Later verified end-to-end in a
browser against synthetic data: draft → review → submit produced `BR-2026-000001`.

## Decisions

- **ID assigned at submit, not creation.** Abandoned drafts would otherwise burn
  identifiers and leave gaps in a clinical numbering sequence.
- **Atomic upsert over read-then-write.** Two doctors submitting simultaneously must never
  receive the same Request ID.
- **Immutability enforced in two places.** Application logic can be bypassed by a future
  code path; the check constraint cannot.
