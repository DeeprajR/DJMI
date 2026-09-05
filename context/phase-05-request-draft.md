# Phase 5 — Blood request draft and frozen form

**Status:** Complete · 2026-09-06

## Goal

Reproduce the paper blood request form exactly, while sourcing every field the doctor
must not control from the server.

## Frozen form contract

These labels are reproduced **verbatim** and must not be renamed, reordered, merged, or
split. A regression test asserts their presence.

| Form label | Source | Column |
|---|---|---|
| Name of Patient: | patients | `patient_name` |
| Age of Patient: | patients | `patient_age` + `patient_age_unit` |
| Blood Group of Patient: | patients | `patient_blood_group` |
| IP No. of Patient: | admissions (PK) | `ip_no` |
| Ward No.: | admissions | `ward_no` |
| Reason for transfusion: | doctor input | `reason_for_transfusion` |
| Date Needed: | doctor input | `date_needed` |
| Blood Group: | doctor input | `requested_blood_group` |
| Request: Whole Blood, Packed RBC, Platelet, Fresh Frozen Plasma, Cryopresipitate | doctor input | `product` |
| No. of Units: | doctor input | `units` |
| Doctor name: | authenticated account | `doctor_name_snapshot` |
| Doctor Provisional Reg.: | authenticated account | `doctor_provisional_reg_snapshot` |
| Doctor Seal: | authenticated account | `doctor_seal_path_snapshot` |

Product enum values, including the original spelling: `whole_blood`, `packed_rbc`,
`platelet`, `fresh_frozen_plasma`, `cryopresipitate`.

## What was built

- `/requests/new?ipNo=<admission_ip_no>` — new draft, admission context locked
- `/requests/:id` — edit an existing draft
- `POST /api/requests/drafts` and `POST /api/requests/drafts/:id` (owner-only)

Patient, admission, and doctor fields render as read-only inputs and are re-resolved
server-side on every write, so tampering with the posted form cannot change them.

## Files changed

`README.md`, `PHASE_CHECKLIST.md`, `src/proxy.ts`, `src/app/admissions/page.tsx`,
`src/app/requests/new/page.tsx`, `src/app/requests/[id]/page.tsx`,
`src/app/api/requests/drafts/route.ts`, `src/app/api/requests/drafts/[id]/route.ts`,
`src/lib/blood-request/draft.ts`, `src/lib/blood-request/context.ts`

## Verification

`npm run lint`, `npm run typecheck`, `npm run build` passed.

## Decisions

- **Two distinct blood group fields.** `Blood Group of Patient` is the patient's own ABO/Rh;
  `Blood Group` is the group of the product being requested. They are stored separately and
  a mismatch is never silently blocked — that is a clinical judgement, not a code rule.
- **One product per request.** Multiple products means multiple requests, matching the
  paper form rather than inventing a line-item model.
- **Read-only inputs are cosmetic; the server is authoritative.** Disabled fields in HTML
  are trivially bypassed, so identity is always re-read from the session.
