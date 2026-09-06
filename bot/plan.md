# PRD: Blood Donor Telegram Bot

**Version:** 1.0 (Draft)
**Status:** For review
**Scope:** Telegram bot only (donor + volunteer admin experience). The blood bank system that originates requests is a separate component and out of scope here, except for the API contract it must fulfill.

---

## 1. Problem Statement

When a blood bank has urgent demand, reaching eligible, willing, nearby donors is slow and manual — requests travel through phone calls and unstructured WhatsApp forwards, with no way to know who is eligible, who has responded, or when demand is met. Donors, in turn, get spammed with requests they can't act on and drop out. The cost is delayed fulfillment of urgent blood demand and burnout of the volunteer donor pool.

## 2. One-line Concept

A Telegram bot that lets verified blood donors receive, accept, and complete blood donation requests in under 3 taps, while volunteer admins amplify requests through their networks via forwardable deep links — with demand originating from the blood bank system.

## 3. Goals

1. **Fast fulfillment:** Median time from request broadcast to required units confirmed (approved donors ≥ units needed) under 60 minutes for common blood groups.
2. **Frictionless onboarding:** ≥ 80% of donors who tap a deep link complete registration; median onboarding time under 90 seconds.
3. **Zero wasted pings:** Donors only ever receive requests they are eligible for (blood-group compatible, in-district, past cooldown, not snoozed).
4. **Reliable donor data:** ≥ 95% of completed donations recorded with a donation date, keeping future eligibility computation accurate.
5. **Admin leverage:** Every request reachable by donors outside the registered pool via admin-forwarded deep links; new-donor signups attributable to admin links.

## 4. Non-Goals (v1)

- **Creating requests inside the bot.** Demand originates only from the blood bank system via API. (Prevents duplicate/unverified requests; keeps the bot a pure distribution channel.)
- **Medical certification.** The questionnaire filters obviously ineligible donors to prevent wasted trips; final medical screening always happens at the blood bank.
- **Donor–recipient direct contact or patient details.** The bot exposes only blood group, hospital, units, and time. No patient names or attender phone numbers. (Privacy + safety.)
- **Payments, rewards, or gamification.** Revisit post-v1 once the core loop works.
- **Multi-language UI.** v1 ships in one language (English or Malayalam — decide before build); architecture must not block adding the second later.
- **In-bot chat/support with admins.** Out of scope for v1; a static help contact is sufficient.

## 5. Personas

- **Donor (first-time):** Arrived via an admin's forwarded link or word of mouth. Has Telegram, may never have used a bot. Needs onboarding to be near-zero effort.
- **Donor (registered):** Wants to help but hates noise. Will tolerate rare, relevant, actionable pings. Needs one-tap responses and clear status.
- **Volunteer admin:** Runs a circle (college group, residents' association, NGO chapter). Needs a forwardable message + live visibility into whether a request still needs pushing.
- **Blood bank system (machine actor):** Sends demand, receives fulfillment status. Interacts via API only.

## 6. User Stories

**Donor — onboarding**
- As a first-time donor, I want to register by tapping buttons and sharing my Telegram contact so that I never have to type more than my name.
- As a first-time donor arriving via a request link, I want to land directly on that request after registering so that I can act on the reason I came.
- As a donor who doesn't know my blood group, I want to select "I don't know" so that I can still register and be verified at my first donation.

**Donor — requests**
- As a registered donor, I want to receive only requests I'm eligible for so that every notification is actionable.
- As a donor, I want to accept or decline a request in one tap so that responding takes seconds.
- As an accepted donor, I want to answer a short questionnaire and immediately get my appointment slot so that I know exactly where to be and when.
- As a confirmed donor, I want a reminder before my appointment so that I don't forget.
- As a donor whose donation is completed, I want a thank-you with my next eligible date so that I know when I can help again.
- As a donor, I want to cancel a confirmed slot so that the slot can go to someone else.
- As a donor, I want to snooze all requests for a period so that I can mute the bot without blocking it.

**Donor — account**
- As a donor, I want to view and update my district/city, phone, and last-donation date so that my record stays accurate.
- As a donor, I want to see currently open requests I'm eligible for so that I can volunteer proactively.

**Volunteer admin**
- As an admin, I want each new request delivered with a pre-formatted forwardable message and deep link so that I can amplify it to my circles in one forward.
- As an admin, I want a live counter (accepted / confirmed / completed vs. units needed) so that I know whether to keep pushing.
- As an admin, I want to know when a request is fulfilled or expired so that I stop promoting it.

## 7. Core Flows

### 7.1 Request lifecycle (system view)

```
Blood bank system → POST /requests → Bot
Bot → notify admins (forwardable message + deep link)
Bot → notify eligible donors in waves
Donor: Accept → Questionnaire → PASS → Auto-confirmed (if units remain) → Slot + reminder
                              → FAIL → Eliminated from request (polite message)
Units confirmed == units needed → request CLOSED to new confirmations
Blood bank marks donations completed → Bot sends thank-you + next eligible date
Request expires at needed-by time if unfulfilled → notify admins
```

### 7.2 Donor states per request

`NOTIFIED → ACCEPTED → SCREENING → CONFIRMED → COMPLETED`
Exit paths: `DECLINED` (explicit "Not this time"), `ELIMINATED` (questionnaire fail), `CANCELLED` (donor cancels after confirm — slot reopens, waitlist promoted), `NO_SHOW` (marked by blood bank/admin), `REQUEST_FILLED` (accepted but units already met → placed on waitlist, notified if a slot reopens).

### 7.3 Onboarding (first-time donor)

/start (or deep link) → share contact button (captures verified phone) → name → DOB (date picker) → sex (buttons; needed for cooldown rule) → blood group (button grid incl. "I don't know") → district picker → city/town picker → "Have you donated before?" → if yes, last donation date → consent to receive request notifications → done.
If entry was via `?start=req_<id>` and the donor is eligible for that request, show the request card immediately.

### 7.4 Eligibility computation (automatic, never asked)

A donor is eligible for a request when ALL of:
- Blood group compatible with the requested group (full compatibility matrix, e.g., O− matches all; "I don't know" donors are only matched once verified)
- Same district as the request (city used for wave ordering, not exclusion)
- Age 18–65 (from DOB)
- Cooldown passed: ≥ 90 days since last donation (male), ≥ 120 days (female) — NBTC norms
- Not snoozed, not opted out, not already engaged with this request

### 7.5 Wave-based notification

Notify eligible donors in waves of N (default 20), ordered by proximity (same city first) then by longest-since-last-donation. Escalate to next wave if confirmed count < units needed after T minutes (default 30). Stop all waves the moment confirmations == units needed.

### 7.6 Questionnaire (pre-screening, hard gate)

Yes/no button questions, e.g.: weight ≥ 45 kg; feeling well today; illness/fever in last 2 weeks; antibiotics or other medication currently; tattoo/piercing in last 6 months; alcohol in last 24 hours; (female) currently pregnant or recently delivered.
**Fail behavior (per decision):** any disqualifying answer eliminates the donor from this request with a courteous message. Temporary conditions (fever, medication, tattoo) do NOT alter the donor's profile — they remain eligible for future requests. Permanent-style answers may set a flag for admin review. Never phrase elimination as a medical verdict.

### 7.7 Volunteer admin flow

Request created → all admins (or admins of that district) receive: request card + "Forward this" pre-formatted message containing `t.me/<bot>?start=req_<id>` + live status line. Admin forwards to circles. Status message auto-updates (or admin taps "Refresh"). On fulfillment/expiry, admins get a closing notification.

## 8. Requirements

### P0 — Must-have (cannot ship without)

| # | Requirement | Acceptance criteria (abridged) |
|---|-------------|-------------------------------|
| P0-1 | Inbound request API from blood bank system (create, close/fulfill, cancel) with auth | Given a valid signed request payload (blood group, units, hospital, needed-by, district), when POSTed, then a request is created and distribution begins; invalid/unauthenticated payloads rejected with error |
| P0-2 | Donor onboarding flow as in 7.3, all input via buttons except name | A new user completes registration end-to-end without typing anything except their name; record stores telegram_user_id (PK), verified phone, name, DOB, sex, blood group, district, city, last donation date, consent timestamp |
| P0-3 | Deep-link entry `?start=req_<id>` | New user completing onboarding via a request link is shown that request if eligible; registered user tapping the link goes straight to the request card; filled/expired requests show a "request closed — thank you" message |
| P0-4 | Eligibility engine per 7.4 with full blood-group compatibility matrix | An ineligible donor (wrong group / cooldown / other district / snoozed) never receives the request notification |
| P0-5 | Wave-based fan-out per 7.5 | Given units are met, when the next wave timer fires, then no further donors are notified |
| P0-6 | Accept / Not-this-time inline buttons | Tapping either records the response and updates the message; donor is never re-notified for that request |
| P0-7 | Auto-approve until units met (per decision) | Given confirmations < units needed, when a donor passes screening, they are confirmed instantly; given units met, the donor is told the request is filled and placed on the waitlist |
| P0-8 | Hard-gate questionnaire per 7.6 (per decision) | Any disqualifying answer ends the flow for this request with a polite message; the slot is not consumed; temporary fails don't change future eligibility |
| P0-9 | Confirmation message with hospital, address, appointment time; reminder 2h before needed-by/slot time | Confirmed donor receives both messages |
| P0-10 | Donor cancel after confirmation | Slot reopens; earliest waitlisted donor is offered it; admins' counters update |
| P0-11 | Completion → thank-you + next eligible date; last-donation date updated | Given blood bank marks a donation complete via API, the donor's record and cooldown update and the thank-you is sent |
| P0-12 | Admin request card + forwardable deep-link message + live counter | Admin receives card within seconds of request creation; counter reflects accepted/confirmed/completed vs units |
| P0-13 | Account settings: view/update district, city, phone, last donation date; snooze (1/3/6 months); delete my data | Each is reachable from a persistent menu and works via buttons |
| P0-14 | View open eligible requests on demand | Donor can list open requests they qualify for and accept from the list |

### P1 — Nice-to-have (fast follows)

- Waitlist auto-promotion with time-boxed offer ("A slot opened — confirm within 15 min")
- Rejection/closure reasons surfaced to donors ("Request was fulfilled — you weren't needed this time, thank you")
- Admin scoping by district (admins only see their district's requests)
- No-show marking by admin and gentle follow-up to donor
- Attribution analytics: which admin's link produced which signups/donations
- Proactive "you're eligible again" nudge on cooldown expiry (opt-in)
- Second language (Malayalam/English toggle)

### P2 — Future considerations (design for, don't build)

- Multiple blood banks / multi-tenant support (keep `blood_bank_id` on requests from day one)
- Donation history view and shareable donor card
- Emergency "rare group" escalation path (wider radius, all-districts blast with admin approval)
- Web dashboard for blood bank staff (today they only have the API)

## 9. Success Metrics

**Leading (first 30 days)**
- Deep-link → completed registration conversion ≥ 80%
- Median onboarding duration < 90s
- Request acceptance rate (accepts / notified) ≥ 15%
- Median time to fulfillment (broadcast → units confirmed) < 60 min for A/B/O+ groups
- Notification opt-out + block rate < 3% of registered donors

**Lagging (quarter 1)**
- % of requests fulfilled before needed-by time ≥ 90%
- Confirmed-to-completed rate ≥ 85% (measures no-shows/cancellations)
- 90-day donor retention (still opted-in, not blocked) ≥ 85%
- Repeat donation rate among eligible donors trending up quarter over quarter

Measurement: bot event log (every state transition timestamped per request per donor); evaluate at 1 week, 1 month, 1 quarter.

## 10. Open Questions

- **[Blood bank / integration — blocking]** Exact API contract and auth mechanism from the blood bank system: who signs requests, how are completions reported, is there a sandbox?
- **[Blood bank — blocking]** Are appointment times slotted (bot assigns slots) or is it "arrive before needed-by time"? P0-9 assumes the latter with an optional slot field.
- **[Product — blocking]** v1 language: English or Malayalam?
- **[Ops — non-blocking]** Who onboards/verifies volunteer admins, and how are they added to the bot (manual whitelist is fine for v1)?
- **[Legal/privacy — non-blocking]** Data retention policy and consent wording for storing health-adjacent data (DPDP Act 2023 applies: phone, DOB, donation history). Draft consent text needed before launch.
- **[Product — non-blocking]** Should "I don't know my blood group" donors receive any requests (e.g., drives/camps) before verification, or stay fully unmatched?

## 11. Timeline & Phasing (suggested)

- **Phase 1 (build):** P0-1 → P0-8 — request intake, onboarding, eligibility, fan-out, accept/screen/confirm loop. This is a testable end-to-end skeleton.
- **Phase 2 (build):** P0-9 → P0-14 — confirmations, reminders, cancellations, completion loop, admin tooling, settings.
- **Pilot:** one district, one blood bank, 3–5 volunteer admins, seeded donor pool of 100–200. Run 4 weeks against the leading metrics before widening.
- **Dependency:** the blood bank system's request API (Open Question 1) gates Phase 1 integration testing; the bot can be built against a mock in the meantime.

## 12. Key Technical Notes (constraints for whoever builds it)

- Primary key = Telegram `user_id`; phone stored as verified attribute via contact-share (prevents duplicates across number changes).
- All request/donor state transitions must be idempotent — Telegram delivers duplicate callback taps.
- Concurrency guard on confirmation: two donors passing screening simultaneously for the last unit must resolve to exactly one confirmation and one waitlist placement.
- Deep-link payload limit: Telegram `start` parameter ≤ 64 chars — short request IDs.
- Message edits, not new messages, for status updates on the same request card (keeps donor chat clean).