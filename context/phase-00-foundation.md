# Phase 0 — Foundation scaffold and compliance baseline

**Status:** Complete · 2026-09-06

## Goal

Stand up a TypeScript Next.js project with the licensing and medical-disclaimer
posture this domain requires, before any clinical logic exists.

## What was built

- Next.js App Router project in TypeScript
- PolyForm Noncommercial 1.0.0 license
- Medical disclaimer rendered in the app shell and documented in the README
- Base scripts wired: `lint`, `typecheck`, `build`
- `.env.example` documenting required configuration

## Files changed

`.gitignore`, `README.md`, `package.json`, `src/app/globals.css`,
`src/app/layout.tsx`, `src/app/page.tsx`, `.env.example`, `LICENSE`

## Verification

`npm run lint`, `npm run typecheck`, `npm run build` all passed.

## Notes

`create-next-app` refused to scaffold in place because the workspace directory name
`Blood Request` contains a space and a capital letter, which fails npm package-name
validation. Resolved by scaffolding into a lowercase-hyphen subdirectory and moving the
contents to the project root.

## Decisions

- **PolyForm Noncommercial over MIT/Apache.** Deliberate: this is unvalidated clinical
  software and permissive licensing would invite unreviewed reuse.
- **Disclaimer in the layout, not a page.** It appears on every screen so it cannot be
  bypassed by deep-linking.
