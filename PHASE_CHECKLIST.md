# Blood Request PWA Phase Checklist

Use this file as the single source of truth for implementation progress.

## Status Key

- [ ] Not started
- [~] In progress
- [x] Completed
- [!] Blocked

## Phase Checklist

- [x] Phase 0 - Foundation scaffold and compliance baseline
  - Next.js TypeScript project scaffolded
  - PolyForm Noncommercial license added
  - Medical disclaimer added to app shell and README
  - Base scripts and checks wired (`lint`, `typecheck`, `build`)
- [x] Phase 1 - Database schema and migrations (PostgreSQL + Drizzle)
- [x] Phase 2 - Authentication and session security
- [x] Phase 3 - Doctor profile and seal upload/serve flow
- [x] Phase 4 - Patient and admission management
- [x] Phase 5 - Blood request draft creation and frozen form implementation
- [x] Phase 6 - Review, submit, and Request ID generation
- [x] Phase 7 - Request viewing and data-dense dashboard tables
- [x] Phase 8 - Blood sample association workflow
- [x] Phase 9 - PWA installability and app-shell caching
- [x] Phase 10 - Hardening, audit, and test coverage

## Module 2 - Blood Bank Dashboard

- [x] Repository layout reunified at the root (the dev branch was half-moved into `apps/hospital/` and did not build)
- [x] `blood_bank` role, `/bank` guard, navigation and role badge
- [x] Tables: `bank_settings`, `blood_bags`, `bank_decisions`, `donor_demand`, `donor_demand_confirmations` (`drizzle/0002_blood_bank.sql`)
- [x] Inventory by bag with RFID identity; reader endpoint `POST /api/bank/bags/scan`
- [x] Request queue with issue-from-stock decisions and donor demand for the shortfall
- [x] 25-unit floor per group with one-click restocking demand
- [x] Donor demand page: bot progress, confirmed-donor roster, counter marks
- [x] Doctor's request view shows the bank's decision
- [ ] First run against PostgreSQL (migration apply, seed, walkthrough) - blocked on database credentials

See [context/module-2-blood-bank.md](context/module-2-blood-bank.md).

## Design System Rollout

- [x] Apply supplied design system to all frontend screens
  - Shared tokens, typography, light/dark surfaces, accessible controls
  - Responsive navigation, forms, tables, request workflow and PWA presentation
  - Preserve clinical labels, authentication, and form submissions
  - Verify quality checks and responsive browser rendering

### Design Rollout Log

- 2026-09-06: Frontend design-system rollout completed.
  - Changed: all existing page components; shared shell, global styles and design tokens; root font/viewport metadata; loading, error and not-found screens; PWA icons, manifest, registration and shell cache; design and worker regression tests; isolated synthetic preview script; README and checklist.
  - Preserved: clinical form wording, read-only identity fields, API form contracts, authentication and draft/submitted workflows.
  - Browser verification: 24 authenticated route/viewport combinations (320/768/1440px), eight public screen/theme combinations, keyboard skip/focus, reduced motion, and draft → submit → sample association using only synthetic data.
  - Quality verification: 12 tests passed; lint, TypeScript, production build, and whitespace checks passed.
  - PWA verification: cache inspection found no clinical/API/sign-in entries; offline logic covered by worker tests. Native installation and real-device offline testing remain outside this verification.

## Update Rule (Apply on Every Phase Completion)

1. Mark the phase checkbox from [ ] to [x].
2. Add one entry to the Phase Update Log below.
3. List changed files and verification results.
4. Note assumptions, blockers, or unresolved issues.

## Phase Update Log

- 2026-09-06: Phase 0 marked complete.
  - Changed files: `.gitignore`, `README.md`, `package.json`, `src/app/globals.css`, `src/app/layout.tsx`, `src/app/page.tsx`, `.env.example`, `LICENSE`
  - Verification: `npm run lint`, `npm run typecheck`, `npm run build` passed
  - Notes: Initial scaffold had naming conflict due to workspace folder name; resolved by scaffolding in subfolder and moving to root
- 2026-09-06: Phase 1 marked complete.
  - Changed files: `package.json`, `README.md`, `.env.example`, `drizzle.config.ts`, `docker-compose.yml`, `src/db/client.ts`, `src/db/schema/enums.ts`, `src/db/schema/tables.ts`, `src/db/schema/index.ts`, `drizzle/0000_sleepy_living_mummy.sql`, `drizzle/meta/0000_snapshot.json`, `drizzle/meta/_journal.json`, `scripts/create-admin.ts`, `scripts/create-doctor.ts`
  - Verification: `npm run db:generate`, `npm run lint`, `npm run typecheck`, `npm run build` passed
  - Notes: `npm run db:migrate` could not be executed in this environment because PostgreSQL runtime access is unavailable (`docker` socket denied and local PostgreSQL binaries absent)
- 2026-09-06: Phase 2 marked complete.
  - Changed files: `package.json`, `package-lock.json`, `README.md`, `src/proxy.ts`, `src/app/sign-in/page.tsx`, `src/app/dashboard/page.tsx`, `src/app/api/auth/sign-in/route.ts`, `src/app/api/auth/sign-out/route.ts`, `src/lib/auth/constants.ts`, `src/lib/auth/password.ts`, `src/lib/auth/rate-limit.ts`, `src/lib/auth/session.ts`, `src/lib/auth/guard.ts`, `src/db/schema/tables.ts`, `drizzle/0001_new_stone_men.sql`, `drizzle/meta/0001_snapshot.json`, `drizzle/meta/_journal.json`, `scripts/create-admin.ts`, `scripts/create-doctor.ts`
  - Verification: `npm run db:generate`, `npm run lint`, `npm run typecheck`, `npm run build` passed
  - Notes: authentication routes and dashboard are implemented; runtime DB migration apply remains environment-dependent because no accessible PostgreSQL runtime is available in this session
- 2026-09-06: Phase 3 marked complete.
  - Changed files: `README.md`, `PHASE_CHECKLIST.md`, `src/proxy.ts`, `src/app/dashboard/page.tsx`, `src/app/profile/page.tsx`, `src/app/api/doctor/seal/route.ts`, `src/app/api/seal/[doctorId]/route.ts`, `src/lib/storage/seal.ts`, `package-lock.json`
  - Verification: `npm run lint`, `npm run typecheck`, `npm run build` passed
  - Notes: seal upload/serve is backend-enforced; route handlers require authenticated session and profile identity remains account-managed
- 2026-09-06: Phase 4 marked complete.
  - Changed files: `README.md`, `PHASE_CHECKLIST.md`, `src/proxy.ts`, `src/app/dashboard/page.tsx`, `src/app/patients/page.tsx`, `src/app/admissions/page.tsx`, `src/app/api/patients/route.ts`, `src/app/api/admissions/route.ts`
  - Verification: `npm run lint`, `npm run typecheck`, `npm run build` passed
  - Notes: patient/admission create and search are authenticated and server-validated; admission creation enforces patient existence and unique IP No.
- 2026-09-06: Phase 5 marked complete.
  - Changed files: `README.md`, `PHASE_CHECKLIST.md`, `src/proxy.ts`, `src/app/admissions/page.tsx`, `src/app/requests/new/page.tsx`, `src/app/requests/[id]/page.tsx`, `src/app/api/requests/drafts/route.ts`, `src/app/api/requests/drafts/[id]/route.ts`, `src/lib/blood-request/draft.ts`, `src/lib/blood-request/context.ts`
  - Verification: `npm run lint`, `npm run typecheck`, `npm run build` passed
  - Notes: frozen blood request form labels are preserved; doctor identity and admission context are enforced server-side for draft create/update.
- 2026-09-06: Phase 6 marked complete.
  - Changed files: `README.md`, `PHASE_CHECKLIST.md`, `src/app/requests/[id]/page.tsx`, `src/app/requests/[id]/review/page.tsx`, `src/app/api/requests/drafts/[id]/route.ts`, `src/app/api/requests/submit/[id]/route.ts`, `src/lib/blood-request/request-id.ts`
  - Verification: `npm run lint`, `npm run typecheck`, `npm run build` passed
  - Notes: submit flow now performs atomic status transition and request ID generation; non-draft updates are redirected to review and treated as immutable.
- 2026-09-06: Migration runtime caveat resolved.
  - Changed files: `.gitignore`, `package.json`, `package-lock.json`, `scripts/apply-migrations-local.ts`, `README.md`, `PHASE_CHECKLIST.md`
  - Verification: `npm run db:migrate:local` applied migrations successfully using embedded PostgreSQL and listed public schema tables
  - Notes: local migration apply no longer depends on Docker socket or system PostgreSQL binaries.
- 2026-09-06: Phase 7 marked complete.
  - Changed files: `README.md`, `PHASE_CHECKLIST.md`, `src/app/dashboard/page.tsx`, `src/app/requests/[id]/review/page.tsx`, `src/app/requests/[id]/view/page.tsx`
  - Verification: `npm run lint`, `npm run typecheck`, `npm run build` passed
  - Notes: dashboard now renders live request metrics and recent requests table; submitted requests have dedicated read-only view route.
- 2026-09-06: Phase 8 marked complete.
  - Changed files: `README.md`, `PHASE_CHECKLIST.md`, `src/app/api/requests/[id]/samples/route.ts`, `src/app/requests/[id]/view/page.tsx`
  - Verification: `npm run lint`, `npm run typecheck`, `npm run build` passed
  - Notes: sample association is enforced server-side and limited to submitted requests; request view now includes sample add form and sample history table.
- 2026-09-06: Phase 9 marked complete.
  - Changed files: `README.md`, `PHASE_CHECKLIST.md`, `next.config.ts`, `src/app/layout.tsx`, `src/app/manifest.ts`, `src/app/offline/page.tsx`, `src/components/pwa-register.tsx`, `public/sw.js`, `src/app/icons/icon-192/route.ts`, `src/app/icons/icon-512/route.ts`, `src/app/icons/icon-512-maskable/route.ts`
  - Verification: `npm run lint`, `npm run typecheck`, `npm run build` passed
  - Notes: app is installable with manifest + service worker, while API and clinical data routes remain network-only to avoid stale/offline data mutation risks.
- 2026-09-06: Phase 10 marked complete.
  - Changed files: `README.md`, `PHASE_CHECKLIST.md`, `package.json`, `src/lib/security/csrf.ts`, `src/lib/security/csrf.test.ts`, `src/lib/auth/redirect.ts`, `src/lib/auth/redirect.test.ts`, `src/lib/audit/log.ts`, `src/app/api/auth/sign-in/route.ts`, `src/app/api/auth/sign-out/route.ts`, `src/app/api/patients/route.ts`, `src/app/api/admissions/route.ts`, `src/app/api/doctor/seal/route.ts`, `src/app/api/requests/drafts/route.ts`, `src/app/api/requests/drafts/[id]/route.ts`, `src/app/api/requests/submit/[id]/route.ts`, `src/app/api/requests/[id]/samples/route.ts`
  - Verification: `npm run test`, `npm run lint`, `npm run typecheck`, `npm run build` passed
  - Notes: CSRF same-origin checks are now enforced for POST mutations, and high-value workflow events are written to audit log with best-effort non-blocking semantics.
