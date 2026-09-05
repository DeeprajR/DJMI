# Design system rollout

**Status:** Complete · 2026-09-06

## Goal

Apply the design system in [design-system-blood-app.md](../design-system-blood-app.md)
across every screen without touching clinical wording or form contracts.

## What was built

- **Tokens and components:** `src/app/design-system.css` — colours, typography, spacing,
  radii, elevation, and semantic component classes (`.panel`, `.button`, `.input`,
  `.field`, `.data-table`, `.notice`, `.status-pill`, `.blood-chip`, `.metric-card`,
  `.workflow-steps`)
- **App shell:** `src/components/app-shell.tsx` — responsive navigation, skip link,
  offline banner, medical disclaimer footer
- **Typography:** Bricolage Grotesque for headings, IBM Plex Sans for UI text, Noto Sans
  Malayalam fallback, all self-hosted via `next/font`. Tabular numerals throughout.
- **New screens:** loading, error, not-found, plus rebuilt landing, sign-in, and offline
- **Themes:** system-driven light and dark, with print styles that strip navigation

## Core principles applied

- **Red means blood, not decoration.** Crimson is reserved for blood groups, urgency, and
  the single primary action per screen. Validation errors use amber; the offline banner is
  neutral grey.
- **48px minimum touch targets** at every breakpoint, including desktop
- **52px inputs**, single-column forms capped at 480px
- **Blue focus ring**, always visible
- **Responsive navigation:** bottom bar under 768px, 72px icon rail at 768px, 240px
  sidebar at 1024px, with `env(safe-area-inset-*)` padding for standalone mode

## Preserved

Clinical form wording, read-only identity fields, API form contracts, authentication, and
the draft → submitted workflow were all left untouched. A regression test enforces the
frozen labels.

## Files changed

Every page component; `src/app/globals.css`, `src/app/design-system.css`,
`src/components/app-shell.tsx`, `src/app/layout.tsx` (fonts, viewport, theme colour);
`src/app/loading.tsx`, `src/app/error.tsx`, `src/app/not-found.tsx`; PWA icons, manifest,
registration and shell cache; `src/components/design-system.test.ts`,
`src/components/service-worker.test.ts`; `scripts/preview-design.ts`; `README.md`;
`PHASE_CHECKLIST.md`

## Verification

- **Browser:** 24 authenticated route/viewport combinations at 320px, 768px, and 1440px —
  no horizontal overflow, no control under 48px, never more than one filled primary action
  per screen. Eight public screen/theme combinations. Keyboard skip link, focus ring, and
  reduced motion confirmed.
- **Workflow:** draft → submit → sample association completed end-to-end using synthetic
  data only.
- **Automated:** 12 tests passing, including WCAG AA contrast ratios for every semantic
  colour pair, control dimensions, focusable `main` landmarks on every page, and frozen
  form wording.
- **Quality:** lint, TypeScript, and production build all passed.

## Notes

A disposable preview harness, `scripts/preview-design.ts`, runs the production build
against a throwaway embedded PostgreSQL instance with synthetic fixtures on loopback ports
3100/55433. It never touches the configured clinical database and is not for deployment.

Native installation and real-device offline emulation were not tested; the integrated
browser did not support network emulation.

## Known pitfall

Editing CSS while the dev server runs can leave Turbopack holding a stale negative
resolution for an imported stylesheet, producing a misleading
`Can't resolve './design-system.css'` build error. Restart the dev server rather than
debugging the import.
