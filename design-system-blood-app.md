# Design System — Blood Collection App

## Principles

1. Red is information, not decoration — red only for blood types, urgency, live requests, SOS.
2. Design for the worst minute — 48px min touch targets, AA+ contrast, one decision per screen in emergency flows.
3. One system, five roles — roles differ by accent badge only, never full re-theme.
4. Data reads like a chart — tabular figures for all numbers; blood type is the only hero data element.
5. Motion earns its place — only ambient animation is the critical-request pulse.

## Colors

### Neutrals
| Token | Hex |
|---|---|
| neutral-0 | #FFFFFF |
| neutral-25 | #FAFBFC |
| neutral-50 | #F3F5F7 |
| neutral-100 | #E7EAEE |
| neutral-200 | #D2D7DE |
| neutral-300 | #AAB2BD |
| neutral-400 | #7C8595 |
| neutral-500 | #59616F |
| neutral-700 | #333A45 |
| neutral-900 | #181C23 |

### Crimson
| Token | Hex |
|---|---|
| crimson-50 | #FDF2F3 |
| crimson-100 | #FAE0E3 |
| crimson-200 | #F3BDC4 |
| crimson-400 | #D95468 |
| crimson-600 | #B2273C |
| crimson-700 | #93202F |
| crimson-800 | #741A26 |
| crimson-900 | #571219 |

### Support
| Token | Hex |
|---|---|
| green-100 | #DCF2E6 |
| green-600 | #1E7F4F |
| green-800 | #155C39 |
| amber-100 | #FCEFD8 |
| amber-600 | #B45309 |
| amber-800 | #7C3A06 |
| blue-100 | #DEEAF8 |
| blue-600 | #1D6FB8 |
| blue-800 | #154E82 |
| violet-100 | #E9E4F6 |
| violet-600 | #5B4BA6 |

## Semantic tokens

### Surfaces & text
| Token | Light | Dark |
|---|---|---|
| bg/app | neutral-25 | #101318 |
| bg/surface | neutral-0 | #181D24 |
| bg/recessed | neutral-50 | #0C0F13 |
| border/subtle | neutral-100 | #262C35 |
| border/strong | neutral-200 | #38404C |
| text/primary | neutral-900 | #EDF0F4 |
| text/secondary | neutral-500 | #9AA3B0 |
| text/disabled | neutral-300 | #5A6472 |
| text/inverse | neutral-0 | #101318 |

### Interactive
| Token | Value |
|---|---|
| action/primary | crimson-600 |
| action/primary-hover | crimson-700 |
| action/primary-pressed | crimson-800 |
| action/secondary | neutral-900 outline |
| action/link | blue-600 |
| focus/ring | blue-600, 2px, 2px offset |

### Urgency tiers
| Tier | Background | Border | Text |
|---|---|---|---|
| routine | bg/surface | border/subtle | text/primary |
| soon | amber-100 | amber-600 1.5px | amber-800 |
| critical | crimson-50 | crimson-600 2px + 4px left rail | crimson-900 |

### Role accents (badge only)
| Role | Color |
|---|---|
| Patient | crimson-600 |
| Donor | green-600 |
| Doctor | blue-600 |
| Blood bank | violet-600 |
| Bystander | amber-600 |

### Blood type chip
- Filled: bg crimson-600, text neutral-0, radius pill
- On tint: bg crimson-100, text crimson-900, border crimson-200

## Typography

- Display: Bricolage Grotesque (500/600/700)
- Body/UI: IBM Plex Sans (400/500/600), tabular figures for numbers
- Fallbacks: Noto Sans Malayalam; -apple-system, "Segoe UI", Roboto, sans-serif

| Token | Family | Size/Line | Weight | Tracking |
|---|---|---|---|---|
| display | Bricolage | clamp(28px, 5vw, 40px) / 1.15 | 700 | -0.5px |
| title-lg | Bricolage | clamp(22px, 3.5vw, 28px) / 1.25 | 600 | -0.25px |
| title | Bricolage | clamp(18px, 2.5vw, 22px) / 1.3 | 600 | 0 |
| body-lg | Plex Sans | 18/28 | 400 | 0 |
| body | Plex Sans | 16/24 | 400 | 0 |
| body-strong | Plex Sans | 16/24 | 600 | 0 |
| body-sm | Plex Sans | 14/20 | 400 | 0 |
| caption | Plex Sans | 12/16 | 500 | +0.1px |
| button | Plex Sans | 16/24 | 600 | 0 |
| blood-type | Bricolage | 22/24 | 700 | 0 |
| data-hero | Bricolage | clamp(36px, 5vw, 48px) / 1.1 | 700, tabular | -0.5px |
| data | Plex Sans | 16/24 | 500, tabular | 0 |

Max line length 68ch. Minimum size 12px. Sentence case everywhere; no all-caps labels.

## Breakpoints (PWA — min supported width 320px)

| Token | Range | Layout |
|---|---|---|
| xs | 320–479 | 1 column, bottom nav |
| sm | 480–767 | 1 column, bottom nav |
| md | 768–1023 | 2 columns, side rail nav (72px, icons) |
| lg | 1024–1439 | 2–3 columns, side nav expanded (240px) |
| xl | 1440+ | 3 columns, content capped |

## Layout grid

| Token | Value |
|---|---|
| container/max | 1200px, centered |
| content/max (reading) | 680px |
| grid/columns | 4 (xs–sm) · 8 (md) · 12 (lg+) |
| grid/gutter | 16 (xs–sm) · 24 (md+) |
| screen gutter | 16 (xs–sm) · 24 (md) · 32 (lg+) |

- Cards: full-width xs–sm; 2-up md; 3-up lg+ (request/donor lists).
- Modals: bottom sheet (radius xl top) below md; centered dialog max-w 480px at md+.
- Forms: single column always, max-w 480px at md+.
- SOS button: full-width xs–sm; max-w 400px centered at md+.

## PWA rules

- Safe areas: pad with `env(safe-area-inset-*)` on nav bars, sheets, and SOS button (standalone mode).
- Hover states only under `@media (hover: hover)`; pressed states everywhere.
- Touch targets stay 48px minimum at all breakpoints, including desktop.
- Theme color meta: `#FAFBFC` light / `#101318` dark. Splash/manifest background: `bg/app`.
- Offline state uses `bg/recessed` banner with `text/secondary` — never red (red = blood-meaning only).

## Spacing (4pt)

4, 8, 12, 16, 20, 24, 32, 40, 48, 64

- Card padding: 16 (xs–sm), 20 (md+) · Between cards: 12 · Between sections: 32 (xs–sm), 40 (md+)

## Sizes
| Token | Value |
|---|---|
| touch-min | 48×48 |
| button | h48 |
| button-lg | h56 |
| sos | h64, full-width |
| input | h52 |
| icon | 24 (20 inline) |
| avatar | 40 (64 profile) |

## Radius
| Token | Value | Use |
|---|---|---|
| sm | 6 | chips, tags |
| md | 10 | inputs, secondary buttons |
| lg | 14 | cards |
| xl | 20 | sheets, modals |
| pill | 999 | blood type chips, status pills, SOS |

## Elevation
| Token | Value | Use |
|---|---|---|
| none | — | default; cards use border/subtle |
| raised | 0 2px 8px rgba(24,28,35,0.08) | sticky bars, FAB |
| overlay | 0 8px 28px rgba(24,28,35,0.16) | sheets, dialogs |

## Motion
| Token | Value | Use |
|---|---|---|
| fast | 120ms ease-out | presses, toggles |
| base | 200ms ease-in-out | sheets, tabs |
| slow | 320ms ease-in-out | screen transitions |
| pulse | 1.6s loop, opacity 1→0.45→1 | critical dot only |

Reduced motion: pulse becomes static dot; transitions become instant fades.

## Accessibility rules

- Text contrast ≥ 4.5:1; large text/icons ≥ 3:1.
- Urgency triple-encoded: color + border + text label.
- Blood group always rendered as text, never color-only.
- Focus ring always blue, visible on all surfaces.
- One filled red button per screen maximum.