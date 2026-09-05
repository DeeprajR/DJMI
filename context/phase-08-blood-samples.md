# Phase 8 — Blood sample association

**Status:** Complete · 2026-09-06

## Goal

Record the physical blood samples collected against a submitted request, closing the
workflow loop.

## What was built

- `POST /api/requests/:id/samples`
- Add-sample form and sample history table on `/requests/:id/view`

Captured per sample: `sampleIdentifier`, `collectedAt`, and `collectedByDoctorId` taken
from the authenticated session.

Rules enforced server-side:

| Rule | Behaviour |
|---|---|
| Request must be `submitted` | Drafts return `error=requires_submitted` |
| Ownership | The query filters on `doctor_id`, so a non-owner sees a redirect to the dashboard |
| Unique identifier | `blood_samples_identifier_uq`; a collision returns `error=duplicate_sample` |
| Valid timestamp | Unparseable input returns `error=invalid_collected_at` |

Multiple samples per request are supported.

## Files changed

`README.md`, `PHASE_CHECKLIST.md`, `src/app/api/requests/[id]/samples/route.ts`,
`src/app/requests/[id]/view/page.tsx`

## Verification

`npm run lint`, `npm run typecheck`, `npm run build` passed. Later verified in a browser:
associating `UI-VERIFIED-001` against a submitted request appeared in the history table.

## Decisions

- **Samples only after submit.** A sample is drawn against an authorised request; allowing
  it on a draft would let an unauthorised request drive physical collection.
- **Globally unique sample identifiers.** Sample IDs are matched against physical tubes in
  the lab, so uniqueness must hold across all requests, not just within one.
- **Collector taken from the session.** Chain of custody must reflect who was
  authenticated, not who was typed into a form.
