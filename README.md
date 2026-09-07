# Fitfinity Staff Portal — M3

Canonical React/Vite frontend reconstructed from the frozen v0.57 behaviour.
M3 covers the operational frontend through M3.9C. The next milestone is **M4 — frontend freeze and acceptance**; backend/auth starts at **M5**.

## Progress: M1 → M3

| Milestone | Completed work |
|---|---|
| **M1 — Foundation** | React application shell, owner/trainer navigation, demo identities, mock persistence and service boundaries, client profiles, permissions, and initial automated tests. |
| **M2 — Sessions** | Session lists/details, exercise planning, outcomes and package-credit rules, client summaries, profile workflows, and responsive regression coverage. Frozen at `ebcec81` / `m2-sessions-frontend`. |
| **M3 — Operations** | Client and trainer onboarding with review/edit summaries; dashboard shortcuts; schedule approvals and Messages; remuneration; Exercise Library and local attachments; shared notification banners; Setup → Packages; navigation, accessibility, responsive layout and CSS/code-health repairs. |

The verified M3.9C Mac run passed **212 unit tests in 47 files** and **357 browser tests**: 119 each on desktop Chromium, phone WebKit and tablet WebKit. The production build and final integrity/code-health gates also passed. The M3 checkpoint script reruns these gates before creating the `m3-operations-frontend` tag and pushing `main`.

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

Use the Local or Network URL printed by Vite. The demo identity selector and browser-local data are development features; production authentication and backend storage are not connected yet.

## Verification and delivery rules

Install the browser engines once with `npx playwright install`, then keep this full gate order:

```bash
unset NO_COLOR NODE_DISABLE_COLORS
export FORCE_COLOR=1 CLICOLOR=1 CLICOLOR_FORCE=1
npm test
npm run build
CI=1 PLAYWRIGHT_FORCE_TTY=0 npm run test:e2e -- --reporter=list
git diff --check
```

Delivery scripts must verify the repository/base and expected source before editing; retain named green/red test output; check exact test totals, source integrity and code health; and stop on any failed, skipped or flaky test. The original 40 M2 unit scenarios and 150 M2 browser cases remain included. Keep the preview port 4173 free for the browser suite.

Edit canonical component, service and stylesheet owners in place. Remove superseded code; do not add patch files, duplicate implementations, override tails or backup artifacts. CSS review includes selector usage, responsive rules, duplicate declarations and custom properties. Static checks complement browser coverage; they do not prove every possible visual state.

Only print `=== COMPLETE — ALL GATES PASSED ===` after every required gate succeeds. Commit, tag or push only when authorized. Do not reset, stash, force-push or launch the development server automatically.

## Next: M4

M4 will reconcile the remaining frontend scope, complete phone/iPad/desktop and PWA acceptance, verify install/update/offline behaviour, and establish the canonical frontend freeze. Content Management, the owner-profile placeholder, public-site parity and session-media limitations still need explicit scope review. M3's green test count does not establish that this work is complete.

**M5** introduces backend/auth, followed by domain API replacement and production notification/media integration. Exercise Library attachments currently use browser-local storage; session filming remains a partial browser prototype. Cloud upload, processing and reliable cross-device media are later integration work.

The earlier `docs/MIGRATION_STATUS.md` and `docs/FIRST_RUN_MAC.md` describe the initial migration slice. This README records the current milestone position and supersedes their old progress labels.
