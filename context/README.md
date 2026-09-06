# Project Context

Build history for the Blood Request PWA. One document per phase, covering what was
built, which files changed, how it was verified, and any constraint that shaped the
decision.

Source of truth for progress tracking remains [PHASE_CHECKLIST.md](../PHASE_CHECKLIST.md).

## Phases

| # | Phase | Document |
|---|---|---|
| 0 | Foundation scaffold and compliance baseline | [phase-00-foundation.md](phase-00-foundation.md) |
| 1 | Database schema and migrations | [phase-01-database.md](phase-01-database.md) |
| 2 | Authentication and session security | [phase-02-authentication.md](phase-02-authentication.md) |
| 3 | Doctor profile and seal upload | [phase-03-doctor-seal.md](phase-03-doctor-seal.md) |
| 4 | Patient and admission management | [phase-04-patients-admissions.md](phase-04-patients-admissions.md) |
| 5 | Blood request draft and frozen form | [phase-05-request-draft.md](phase-05-request-draft.md) |
| 6 | Review, submit, and Request ID generation | [phase-06-review-submit.md](phase-06-review-submit.md) |
| 7 | Request viewing and dashboard tables | [phase-07-request-view.md](phase-07-request-view.md) |
| 8 | Blood sample association | [phase-08-blood-samples.md](phase-08-blood-samples.md) |
| 9 | PWA installability and app-shell caching | [phase-09-pwa.md](phase-09-pwa.md) |
| 10 | Hardening, audit, and test coverage | [phase-10-hardening.md](phase-10-hardening.md) |
| — | Design system rollout | [design-system-rollout.md](design-system-rollout.md) |
| — | Admin panel and RBAC | [admin-panel-rbac.md](admin-panel-rbac.md) |
| — | Module 2: Blood bank dashboard | [module-2-blood-bank.md](module-2-blood-bank.md) |

## Workflow

```
Doctor → Authentication → Dashboard → Identify Admission/Patient
      → Create Blood Request → Complete Form → Review → Submit
      → Generate Blood Request ID → View Request → Associate Blood Sample
```

## Standing constraints

These held across every phase and should not be changed without review.

- **Frozen clinical wording.** Blood request form labels are reproduced verbatim,
  including the original spelling `Cryopresipitate`. A regression test enforces this.
- **Server-side identity.** Doctor name, provisional registration, and seal always come
  from the authenticated account, never from client input.
- **Immutability.** A request is editable only while `draft`. After submit it is
  read-only and receives a generated Request ID.
- **Admission identity.** `ip_no` is the primary key of `admissions`; blood requests
  reference it and carry their own UUID.
- **Network-only clinical data.** The app installs and caches its shell, but all data
  reads and writes require connectivity. No offline write queue exists.
- **No self-registration.** Accounts are provisioned by an admin or seed script.
- **Not clinically validated.** Licensed under PolyForm Noncommercial 1.0.0 and
  carrying a medical disclaimer; not for real clinical use without institutional review.

## Verification commands

```bash
npm run test       # node:test suite
npm run lint       # eslint
npm run typecheck  # tsc --noEmit
npm run build      # next build
```
