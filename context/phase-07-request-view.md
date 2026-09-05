# Phase 7 — Request viewing and dashboard tables

**Status:** Complete · 2026-09-06

## Goal

Give a doctor a live picture of their workload and a permanent read-only view of any
submitted request.

## What was built

- `/requests/:id/view` — read-only record showing every frozen field, status, Request ID,
  and the doctor's seal
- Dashboard rebuilt around live data for the signed-in doctor

Dashboard metrics:

| Metric | Query |
|---|---|
| Active admissions | Count of admissions with `admission_status = 'active'` |
| My draft requests | Doctor's requests with `status = 'draft'` |
| Submitted today | Doctor's requests submitted since local midnight |
| Samples pending | Submitted requests with no associated `blood_samples` row |

The recent-requests table lists the doctor's 20 most recently updated requests, with a
status pill and a context-appropriate action — **Open draft** for drafts, **View request**
for submitted records.

## Files changed

`README.md`, `PHASE_CHECKLIST.md`, `src/app/dashboard/page.tsx`,
`src/app/requests/[id]/review/page.tsx`, `src/app/requests/[id]/view/page.tsx`

## Verification

`npm run lint`, `npm run typecheck`, `npm run build` passed.

## Decisions

- **Scope metrics to the signed-in doctor.** A dashboard is a personal work queue; a
  department-wide view is a different feature with different access implications.
- **"Samples pending" uses `NOT EXISTS`.** Cheaper and clearer than a left join with a
  null filter, and it expresses the intent directly.
- **Separate view route from the review route.** Review is a pre-submit decision point;
  view is the permanent record. Merging them would blur an immutability boundary.
