# Fitfinity Staff Portal Documentation

Updated 8 September 2026. This is the consolidated project handoff, operating guide and architecture contract. It covers the owner/trainer React portal reconstructed from the frozen v0.57 reference. Current source and later agreed requirements supersede historical prototype rules.

## Process Thus Far

### Milestones and current position

| Milestone | Status and scope |
|---|---|
| M0 | Frozen v0.57 behavioural reference. |
| M1 — Foundation | Completed: React shell, role navigation, demo identities, mock persistence, service boundaries, profiles, permissions and initial tests. |
| M2 — Sessions | Frozen at `ebcec81`, tag `m2-sessions-frontend`: session lists/details, planning, outcomes, package-credit invariants, summaries and responsive workflows. |
| M3 — Operations | Frozen and pushed at `7d114a14630f5c17ab2c761626695dd655a847c1`, tag `m3-operations-frontend`: client/trainer onboarding, approvals and Messages, remuneration, Exercise Library, Packages, shared notifications, accessibility and code-health repairs. |
| M4 — Staff frontend acceptance | In progress: hosted staff demo, physical-device repairs, calendar refinements, PWA release handling and documentation. Final freeze remains pending. |
| M5 — Backend/auth foundation | Cognito integration, authenticated sessions, PostgreSQL migrations, `/me`, server authorization and authoritative policy/clock. |
| M6 — Domain APIs | Replace mock adapters with durable domain APIs while preserving the frontend contracts and existing scenarios. |
| M7 — Events and media | Backend events, scheduled notifications, protected cloud media and processing/delivery. |
| M8 / M9 | Production-like staging and owner/trainer UAT; then launch, monitoring, backups and operating runbook. |

The latest committed remote source is `04dc6ebd752050c3409c46b58baebbcfe834cbdc`. The current working candidate adds the refinements described below and is uncommitted. The publicly reachable deployment is a staff demo using browser-local records; real authentication and backend storage start at M5. Clients do not sign into the operational portal.

### Current acceptance baseline

- Dashboard renewal Messages sit above Weekly/Monthly calendars as compact single rows; the separate daily agenda and Today button remain removed. The total follow-up number is 23.4px, 35% below its previous 36px size.
- Renewals have one reminder type: two package sessions remaining, such as 10/12, 22/24 and 34/36. A package creates at most one reminder, shared by the owner and its assigned trainer; reading, reloads and completion corrections never generate another.
- Weekly shows seven consecutive dates from the displayed period's start, initially the gym's today; arrows move seven days. Monthly shows only its own 28–31 dates, aligned to weekdays. Empty dates have no View day action in either mode. Weekly/Monthly sit at the top right beside Calendar; period arrows and range are below, with no single-date picker.
- Owner calendars and trainer Monthly use counts and day popups. Trainer Weekly shows every session in a compact time/client/status row. Every day-popup session also shows Not Planned, Planned or Completed. Past days dim while existing actions remain enabled; Today has a visible label, strong blue surface and inset border.
- Sessions opens on Upcoming, nearest first. All sorts from the furthest future date/time backwards across statuses. Back preserves explicit filters, page, related profile tab and scroll. Remuneration Show/Hide amounts controls are compact in both roles.
- Physical repairs restore account-scoped navigation state, mobile section collapse, numeric progress from signed plans, future-date action guards, future-only trainer time-change requests and configurable integer package counts.
- Client Progress has owner-only Export/WhatsApp History. Owner and assigned-trainer report actions record who acted and when. General Information has no manual renewal status, date or history workflow.
- Existing onboarding, approvals, profile permissions, exercise management, drawn signatures, mock account flows and generic staff Content Management remain in scope. See [Frontend Architecture](#frontend-architecture) for their exact contracts.

No new complete screen-by-screen visual comparison against v0.57 is claimed. Final M4 acceptance requires the current candidate's complete green gate and recorded physical-device evidence.

### Development and delivery rules

- **Canonical code, no patch style:** Reconstruct the frozen v0.57 behaviour in canonical React owners; do not translate its historical patch chain. Keep one owning component/service/style per responsibility. No patch files, versioned fixes, CSS override tails, backup source, duplicate features or drifting owner/trainer copies. Remove superseded code. Temporary rollback backups are never canonical source or tracked deliverables.
- **Service and policy boundaries:** Components call injected services; do not mutate stored arrays or scatter persistence/fetch calls through screens. Load business timezone, clock context, currency, password/package rules and configuration through the existing policy/service boundary. Keep mock records/defaults isolated and enforce real authorization in the backend.
- **Interaction and layout:** Preserve one shared navigation/history owner, single active editor, dirty-exit guard, confirmation, notification and modal layer. Retain existing review/confirm/save flows; opening or closing Messages does not require confirmation. Successful saved edits generate the relevant Messages through their service flow. Operational lists must not require horizontal scrolling: wrap values and expand rows. Preserve vertical panning and horizontal Back gestures, visible keyboard focus, scoped records and saved navigation context.
- **Regression discipline:** Automate high-risk behaviour before advancing. Preserve lifecycle/status, Messages, navigation, trainer-schedule and original M2/M3 coverage, including 40 M2 unit scenarios and 150 M2 browser cases. Deliberate new scenarios must update exact inventory checks and CI together. Never increase timeouts/retries or skip assertions to mask failures. State when a delivered change affects tests only; do not claim an application fix from a fixture or assertion change. Static code/CSS checks complement full browser and physical acceptance.
- **Ordered delivery gate:** Preflight → recognised source and test inventory → all unit tests → production builds → all browser tests → integrity/code health. Reject unknown/partial source, failed/skipped/flaky/incomplete results and failures masked by `tee`. Keep named green/red logs, report directory and candidate fingerprint; print the completion marker only after every required gate passes.
- **Installer limits:** A routine installer never installs dependencies, launches a development server, stages, commits, tags, pushes or publishes. Preserve unknown edits and stop on a mismatch; no reset/stash/force-push. Use the exact recognised revision and keep the installer outside the repository.
- **Checkpoint and publication:** Before an explicitly authorized checkpoint, deliberately review `git status`, `git diff --check`, the intended changes, then the staged whitespace check and staged stat. Commit/push only the reviewed checkpoint. Publication is a separate post-gate action; a hosted demo checkpoint does not freeze M4 without device evidence.

### Verification evidence and required gate

| Checkpoint | Evidence retained |
|---|---|
| Frozen M3 | Mac: 212 unit tests / 47 files, build and 357 browser cases, 119 per project; integrity/code health passed. 159-file fingerprint: `9648fe7a4801b90ef947d47bd2a009ff4396966420c55b0261afeb174d983ba6`. |
| M4.2E | Uploaded Mac receipt: all gates passed, 257 units / 54 files and 423 browser cases. Fingerprint: `89de2e49de4a68a3b4466f9fd6e1698ef749bf40853ded32e0a802e6ed5da6e4`. |
| M4.3 and media/client-refresh follow-up | Mac: 264 units / 54 files and 432 browser cases passed. Deployed checkpoint: `de257440787b88470d4ee096115abb9df2061acf`; fingerprint `d32f6ede6bee04bcdaedc585ee8d883860507c7bd018901ef63b3eea05cdd906`. |
| Report action history | Mac receipt 083541: all gates passed, 287 units / 56 files, root/Pages builds and PWA checks, 471 browser cases and code health. Fingerprint: `ddebf8a2aee5d031293b11bd5f42050053198a405e144f4af14e1ca24a84ddf3`. |
| Committed Oracle calendar | Mac receipt 134618: 289 units / 57 files, 471 browser cases, builds/PWA and code health passed. Fingerprint: `a37207fadcb3d407132ed4cd8f6c2a2f17c345e03e979341b07e1c49f9d28895`; all 209 Git blobs matched published commit `04dc6ebd`. |
| Label restoration / past-day dimming | User reported all gates passed; no new terminal receipts attached. Fingerprints: `b2b524777f02e25f700a667a6eed50c9a232bc250eb5dd9d5ecf813837fd08cf` and `3337a5db6821fb01a52e511b43ad1f2a4a6ff45ff271f3a3a159fd7904d0f39f`. |
| Dashboard/session follow-up | Workspace: 289 units / 57 files, both builds, PWA checks, 471-case discovery and code health passed for `86aff921a003044d1bf98ce525176c8666cccca71706f1a35d62b21dff68ee20`. No Mac browser receipt supplied. |
| Rolling-calendar/status/documentation candidate | Uploaded Mac receipt 153313: 289/289 units in 57 files and production/PWA builds passed; 468/471 browser cases passed. Three remuneration-width checks failed (desktop/tablet 120.234375px against 120px, phone 114.234375px against 112px). Candidate `2aaa8eb1ad6612c5439f8b20e02be15ef3d59f7dc284fdaf0283ff6cf273ebba` remains uncommitted; the installer stopped before final code health. |
| Compact-dashboard candidate | Uploaded Mac receipt 155743: all gates passed, 289 units / 57 files and 471 browser cases, root/Pages builds, PWA verification and code health. Fingerprint `54e58d9fc4cb10ef1af6d1c7a4fa840eba0da298028191a8bae394761f340f0f`; HEAD/tree/index remained unchanged. |
| Renewal and service review candidate | Adds the single package-threshold reminder, legacy demo-message migration and regression coverage; corrects Message timestamp/filter timezone wiring and strengthens independent adapter checks. Its installer records the exact fingerprint and verification results. Browser execution is unavailable in this workspace; discovery is not execution. Full Mac/CI browser execution and physical acceptance remain required. |

The required gate is **297/297 unit tests in 58/58 files; root and repository-path builds with PWA verification; 474/474 browser cases, 158 each on desktop Chromium, phone WebKit and tablet WebKit; source integrity and code health**. The increase adds eight renewal unit scenarios and one renewal browser scenario across the three existing projects. CI and the installer use the same exact result verifier. Inventory/discovery is not execution. Failed, skipped, flaky, retried, interrupted or incomplete tests are not green. Historical failures were repaired with regression coverage; their intermediate failure logs do not certify later source.

Keep the original 40 M2 unit scenarios and 150 M2 browser cases within the growing suite. Preserve behavioural assertions; do not make a gate pass by skipping cases, raising retries or concealing failures.

### Mac setup and local operation

Use the existing `~/Desktop/FitfinityReact` checkout. Do not rerun historical M3-based installers on a newer HEAD, reset the tree or replace the lockfile. Current dependencies require Node 20.19+ or 22.12+, or a supported newer release; CI uses Node 24.

```bash
cd "$HOME/Desktop/FitfinityReact"
node --version
npm --version
git --no-pager status --short --branch
```

For a fresh checkout, or when the locked dependencies need installing:

```bash
npm ci
npx playwright install chromium webkit
```

To inspect the app manually, run `npm run dev -- --host` and open Vite's printed Local/Network URL. Demo accounts appear in the sign-in dropdown; their initial password is `FitfinityDemo1!`, unless changed locally. Password controls require HTTPS or localhost. Use sample records and demo passwords.

For a production preview, stop other Vite servers, run `npm run build`, then `npm run preview -- --host`. Mac localhost supports service workers. A phone's ordinary HTTP LAN URL establishes responsive behaviour only; physical PWA acceptance requires trusted HTTPS.

### Full gate, installer behaviour and failure handling

Keep preview port 4173 free. Run the latest revision-specific installer from Downloads, outside the repository, against the exact source it recognises. Its filename and accepted base belong to that delivered revision; obsolete M4.3 installer commands are not a safe update path.

The installer must validate repository/branch/HEAD, index state and every recognised baseline byte before editing; reject unknown or mixed source without overwriting it; retain named test logs and the final fingerprint; verify exact totals, protected files, imports, CSS and new-file whitespace. It may accept a complete recognised rerun after a failed gate. It must not reset, stash, stage, install dependencies, start the development server, commit, tag, push or publish automatically.

The equivalent application gates, with retained logs, are:

```bash
cd "$HOME/Desktop/FitfinityReact"
set -euo pipefail
unset NO_COLOR NODE_DISABLE_COLORS
export FORCE_COLOR=1 CLICOLOR=1 CLICOLOR_FORCE=1
export GIT_PAGER=cat PAGER=cat
FITFINITY_REPORT_DIR="$(mktemp -d "${TMPDIR:-/tmp}/fitfinity-gates.XXXXXX")"
npm test 2>&1 | tee "$FITFINITY_REPORT_DIR/unit.log"
node scripts/verify-test-results.mjs unit "$FITFINITY_REPORT_DIR/unit.log"
npm run build
CI=1 PLAYWRIGHT_FORCE_TTY=0 npm run test:e2e -- --reporter=list 2>&1 | tee "$FITFINITY_REPORT_DIR/browser.log"
node scripts/verify-test-results.mjs browser "$FITFINITY_REPORT_DIR/browser.log"
git --no-pager diff --check
```

`test:e2e` builds both `/` and `/FitfinityReact/`, verifies both generated PWA releases, then executes Playwright; it does not run unit tests itself. The installer additionally supplies candidate integrity/code-health checks. `set -euo pipefail` makes a failed command stop the sequence even through `tee`: a unit failure means subsequent builds/browser execution did not run.

On failure, preserve the applied source, error and report directory; repair the canonical owner and rerun the applicable complete gate. Do not clear browser data or reset the checkout as routine recovery. Print `=== COMPLETE — ALL GATES PASSED ===` only after every required gate passes. A commit/tag/push requires authorization for that release.

### GitHub Pages demo release

The repository workflow is [`.github/workflows/pages.yml`](../.github/workflows/pages.yml), named **Verify and publish the staff demo**. In [Pages settings](https://github.com/LimYouSheng/FitfinityReact/settings/pages), select **Build and deployment → Source → GitHub Actions**. Review and commit only the intended verified source; generated `dist/`, `dist-pages/`, dependencies, environment files and test reports stay out of Git. Do not rerun an installer requiring the pre-commit HEAD afterward.

The workflow runs on `main` pushes or manual dispatch:

1. On macOS 15 / Node 24, install locked dependencies and enforce the exact unit gate.
2. Install Chromium/WebKit; build and validate root/subpath PWA releases; enforce the full browser gate.
3. Read Pages metadata, set `FITFINITY_BASE_PATH`, build for that directory and verify its PWA files.
4. Upload complete `dist/`; the dependent deployment job publishes only after verification succeeds.

Actions are pinned to commits. Build permissions are `contents: read` and `pages: read`; deployment uses `pages: write` and `id-token: write`. Inspect the relevant failing step in [Actions](https://github.com/LimYouSheng/FitfinityReact/actions). If Pages was enabled after a failed push-triggered run, configure the source and rerun the workflow.

An observed HTTPS push failure rejected `.github/workflows/pages.yml` because the classic Personal Access Token lacked `workflow` scope. For that specific error, update the authenticated token's scope before retrying the reviewed push; changing application source does not resolve it. Do not put tokens in scripts, URLs, documentation or Git.

Use the successful deployment's URL; with the current repository name and no custom domain it is [Fitfinity staff demo](https://limyousheng.github.io/FitfinityReact/). A deployment checkpoint is not the final M4 freeze. Finish the current candidate's automated and physical acceptance before freezing M4.

### Physical acceptance record

All rows below remain pending for the current candidate. Record the **device, OS/browser, date, HTTPS URL, commit, candidate fingerprint, action and actual result** for owner and at least one trainer. Preserve any failed case as unresolved until rechecked.

| Area | Required physical checks | Result |
|---|---|---|
| Calendar | Both roles and modes; rolling seven-day navigation; 28/29/30/31-day months and year/leap boundaries; weekday alignment and empty dates without actions; top-right mode buttons and period arrows with no date picker; past-day readability and clickable populated dates; Today even when empty; full trainer rows/status and grouped owner popups; Close/Escape/Back/Forward and retained mode/date. | Pending |
| Account / owner profile | Bad password, loaded requirements, invalid drafts, change password, dirty Sign Out cancellation, sign out/reload, expiry/deactivation; read-only owner name/role/status and Back. | Pending |
| Signatures / progress | Finger/stylus/mouse, blank blocked, clear/redraw, review/cancel/save/reopen; date guards; at most one credit debit; no-show without signature; numeric plans and explicit outcomes in charts/CSV; corrected/older signed records without duplicate points. | Pending |
| Onboarding / Packages | Section-by-section validation, Back/Edit and confirmation without duplicate creation; independent frequency; integer count 1–365; invalid formats rejected; proportional validity and purchased snapshots preserved. | Pending |
| Renewals / Messages / requests | One reminder at two sessions remaining, no duplicate after retry/correction/reload, read/unread and owner/assigned-trainer scope; total and up-to-three compact previews; gym-timezone category/search/date filtering and related-record Back; old/new approval details; stale time requests rejected at confirmation and approval, while rejection remains possible. | Pending |
| Report action history | Owner-only per-client history, owner/trainer names and gym-local timestamps; paging, empty/history reload, blocked popup, failed-save retry without relaunch, no trainer history access or General Information renewal controls. | Pending |
| Sessions / remuneration | Upcoming default and nearest-first order; All descending across statuses with filters retained; separate client history; compact Show/Hide amounts with visible focus; one pay row per session and stale-safe approval. | Pending |
| Navigation / layout | Initially collapsed desktop/tablet/mobile groups, independent click/tap/Enter/Space, hidden links out of tab order, destination reveal, resize/account reset; long names, no overflow; shared profile row from 700px and menu below. | Pending |
| Back / modal / keyboard | Client History page 2 → Session → Back restores tab/page/scroll; trainer nested navigation, filters and selected progress exercise survive Back/Forward/reload; focus enters/stays/returns, background scroll locks, virtual keyboard leaves Save/Cancel usable, drafts survive cancelled exits. | Pending |
| Content / media | Owner safe-text create/preview/save/edit/archive/search, trainer denied; browser-local attachment/capture/playback, replacement failure and quota/codec/storage limitations recorded separately. | Pending |
| PWA install / offline | Trusted HTTPS installation/Add to Home Screen, icon/splash/standalone/dashboard; after an online install, go offline and fully reopen a previously unvisited hash route. Check Android detail Back and dashboard exit, real swipe feel and airplane mode. | Pending |
| PWA update / recovery | Old build open in browser and standalone; publish complete new build; preserve active edits while update waits; close all app windows and reopen to activate; failed update/network loss retains usable release and reconnect/retry works. | Pending |

Browser PWA tests use real production bundles and isolated localhost origins at both base paths. They cover fresh-tab offline document loading, full shell caches, private-response exclusion, waiting updates across two tabs, local-data retention, owned-cache cleanup and failed-update recovery. An origin outage blocks all responses and verifies uncached API failure; Chromium also uses Playwright offline mode. WebKit uses the origin outage because its earlier emulated offline reload errored internally. This does not prove OS installation or physical offline behaviour.

Hardware-keyboard tests use nonmobile/nontouch contexts; macOS WebKit uses Option-Tab/Shift-Option-Tab, other cases use Tab/Shift-Tab. Exact focus and hidden-link assertions remain separate from touch coverage. These tests do not certify a physical iPad keyboard.

### Deferred and undecided scope

Public website publishing, website-specific Content Management and Glofox member access are deferred until the staff portal is finished. Verify Glofox account/API entitlement, supported login methods and fees before integration. Generic staff content editing does not publish public pages.

Owner Profile remains a read-only view of existing account data; editing fields are unspecified. Additional Setup pages, existing-client renewal/purchasing eligibility, payment/overlapping-package rules and a Copy Previous Plan UI are undecided. Existing service methods do not establish those UI requirements. Session filming is partial; physical capture and production processing remain open. Do not invent rules or claim these scopes complete.

## Production Architecture

### Ownership, hosting boundaries and initial AWS option

Fitfinity/Chau owns the AWS account and billing, with root MFA and delegated IAM access. Primary business services/data belong in Singapore (`ap-southeast-1`). The operational audience is the owner and roughly ten or more trainers. Keep dedicated staff, public website and later member access boundaries; authentication identifies a person, while server authorization grants role/record access.

| Layer | Initial production design |
|---|---|
| Web edge / frontend | HTTPS/DNS, CloudFront and AWS WAF; S3-hosted static React/PWA assets behind CloudFront. Staff portal has its own origin when public/member services are added. |
| Identity | Cognito for owner/trainer authentication; backend checks active status, roles and record relationships on every read/write. |
| API / compute | Stable API hostname and contract; API Gateway HTTP API → Lambda as the low-cost starting option. |
| Database | Private, encrypted RDS PostgreSQL Single-AZ; automated backups, point-in-time recovery, deletion protection and final-snapshot policy. |
| Media | Private S3 stores durable bytes; PostgreSQL stores media IDs/metadata. API authorizes uploads/playback before protected API or CDN delivery; private media never becomes a public static asset. |
| Operations | Least-privilege IAM, managed secrets/configuration, CloudWatch logs/alarms and budget alerts. |

Inherited planning target: **roughly S$60–100/month, aiming below S$100** where practical; the previously communicated roughly S$200 provides headroom. These are planning figures, not current quotations. Recheck sizing, regional pricing, network/egress and any Glofox charges before deployment. Preserve isolation, authentication, backups and monitoring when choosing costs.

Do not add ALB, always-on containers/EC2, NAT Gateway or Multi-AZ solely for hypothetical scale. Resolve private database connectivity, Lambda database connections, external API access and their cost before implementation; the budget does not prove those network paths are free or already configured.

### Portable application and infrastructure upgrade

Build **one canonical stateless, container-compatible backend** with API/controller, domain/service, authorization and repository boundaries. Put AWS-specific adapters at the deployment boundary. Business rules must not spread across Lambda handlers.

PostgreSQL owns durable business state, S3 owns durable media, Cognito owns identities and managed storage owns secrets. Never depend on one process, local compute disk or Lambda `/tmp` for durable workflow state. Keep stable API contracts/hostname and infrastructure-neutral migrations. Preserve transactional credits/progress, atomic approvals, saved remuneration evidence, stale-write checks and retry-safe mutations.

When requirements justify it, move **API Gateway/Lambda → ALB + Auto Scaling/EC2**, with at least two application instances across availability zones. Upgrade RDS to Multi-AZ and expand private networking/NAT as required by availability and egress design. Retain CloudFront/WAF, S3, Cognito, PostgreSQL and the frontend API/media contract where appropriate.

This should be an infrastructure/deployment migration with minimal application redevelopment. Record any deliberate departure before building a conflicting backend. These are future architecture choices, not infrastructure already provisioned by the staff demo.

### Backend phases and authoritative responsibilities

| Phase | Required work and preserved behaviour |
|---|---|
| M5 | Authentication/session lifecycle, `/me`, server principal and role/record authorization, database migrations, managed configuration, authoritative gym clock and error mapping. Decide authenticated offline-data handling and online-only mutations before using live data. |
| M6 | API adapter for the exported service operations; authorized queries/pagination, transactions, conflict/version checks, idempotent creation/completion/report history, immutable purchased terms and remuneration approvals, protected media upload/download. Run existing scenarios against that adapter; explicitly migrate any demo data worth retaining. |
| M7 | Durable events and scheduled notification creation/recipients, protected cloud media validation/transcoding/captions/delivery, appropriate processing retries and cleanup. Define any real WhatsApp integration separately from browser handoff logging. |

The API supplies canonical amounts, authorization and timestamps; browser roles, legacy actor arguments and client clocks are not authority. Enforce time-change constraints again at mutation/approval time, package bounds/validity, one-credit completion, progress corrections, report-history idempotency and media ownership. Translating the existing contract reduces UI rewrites; it does not make the backend automatic or complete.

Future member instructional access must verify current membership eligibility separately from staff privileges. Reuse the canonical exercise catalogue, distinguish instructional videos from private client session recordings, and grant private playback only after backend authorization. The concrete Glofox integration has not been verified for Chau's account.

### PWA release, caching and production hosting

[`vite.config.js`](../vite.config.js) derives the generated worker revision from the deployment directory, worker template and every published static file: HTML, hashed JS/CSS, icons, logo and manifest. Vite's resolved base controls assets, registration and worker scope; the manifest uses relative IDs, icons and launch URLs. Hash routing keeps detail URLs in the same document without server rewrites.

- Local builds default to `/`; `FITFINITY_BASE_PATH` selects a directory. Pages takes its actual directory from metadata; `/FitfinityReact/` remains the representative subpath test case.
- Install fetches the complete shell with HTTP-cache revalidation bypassed. Any failed resource rejects installation and leaves the working worker active. An active worker serves its matching HTML/assets together.
- New workers wait until **all** existing Fitfinity browser tabs and standalone windows close. Save/cancel edits, close all windows and reopen; reloading one tab while another remains open does not activate the waiting release. No forced activation or automatic reload interrupts drafts.
- Worker registration bypasses HTTP cache for `sw.js`. Activation removes only old `fitfinity-react-shell-<encoded app directory>-*` caches; other app directories, legacy unscoped caches, localStorage and IndexedDB remain intact.
- Only the app-directory document and explicitly built static assets are cached. API/auth paths, query URLs, POSTs, range requests, remote content and runtime uploads are excluded. Private media must never be placed in `public/`.
- Publish the **complete generated `dist/`**, including generated `dist/sw.js`, as one release. Never substitute the unexpanded `public/sw.js` template. Production hosting must revalidate the worker and retain previous hashed bundles across rollout; the Pages demo workflow does not configure those production controls.

Offline support currently means reopening an installed shell and continuing browser-local demo records. It does not implement offline authentication, reliable camera capture, queued backend writes, cloud uploads or multi-device sync. An offline first visit cannot install the app; browser storage may be evicted. Reconnect and revisit to recover; routine storage clearing destroys local demo records/media.

For an explicit subpath production preview:

```bash
FITFINITY_BASE_PATH=/FitfinityReact/ npm run build
npm run verify:pwa -- dist /FitfinityReact/
FITFINITY_BASE_PATH=/FitfinityReact/ npm run preview -- --host
```

Open the printed URL under `/FitfinityReact/`; use hosted HTTPS for physical device acceptance.

## Frontend Architecture

### Canonical owners and navigation

| Concern | Canonical source |
|---|---|
| Composition and routes | [`src/App.jsx`](../src/App.jsx), [`AppShell.jsx`](../src/components/AppShell.jsx) |
| Async snapshot/context | [`PortalDataProvider.jsx`](../src/components/PortalDataProvider.jsx), [`usePortalData.js`](../src/hooks/usePortalData.js) |
| Service factory / mock boundary | [`portalService.js`](../src/services/portalService.js), [`defaultPortalServices.js`](../src/services/defaultPortalServices.js), [`mockPortalAdapter.js`](../src/services/mockPortalAdapter.js) |
| Business rules / clock | `src/app/`, including [`clock.js`](../src/app/clock.js), [`calendar.js`](../src/app/calendar.js), [`sessionRules.js`](../src/app/sessionRules.js), [`packages.js`](../src/app/packages.js), [`progress.js`](../src/app/progress.js) and [`remuneration.js`](../src/app/remuneration.js) |
| Feature screens / shared UI | `src/features/`, `src/components/`, [`styles.css`](../src/styles.css) |
| History and view state | [`useAppNavigation.js`](../src/hooks/useAppNavigation.js), [`usePageState.js`](../src/hooks/usePageState.js), [`useSwipeBack.js`](../src/hooks/useSwipeBack.js) |
| Demo records / defaults | `src/data/`; browser persistence remains inside `src/services/`. |

Keep one navigation/history owner, edit guard, confirmation provider, notification provider and modal layer. Edit canonical owners in place and remove superseded implementations; no patch files, duplicate components, stylesheet override tails or backup artifacts. Code-health review covers selector usage, responsive rules, duplicate declarations/custom properties, imports and whitespace. Static checks complement browser coverage without proving every visual state.

`useAppNavigation` installs before first paint and owns account-scoped, per-history-entry view state. Tabs, searches, filters, page, selected progress exercise and scroll survive native/app/swipe Back, Forward and reload. Calendar and message routes carry the current view to related records. Editable drafts remain local and use the shared edit guard.

Navigation groups start collapsed on sign-in/reload/account change across desktop, tablet and mobile hamburger layouts. They toggle independently, remove hidden links from the tab order, reveal the destination's section and retain choices across responsive resizing. Profile/Message categories share `ProfileNavigation`: inline from 700px, selected-label menu below. Trainer client lists omit the redundant trainer filter while existing role scoping remains.

### Injected service contract and refresh lifecycle

`App` accepts `services`. Default composition is `defaultPortalServices → createPortalServices(mockPortalAdapter)`; the factory imports neither mock implementations nor seed data. Feature screens consume records, loaded policy and async callbacks. The default composition import belongs in `PortalDataProvider`; its module exports only the component for Fast Refresh. The single context and hook live in `src/hooks/usePortalData.js`.

| Adapter method | Contract |
|---|---|
| `load()` | Promise of `{user, policy, capabilities, data}`; `user: null` means signed out. Only the demo adapter additionally provides `accounts` and `demoPassword`; an API adapter uses the account text field. |
| `session(method, args)` | `signIn`, `signOut`, `changePassword`; demo additionally implements `switchDemoIdentity`. Successful sign-out clears the displayed private snapshot immediately. |
| `invoke(domain, method, args)` | Implements `PORTAL_OPERATIONS` in `portalService.js`. Return the canonical saved record/documented domain result; reject failed mutations with `Error`. |
| `reset()` | Demo capability only. `capabilities.demoControls` alone enables identity switching and reset UI. |

`PORTAL_OPERATIONS` is the authoritative operation list: clients and report history; trainers and availability; session planning/outcomes/summary/media; exercise catalogue/reference media; packages; generic content; Messages; request resolution; remuneration listing/detail/approval. All factory methods return Promises, including mock reads.

The M4 wiring review matched all 43 registered domain methods to implementations and checked all App action calls against the registry. No feature-level mock storage, seed data or direct HTTP bypass was found. Factory tests exercise argument/result forwarding and rejection identity for every operation. The assembled-app test uses an independent adapter/account to verify initial-load retry, sign-in, absence of demo controls, failed-save draft retention, canonical save/refetch and immediate sign-out clearing even when refresh fails. Existing feature tests cover the individual domain workflows. This verifies the frontend boundary; production still requires an API adapter, authenticated record scoping, transaction/idempotency rules, error mapping, protected media transport and server-authoritative clocks/calculations. Cognito/MFA challenge screens and production offline behavior remain later integration work.

Errors supply a readable `message`. `code: 'SESSION_EXPIRED'` clears private UI and returns to sign-in. Failed initial loads offer Retry; failed refreshes show a retry banner. A refresh failure after a committed save must not be labelled a failed mutation or encourage duplicate creation.

Focus, storage changes and a 30-second clock tick refresh the snapshot; generation checks discard stale overlapping responses. Events may replace polling later without changing screens. Production must authorize every read/write from its authenticated principal. Mock controls and browser storage are accessible to someone controlling the browser and do not provide production/Glofox authorization.

### Loaded records, policy and business clock

`data` provides visible `users`, `clients`, `trainers`, `sessions`, `messages`, `packages`, `exerciseLibrary`, `contentEntries` and `remunerationViews`. A production adapter must return only authorized records. Remuneration views contain `key`, `cycle` (start/end/payout) and canonical trainer breakdowns/totals/revisions; amounts are calculated behind the adapter, not independently by screens.

| Loaded policy | Purpose / current mock defaults |
|---|---|
| `timeZone`, `locale`, `currency` | Gym date/time and money presentation: `Asia/Singapore`, `en-SG`, `SGD`. |
| `packageSessionCount`, `packageValidity`, `packageValidityRule` | Integer limits 1–365; explicit 12/24/36 → 90/180/270 days; otherwise 90 days per 12 sessions, rounded up. |
| `renewal.remainingSessions` | Single reminder threshold; mock default is two sessions remaining. The service owns this rule, not a dashboard calculation or fixed package-size list. |
| `weeklyFrequencies`, `freeGymMinimumFrequency` | Independent weekly frequency 1–7; gym package included from two sessions/week. |
| `availability`, `defaultCountryCode`, `defaultRelationship` | Initial form drafts. |
| `trainerRates`, `trainerTypes`, `approvalDefaults` | Trainer onboarding and approval controls; saved trainer rates govern remuneration. |
| `exerciseCategories`, `exerciseDefaults` | Catalogue and planning drafts. |
| `password.minimumLength/maximumLength`, `sessionHours` | Loaded password length 12–128 and eight-hour mock sessions. |
| `remuneration` | Cycle ends on 15th, payout on 16th; configured weekend/peak windows. |

Use `businessClock` in the configured timezone; calendar dimming/highlighting and date guards do not use the viewer's local timezone or selected calendar date as today's authority. The UI's loaded clock supports immediate feedback; services independently recheck current time inside mutations. Production replaces browser-clock authority with its server clock.

Labels, routing keys, calendar arithmetic, supported media formats and validation bounds remain code. Missing records do not imply a default owner, exercise catalogue or purchased package. Demo records and defaults stay under `src/data`.

### Sessions, packages, approvals and remuneration

- **Lists/status:** New Sessions visits default to Upcoming, nearest first. All orders date/start time descending across statuses, then uses session ID as a stable tie-breaker. Back preserves explicit period/search/page. Client Session History is a separate view. Shared status mapping and `StatusBadge` display Not Planned, Planned or Completed with each calendar session.
- **Onboarding/packages:** Validate one section at a time, preserve Back/Edit drafts and save after final confirmation only. Session count is free text with numeric keyboard; form and service reject blank, decimal, signed, exponential and out-of-range values and store an integer. Review shows computed validity. Purchased package terms/version and existing schedules remain snapshots when templates change.
- **Approval semantics:** Checked **Owner approval needed** means no direct mutation. Pending changes preserve the underlying schedule; resolution is atomic and rejects stale records. Owner direct edits retain record-correction behaviour.
- **Time-change requests:** Original and proposed start must both be strictly later than gym time; completed/cancelled originals are unavailable. Validate before review, after confirmation and inside the service mutation. Owners cannot approve after either start passes, but may reject. Production must enforce the same rule with server time.
- **Date action guard:** `sessionActionError(session, today)` blocks signature/no-show completion and WhatsApp before the training date. UI and service check independently. Actions unlock on that gym-local calendar date, not at session start time.
- **Credit/progress:** A completed session debits one package credit at most; corrections never add another debit. Preserve past evidence and rebuild derived progress by session/result identity. No-shows do not contribute strength points.
- **Remuneration:** Use the saved trainer rates and Singapore session start time. Weekday peak windows are 06:30–08:30 and 18:00–20:30, ends exclusive; weekends are peak all day. Cycle runs 16th through next 15th. Owner approval starts at payout after cycle close, requires reviewable valid sessions/rates, rejects stale revision/already-approved cycles and saves the approved breakdown/evidence. Each session occupies one compact row; both roles have compact Show/Hide amounts controls.

### Dashboard calendar and Messages

Weekly uses exactly seven consecutive dates from the displayed period's start, initially today: Wednesday → Tuesday, with Next starting the following Wednesday. Previous/Next move seven days across month/year boundaries. Monthly uses day 1 through its last day, with Monday-based weekday alignment and blank spaces outside that month. There is no adjacent-month date content or single-date picker.

Owner Weekly/Monthly and trainer Monthly display nonzero counts labelled session/sessions and View day. Empty dates render only a date heading and blank tile, with no count/button/focus target. Trainer Weekly shows seven day sections and every compact time/client/status session row; headings open View day only when that day contains sessions. Empty trainer Weekly headings remain static with No sessions text. There is no preview cap, +more control or booking-capacity rule. Existing or restored day routes can still display an empty-state popup if the day's records have become empty.

Day actions open `#/dashboard/day/YYYY-MM-DD` through the existing navigation owner and `ModalPortal`, with scoped records and shared focus/scroll locking. Owner popups group sessions by trainer, chronological within each group; every popup row uses the same status presentation. Close/Escape/native Back/Forward preserve context; opening a session replaces the popup route so session Back restores calendar date/mode. No new calendar backend operation is required.

Past-day dimming uses `day < today` from the gym clock for both roles/views. Existing controls remain enabled and regain brightness on focus or hover-capable pointers; day popups remain full brightness. Today always has its label, stronger blue background and inset border, even when empty. Weekly/Monthly sit at the top right alongside the Calendar heading; period range/arrows form the next row on every screen size.

Oracle reference: `LimYouSheng/fitfinityPWA`, `assets/css/core.css`, blob `e6e956f75d8357256fe1ff2bc4aace1c44551ee8`. Canonical CSS retains its neutral grid `#0f1116`, session surface `#181b25`, blue `#4f67f6` and owner count treatment. Superseded preview-card/overflow/viewport-subscription implementations are removed.

`MessageInbox` in `MessagesPage.jsx` owns dashboard and inbox lists, dialogs, recipient visibility, related records, read/unread mutations and overlay history. Dashboard renewals preview at most three compact 44px rows, each with a single-line title and Read/Unread action. Long preview titles ellipsize visually; full accessible names, stored titles and popup details remain intact. Dates and request metadata stay in the popup/full inbox. The total counts all visible renewal Messages, including read items, before slicing. **View All Renewals** opens `#/messages/renewals`. Reading a Message does not settle a renewal; this is neither a distinct-client total nor a renewal-completion workflow.

Renewal Messages use only `kind: 'renewal'` with `renewal.type: 'last_sessions'`. A fresh package-credit debit creates the reminder when `total - used` equals the loaded threshold: 10/12, 22/24, 34/36, and the equivalent for other integer totals. 32/36 leaves four and does not trigger it. The same atomic save stores the debit, updated usage and reminder. Signatures and late/no-show consumption both count; retrying completion or changing its evidence does not debit or notify twice. A two-session purchase is already at the threshold when created; a one-session purchase never has two remaining.

Purchased `client.package.id` identifies the package instance, distinct from its template ID. Each reminder stores that ID plus its usage/total/remaining snapshot and creation timestamp, and addresses the owner and assigned trainer in one record. The existing reminder remains after subsequent usage reaches one or zero; read state and timestamps remain intact. A future purchase needs a new package-instance ID. Production should enforce uniqueness by package instance/event type and generate the event transactionally behind the adapter; the UI consumes the returned Messages.

Legacy local demo data migrates once using `renewalMessageVersion: 1`: generic package-review renewal rows are removed; current packages exactly at the threshold receive the canonical reminder. Matching eligible legacy rows retain their ID, timestamp and read state, and missing package IDs gain stable migration IDs. Persistence must succeed before migrated data is exposed. Unrelated Messages, sessions, report activity and existing renewal-tracking metadata are preserved. Fresh seed data uses the same canonical reminder builder, not generic renewal examples.

Adapters may provide category keys `renewals`, `approvals`, `sessions`, `people`, `remuneration`, `updates`. Otherwise `messageFilters.js` classifies typed kind/request/record metadata, never titles. Unknown kinds appear in Updates and All. Shared category navigation combines text/date filters and pagination; selecting categories does not mark read. Timestamp presentation and date filtering both use loaded `policy.timeZone`, including UTC instants crossing the gym's midnight. Failed read mutations keep the list usable with retry feedback. Server notification generation, recipients and complete query/pagination semantics remain backend work.

### Record contracts, signatures and report history

| Record | Contract |
|---|---|
| Client acknowledgement | `acknowledgement.signature` contains normalized SVG strokes of finite `{x,y}` points on a 600×200 surface, with bounded strokes/points. New signatures require drawn evidence; names alone are insufficient. Clear/review/reopen work; `late_no_show` has no signature. Preserve older records without fabricating ink. |
| Exercise results | `exerciseResults` contains stable plan-row `id`, `name`, measured `loadKg`, integer `reps` and `sets`. Signed completion snapshots numeric plan loads only when no separate outcome result list exists; an explicitly empty list remains empty. Blank/nonnumeric loads are not measurements. Completed attended results replace points by session/result; unlinked legacy points remain baseline. Mock loading also projects older signed sessions. |
| Generic content | `{id,key,title,body,status,version,createdAt,updatedAt}`; status `draft`, `ready` or `archived`; unique keys and `expectedVersion` for edits. Preview escapes text. These records do not define future public page templates. |
| Session WhatsApp | `whatsappOpenedAt`/`whatsappOpenCount` record launched handoffs only. Blocked windows expose a link without claiming delivery. Text exports do not attach video files or establish sent/read receipts. |

Only the owner sees **Progress → View Export/WhatsApp History**. Owner and assigned trainer may perform report actions. General Information retains no renewal controls; old renewal metadata is preserved without converting it into fabricated report events.

- `clientService.recordProgressReportAction(clientId, {id, kind})` returns `{id, clientId, kind, at, by:{id,name}}` and a saved-action Message. `kind` is `csv_export` or `whatsapp_opened`; the UI creates a unique action ID while the adapter derives actor/time.
- The same ID/client/kind/actor retry returns the original event without a new timestamp or Message; conflicting ID reuse is rejected. Failed validation, authorization or storage commits nothing.
- `clientService.progressReportHistory(clientId)` requires an active owner and returns that client's newest events first. Caller-supplied owner arguments cannot grant access. History stays out of ordinary snapshots/trainer UI; mock `progressReportEvents` storage is not a component dependency.
- Store ISO UTC instants and display with `policy.timeZone`; production uses its server principal/clock. Entries display ten per page with independent loading/retry. The read-only history view preserves Progress and the selected exercise and remains accessible when charts are empty.
- CSV means a download initiated by the app, not a saved-file receipt. WhatsApp means a successfully opened handoff window, not sent/read confirmation. Launch synchronously during the user action before the async history write; blocked/failed launches create no event.
- After launch, a failed history write offers **Retry History Save** with the same ID and never re-exports or reopens the report. Durable audit storage and real delivery receipts require backend work/integration.

### Account feedback and media persistence

Change Password uses loaded minimum/maximum length for validation and requirement notifications on New password focus or **Password requirements**. Invalid length, missing current password, mismatch or unchanged password notify before confirmation/service calls; no character-class rules are invented. The service verifies current password, session and each mutation; failures retain drafts. Shared compact banners communicate successful actions across content width, while field validation and retryable errors remain available. Static instructional paragraphs are removed where concise labels suffice.

`loadVideo`, `saveVideo` and `removeVideo` cross the service boundary. Mock session videos use immutable IndexedDB byte records; metadata commits only after durable local blob storage. Failed metadata writes remove only the new blob, preserving the previous attachment; old blobs are cleaned after commit. Cleanup failure may leave an unreferenced blob but must not create a broken replacement. Abortable preparation and cleanup remain in the canonical media owners.

Current validation accepts nonempty video files up to 5 MiB (UI label 5 MB) and normally requires a readable positive duration no longer than 60 seconds. Unsupported local processing may retain the original with processing marked deferred; WebKit fallback can retain audio/unknown duration. This is not proof of final production media compliance. Unsupported capture/storage and quota errors must surface without committing metadata for missing bytes.

An API adapter should return media IDs and retrieve Blobs from protected endpoints; metadata is not the payload. Production must validate, transcode/caption where required, authorize private storage/playback and handle processing/cleanup failures. Browser storage may be evicted; cloud media and physical-device capture acceptance remain separate from the working local demo.
