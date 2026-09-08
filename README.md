# Fitfinity Staff Portal — M4 readiness

Canonical React/Vite frontend reconstructed from the frozen v0.57 behaviour.
M3 is frozen and pushed at `7d114a1` / `m3-operations-frontend`. **M4.3 prepares the verified staff demo for GitHub Pages**; final M4 freeze and physical PWA acceptance remain pending. Backend/auth starts at **M5**.

## Progress: M1 → M3

| Milestone | Completed work |
|---|---|
| **M1 — Foundation** | React application shell, owner/trainer navigation, demo identities, mock persistence and service boundaries, client profiles, permissions, and initial automated tests. |
| **M2 — Sessions** | Session lists/details, exercise planning, outcomes and package-credit rules, client summaries, profile workflows, and responsive regression coverage. Frozen at `ebcec81` / `m2-sessions-frontend`. |
| **M3 — Operations** | Client and trainer onboarding with review/edit summaries; dashboard shortcuts; schedule approvals and Messages; remuneration; Exercise Library and local attachments; shared notification banners; Setup → Packages; navigation, accessibility, responsive layout and CSS/code-health repairs. |

The verified M3 checkpoint Mac run passed **212 unit tests in 47 files** and **357 browser tests**: 119 each on desktop Chromium, phone WebKit and tablet WebKit. The production build and final integrity/code-health gates also passed. The checkpoint is already committed, tagged and pushed. Do not rerun its installer to start M4.

## Current rules

- Packages contain **12, 24 or 36 sessions**, with **90, 180 or 270 days** of validity respectively. Weekly frequency is chosen independently; two or more sessions per week includes the free gym package. Existing purchases retain their saved package terms.
- Onboarding validates one section at a time, preserves drafts during Back/Edit, and saves only after the final confirmation.
- **Owner approval needed** checked means a change requires approval. Pending changes do not update the underlying schedule until approved.
- Remuneration uses each trainer's preset rates, with one session per compact row. Weekday peak starts are 06:30–08:30 and 18:00–20:30 (end times exclusive); weekends are peak all day.
- Successful actions use the shared, compact banner across the main content width. Field validation and retryable errors remain available.

## Run locally

```bash
npm ci
npm run dev -- --host
```

Use the Local or Network URL printed by Vite. Sign in with an account from the demo dropdown and initial password `FitfinityDemo1!` (or the replacement you saved). The demo identity selector and browser-local data are development features; production authentication and backend storage are not connected yet.

## Verification and delivery rules

Install the browser engines once with `npx playwright install`, then keep this full gate order:

```bash
unset NO_COLOR NODE_DISABLE_COLORS
export FORCE_COLOR=1 CLICOLOR=1 CLICOLOR_FORCE=1
export GIT_PAGER=cat PAGER=cat
npm test
npm run build
CI=1 PLAYWRIGHT_FORCE_TTY=0 npm run test:e2e -- --reporter=list
git --no-pager diff --check
```

Delivery scripts must verify the repository/base and expected source before editing; retain named green/red test output; check exact test totals, source integrity and code health; and stop on any failed, skipped or flaky test. The original 40 M2 unit scenarios and 150 M2 browser cases remain included. Keep the preview port 4173 free for the browser suite.

Edit canonical component, service and stylesheet owners in place. Remove superseded code; do not add patch files, duplicate implementations, override tails or backup artifacts. CSS review includes selector usage, responsive rules, duplicate declarations and custom properties. Static checks complement browser coverage; they do not prove every possible visual state.

Only print `=== COMPLETE — ALL GATES PASSED ===` after every required gate succeeds. Commit, tag or push only when authorized. Do not reset, stash, force-push or launch the development server automatically.

## M4.3 hosting readiness

- Fixed sidebars above 780px start fully collapsed, with independent section toggles, keyboard support and destination-section reveal after navigation. Hamburger menus keep expanded groups. Collapse preferences last for the current signed-in view and reset on account change/reload.
- The uploaded M4.2E Mac receipt passed all gates: 257 unit tests / 54 files, build, 423 browser cases and integrity/code health. The one-time HMR export removal was expected during the hook move. M4.3 adds root and repository-path PWA coverage; its full Mac browser run and physical-device acceptance remain pending.
- Dashboard shows the full recipient-scoped renewal follow-up count in a prominent badge, with up to three preview Messages above Weekly/Monthly calendars; the separate daily agenda and Today button remain removed. Calendar styling follows the Oracle prototype: owner Weekly/Monthly and trainer Monthly show only a session count under each date; tap the count for the full day. Trainer Weekly shows every session in a compact row grouped by day, without a preview cap. Owner day popups group sessions by trainer. Close/native Back/Forward and session navigation retain calendar context. View All Renewals opens the shared filtered inbox.
- Messages uses the same ProfileNavigation component and CSS as client/trainer profiles: an inline row from 700px and a selected-label dropdown below 700px, alongside search/date filters. Category routes survive reload; the dashboard uses the same list, popup, read/unread and record-link implementation.
- Owner Profile now shows the existing account name, role and status using shared profile components. It is read-only; no new account-editing requirements are implied.
- The production build generates a versioned, complete PWA shell cache. Updates wait until all app windows close; old-cache cleanup is limited to the current app directory's Fitfinity shell caches. Private/API responses and runtime uploads are excluded.
- Existing M2/M3 scenarios remain. The current inventory is **264 unit tests in 54 files** and **432 browser cases: 144 per project**. New inventory is not passing evidence; use the full-gate receipt for actual results.
- Navigation and the session list use Sessions. Instructional paragraphs are removed from Content Management, Change Password and other forms; field labels, record details, validation and concise media limits remain. Password requirements appear through notifications on focus or the requirements action, using loaded policy.
- Calendar, mock sign-in/session expiry, password change, sign-out and staff Content Management are functional. Public website publishing and Glofox members-only access remain deferred.
- Clients draw a signature, clear/redraw, review and save it. Late/no-show remains separate; completion debits one credit at most. Measured exercise loads update progress and CSV exports after completion.
- Session-video metadata commits only after persistent blob storage; failed replacements preserve the previous attachment. Cloud media and physical-device capture acceptance remain later work.
- Screens use injected asynchronous services and loaded configuration. Demo records/defaults are isolated under `src/data`; remuneration breakdowns come from the adapter. See [backend transition contract](docs/FRONTEND_SERVICE_CONTRACT.md).

Follow [GitHub Pages deployment](docs/GITHUB_PAGES.md) after the M4.3 installer passes. The workflow runs the unit and full browser gates before publishing. The deployment directory comes from Pages metadata; local builds default to `/`. Public/Glofox work remains deferred.

Review [migration status](docs/MIGRATION_STATUS.md), [Mac instructions](docs/FIRST_RUN_MAC.md),
[M4 acceptance checklist](docs/M4_ACCEPTANCE.md) and the
[AWS production architecture contract](docs/PRODUCTION_ARCHITECTURE.md).

Use a trusted HTTPS production preview for physical PWA installation/update tests.
The HTTP LAN development URL only establishes responsive browser behaviour.
Publish the complete generated `dist/`, including its generated worker. After an update
is downloaded, save/cancel edits, close all Fitfinity tabs and standalone windows, then reopen.

M5/M6 must preserve the portable stateless backend and low-cost AWS starting architecture
in the handoff. Final M4 freeze requires the exact green gate plus recorded device evidence.

## M4 physical acceptance repairs — 8 September 2026

The staff demo deployed successfully at `de257440`. Physical testing then identified
navigation-state, progress, date-gating, custom package-count and mobile-menu issues.
This candidate fixes the canonical owners and adds regression coverage. Required
verification is 289 unit tests in 57 files, root and Pages PWA builds, all 471 browser
cases and code health. Run the latest Oracle calendar installer before committing.
See `docs/M4_ACCEPTANCE.md` for the remaining device acceptance and
`docs/FRONTEND_SERVICE_CONTRACT.md` for policy and backend responsibilities.


Client Progress includes owner-only **View Export/WhatsApp History**. Owner and
assigned-trainer report actions save an action timestamp and staff identity through
`clientService.recordProgressReportAction`; the owner reads each client's entries
through `clientService.progressReportHistory`. CSV export and WhatsApp opening are
recorded as actions, not delivery confirmations. General Information has no renewal
status or renewal history controls.
