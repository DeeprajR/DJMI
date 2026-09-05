# Blood Request PWA

TypeScript-first Progressive Web App for digitizing a blood request form workflow in an India-focused medical-college hospital context.

Current phase: Phase 10 complete (hardening, audit, and tests).

## Tech Stack

- Next.js App Router (TypeScript)
- Node.js runtime
- PostgreSQL planned for persisted workflow data

## MVP Workflow (Target)

Doctor
-> Authentication
-> Dashboard
-> Identify Admission/Patient
-> Create Blood Request
-> Complete Blood Request Form
-> Review
-> Submit
-> Generate Blood Request ID
-> View Request
-> Associate Blood Sample

## Development

Install dependencies and run local dev server:

```bash
npm install
npm run dev
```

Validation commands:

```bash
npm run lint
npm run typecheck
npm run build
```

## Database (Phase 1)

Create PostgreSQL and set `DATABASE_URL` in `.env` (see `.env.example`), then:

```bash
docker compose up -d postgres
npm run db:generate
npm run db:migrate
```

If Docker or system PostgreSQL is unavailable, run migrations with embedded PostgreSQL:

```bash
npm run db:migrate:local
```

Useful commands:

```bash
npm run db:studio
npm run db:push
```

Admin and doctor accounts are provisioned by seed scripts (implemented in later phases):

```bash
npm run seed:admin
npm run seed:doctor
```

## Authentication (Phase 2)

- Backend-issued session cookie: `httpOnly`, `sameSite=lax`, `secure` in production.
- Session tokens are stored as SHA-256 hashes in `sessions`.
- Doctor identity fields used by blood requests must always come from authenticated account data.
- Login throttling is enforced in database table `auth_rate_limits` for both IP and account scope.

Provision accounts:

```bash
npm run seed:admin
npm run seed:doctor -- --email doctor@example.com --password change-me --name "Dr Test" --provisional-reg "KL-12345"
```

## Doctor Seal (Phase 3)

- Profile page: `/profile`
- Upload endpoint: `POST /api/doctor/seal` (authenticated)
- Seal fetch endpoint: `GET /api/seal/:doctorId` (authenticated, self or admin)
- Accepted file type: PNG only
- Max upload size: 1MB
- Uploaded image is re-encoded as PNG before storing
- Storage location: `SEAL_STORAGE_DIR` outside webroot

## Patient and Admission Management (Phase 4)

- Patients page: `/patients`
- Admissions page: `/admissions`
- Create patient endpoint: `POST /api/patients` (authenticated)
- Create admission endpoint: `POST /api/admissions` (authenticated)
- Admission creation validates patient existence and keeps `ip_no` as admission identity.

## Blood Request Draft Form (Phase 5)

- New draft page: `/requests/new?ipNo=<admission_ip_no>`
- Draft edit page: `/requests/:id`
- Create draft endpoint: `POST /api/requests/drafts` (authenticated)
- Update draft endpoint: `POST /api/requests/drafts/:id` (authenticated, owner-only)
- Frozen form labels are implemented verbatim.
- Patient/admission context is resolved from `ipNo` admission selection.
- Doctor identity fields are read-only and sourced from authenticated account data on the backend.

## Review and Submit (Phase 6)

- Review page: `/requests/:id/review`
- Submit endpoint: `POST /api/requests/submit/:id` (authenticated, owner-only)
- Submit transitions request status from `draft` to `submitted`
- Request ID is generated at submit time in format `BR-YYYY-NNNNNN`
- ID allocation uses transactional counter updates in `blood_request_counters`
- Submitted requests are immutable through draft update endpoints

## Request Viewing and Dashboard Tables (Phase 7)

- Request view page: `/requests/:id/view`
- Dashboard now includes live metrics and recent request table for the signed-in doctor.
- Request table supports direct actions to open draft or view submitted request.
- Submitted requests show generated Request ID and immutable status state.

## Blood Sample Association (Phase 8)

- Sample association endpoint: `POST /api/requests/:id/samples`
- Samples can be associated only for submitted requests.
- Sample fields captured: `sampleIdentifier`, `collectedAt`, and authenticated `collectedByDoctorId`.
- Request view page (`/requests/:id/view`) shows add-sample form and sample history table.

## PWA Installability and App-Shell Caching (Phase 9)

- Web app manifest route: `/manifest.webmanifest`
- Service worker script: `/sw.js`
- Offline fallback page: `/offline`
- Install icons are served from app routes:
	- `/icons/icon-192`
	- `/icons/icon-512`
	- `/icons/icon-512-maskable`
- Caching model is intentionally conservative:
	- App shell/navigation fallback is available offline.
	- Data routes are network-only (`/api/*`, and authenticated clinical workflow pages).
	- Offline API calls return `503` with explicit connectivity-required messaging.

This preserves installability without allowing stale or offline clinical data operations.

## Hardening, Audit, and Test Coverage (Phase 10)

- CSRF protection for mutating endpoints now validates same-origin POSTs via `Origin` + host/proto checks.
- Mutating workflows now emit audit events to `audit_log` (best-effort, non-blocking):
	- auth login success/failure/rate-limit and logout
	- patient/admission creation
	- seal update
	- blood request draft create/update and submit
	- blood sample association
- Added unit tests for critical security/path-safety helpers:
	- `sanitizeNextPath` redirect safety
	- `isTrustedPostOrigin` same-origin validation logic

Run test + quality checks:

```bash
npm run test
npm run lint
npm run typecheck
npm run build
```

## Frontend Design System

The frontend follows [design-system-blood-app.md](design-system-blood-app.md).

- Shared tokens and components: [src/app/design-system.css](src/app/design-system.css) and [src/components/app-shell.tsx](src/components/app-shell.tsx).
- Self-hosted Bricolage Grotesque headings, IBM Plex Sans UI text, and Noto Sans Malayalam fallback. Tabular numbers throughout.
- System-selected light/dark themes, blue keyboard focus, 48px minimum controls, and 52px inputs.
- Mobile bottom navigation, a 72px tablet rail, and a 240px desktop sidebar; safe-area padding supports standalone mode.
- Single-column forms, readable scrollable tables, blood-group chips, and explicit draft/review/submitted progress. Clinical form wording and backend contracts are preserved.
- Neutral offline messaging; amber validation errors; one filled primary action per screen. No invented urgency or additional user-role workflows.
- Loading, error, not-found, sign-in, and public landing screens share the same system. Print styles remove navigation and forms.
- The refreshed service-worker cache allowlists public shell/static assets; authenticated documents, API responses, and RSC payloads remain network-only.

### Design verification

- 24 authenticated screen/viewport checks across 320px, 768px, and 1440px, using synthetic records: no page overflow, undersized controls, or duplicate primary actions.
- Landing, sign-in error, offline, and not-found screens checked at 320px in light and dark modes.
- Keyboard skip link, blue focus, reduced-motion styles, and a complete draft → review → submit → sample association workflow verified in the browser.
- Unit tests cover contrast pairs, control dimensions, page landmarks, frozen form wording, and service-worker offline/cache behavior.
- Native installation and real-device offline emulation were not tested; the integrated browser did not support network emulation.

An optional isolated preview is available through [scripts/preview-design.ts](scripts/preview-design.ts). After building, run `npx tsx scripts/preview-design.ts`. It uses loopback ports 3100/55433, a disposable database, and synthetic fixtures only. It never uses your configured clinical database. Stop it with Ctrl-C. Do not deploy this test-only script.

## License

This project is licensed under PolyForm Noncommercial License 1.0.0.
See `LICENSE`.

## Medical Disclaimer

This software is provided AS IS.

- It is not medical advice.
- It is not a substitute for clinical judgment.
- It is not automatically clinically validated.
- It must not be used in a real clinical environment without appropriate validation, security review, compliance review, and institutional authorization.

No claim of regulatory approval, clinical validation, or production readiness is made.
