# Phase 3 — Doctor profile and seal upload

**Status:** Complete · 2026-09-06

## Goal

Let a doctor upload the seal image that appears on their blood requests, without exposing
it to unauthenticated users or allowing arbitrary file writes.

## What was built

- Profile page at `/profile` showing account-controlled identity fields as read-only
- Upload endpoint `POST /api/doctor/seal`
- Authenticated fetch endpoint `GET /api/seal/:doctorId` (self or admin only)

Upload hardening in `src/lib/storage/seal.ts`:

| Control | Implementation |
|---|---|
| Type check | PNG magic-byte signature verified, not just the MIME header |
| Size limit | 1 MB maximum |
| Re-encode | Image is decoded and re-encoded through `sharp`, stripping any embedded payload |
| Filename | Server-generated `<doctorId>-<uuid>.png`; user input never reaches the path |
| Path safety | Stored filenames validated against `^[a-zA-Z0-9._-]+\.png$` |
| Location | `SEAL_STORAGE_DIR`, outside the webroot — never statically served |
| Permissions | Written with mode `0600` |
| Cleanup | Previous seal file removed on replacement |

## Files changed

`README.md`, `PHASE_CHECKLIST.md`, `src/proxy.ts`, `src/app/dashboard/page.tsx`,
`src/app/profile/page.tsx`, `src/app/api/doctor/seal/route.ts`,
`src/app/api/seal/[doctorId]/route.ts`, `src/lib/storage/seal.ts`, `package-lock.json`

## Verification

`npm run lint`, `npm run typecheck`, `npm run build` passed.

## Decisions

- **Re-encode rather than trust the upload.** A file can be a valid PNG and still carry a
  polyglot payload. Re-encoding through `sharp` produces a known-clean image.
- **Serve through a route handler, not `public/`.** A seal is part of a clinical record;
  it requires an authenticated request and an ownership check.
- **Identity fields are read-only in the UI.** Doctor name and provisional registration
  are account-managed, so a doctor cannot self-attribute a request to another clinician.
