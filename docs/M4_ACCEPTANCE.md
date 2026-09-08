# M4 staff portal acceptance record

Status: **M4.3 Pages readiness candidate; M4.2E Mac gate passed. M4.3 Mac/browser, hosted-device acceptance and final M4 freeze pending.**

## Automated evidence

- Baseline: M3 `7d114a1`, tag `m3-operations-frontend`, 159-file fingerprint
  `9648fe7a4801b90ef947d47bd2a009ff4396966420c55b0261afeb174d983ba6`.
- Candidate receipt: use the fingerprint printed by the M4.3 installer, including
  README, docs, public files, configuration, source and tests.
- Required gate: 264/264 unit tests (54 files), root/repository-path builds and PWA verification, 432/432 browser cases
  (144 per configured desktop Chromium, phone WebKit and tablet WebKit project), then integrity/code health.
- M4.1A Mac run (2026-09-07): 219/219 unit tests and build passed; 367/372
  browser cases passed. Three failures were the PWA test's Back expectation;
  two were WebKit internal errors during an emulated offline reload.
- M4.1B Mac run: passed 219 unit tests / 48 files, build, 372 browser cases and integrity/code health (uploaded 2026-09-07 receipt).
- M4.2 workspace: 243 unit/component tests / 53 files passed; production build passed. Complete browser execution is unavailable here.
- M4.2 Mac run (uploaded 2026-09-07): 243/243 unit tests and build passed; **375 passed / 18 failed out of 393 browser cases**. The run stopped at the browser gate.
- M4.2A workspace: 247 unit/component tests / 54 files passed; production build passed.
- M4.2A Mac run (uploaded 2026-09-07): 247 unit tests / 54 files and build passed; **401 passed / 1 failed out of 402 browser cases**. Failure: expected next-header focus after Tab in the iPad touch context.
- M4.2B workspace: 252 unit/component tests / 54 files passed; production build passed.
- M4.2B Mac run (uploaded 2026-09-07): 252 unit tests / 54 files and build passed; **411 passed / 3 failed out of 414 browser cases**. Failures: phone compact-month session access and both WebKit hardware-keyboard focus checks.
- M4.2C workspace: 255 unit/component tests / 54 files passed; production build passed.
- M4.2C Mac run (uploaded 2026-09-07, 120930 receipt): **all gates passed — 255 unit tests / 54 files, build, 420 browser cases, integrity/code health**, candidate `e5b553501cbc8ae74259f87f1277dc549786262d0a0fffb877733920eca76317`.
- M4.2D workspace: **257 unit/component tests / 54 files and production build passed**. Browser inventory is 423 cases; full browser execution is unavailable here.
- M4.2D Mac run (uploaded 2026-09-07, 123328 receipt): **255 passed / 2 failed out of 257 unit tests**. Both failures were five-second timeouts in assembled calendar scenarios. The script stopped at FULL Vitest; build and browser execution did not start. Applied candidate: `f267d0a2d54dfdd09d9663f2e1faff684ffdb22a0e05d5641db01ae20835fc00`.
- M4.2E workspace: **257 unit/component tests / 54 files and production build passed**. Calendar button queries use their explicit accessible labels and native button selector; mode controls are scoped to their group. An initial full workspace run passed those calendar cases but exposed a signature-scenario timeout; its queries are now scoped to the signing dialog. The default timeout and every behavioral assertion remain.
- M4.2E refresh check: the installed plugin runtime reproduced the mixed-hook export warning and accepted the actual reevaluated component-only provider exports. This is module/runtime verification, not a live browser HMR test.
- M4.2E Mac run (uploaded 2026-09-07, 125144 receipt): **all gates passed — 257 unit tests / 54 files, build, 423 browser cases, integrity/code health**, candidate `89de2e49de4a68a3b4466f9fd6e1698ef749bf40853ded32e0a802e6ed5da6e4`.
- M4.3 workspace: 264 unit/component tests / 54 files passed. PWA scenarios now cover both `/` and `/FitfinityReact/`; browser inventory is 432 cases / 15 files. Full browser execution is unavailable here. The installer and CI reject failed, skipped, flaky or incomplete test gates.
- M4.3 Mac full gate and first GitHub Actions deployment: **pending user run**.
- Actual physical-device results: **pending**.

The sidebar keyboard scenario explicitly uses `isMobile: false` and `hasTouch: false` in each project for hardware-keyboard traversal. On macOS WebKit it now uses Option-Tab and Shift-Option-Tab; Chromium and other platforms use Tab and Shift-Tab. Exact next/previous-header focus and hidden-link assertions remain. The touch-device sidebar scenarios remain separate. This does not establish physical iPad keyboard behaviour.

The browser PWA tests use the real production bundle on isolated localhost origins.
At both root and repository paths, they exercise offline reopening, complete shell caching, private-response exclusion,
waiting updates across two open tabs, retained local data, owned-cache cleanup,
and failed-update recovery. The outage fixture cuts all responses from its origin
and checks that an uncached API request fails before and after loading cached HTML,
JavaScript and CSS. Chromium also uses Playwright's offline switch. WebKit uses the
origin outage without that switch because the M4.1A Mac run errored inside reload
with it enabled; this is not evidence that WebKit's emulation or physical offline
mode is fixed. The reopening test creates a fresh tab, so a hash-only navigation
cannot pass as an offline document load. These checks do not emulate an OS
installation or prove physical airplane-mode behaviour or finger-swipe feel.

## Physical acceptance checklist

Record device/OS/browser, production URL, build fingerprint, date and result for each row.
Test the owner and at least one trainer with local demo data.

| Area | Action and expected behaviour | Result |
|---|---|---|
| Calendar | Weekly/monthly periods, date jump, prominent View day action, five-session previews and +N more opening all sessions (also visible in compact phone month), tap-date session popup, close/native Back/Forward, grid session links and Back retain context; trainer records scoped. No separate daily agenda or Today button. | Pending |
| Account | Sign in, reject bad password, show loaded password requirements in notifications, reject invalid drafts without losing them, change password, dirty Sign Out cancellation, sign out/reload, expire/deactivate session. | Pending |
| Client signature | Finger/stylus/mouse drawing; blank blocked; Clear/Redraw; review/cancel/save/reopen; one credit debit on repeat completion; late/no-show without signature. | Pending |
| Content | Create, preview safe text, save, reopen/edit/archive, search/status filters; trainer denied. | Pending |
| Measured progress | Enter load/reps/sets, complete session, inspect chart and CSV, correct result without duplicate point/debit. | Pending |
| Owner profile | Open from profile menu; name/role/status visible; native Back returns to the previous page. | Pending |
| Onboarding | Add Client/Trainer, revisit sections, edit from Review, cancel confirmation, then confirm once. Draft retained; no duplicate creation. | Pending |
| Packages | Check four-field onboarding row; independent frequency; 12/24/36 session definitions and action gaps. | Pending |
| Dashboard renewals / category filters | Prominent full follow-up count, unchanged by marking read; zero state and trainer scoping; up to three renewal Messages above calendar; open/read/unread/related record/Back; View All Renewals keeps category after reload. Shared client/trainer navigation (row from 700px, selected-label dropdown below) combines with text/date filtering and resets pagination; no page overflow. | Pending |
| Approvals / Messages | Inspect old/new details and record links; cancel/approve/reject; pending indicators and read/unread state remain correct. | Pending |
| Remuneration | Eye control at top right on phone; one compact session row; approval confirmation and stale protection. | Pending |
| Sidebar sections | All groups initially collapsed at sign-in/reload/account change; desktop/iPad fixed menu: independently collapse each group by click/tap/Enter/Space; hidden links leave tab order; destination group opens on navigation. At 780px and below, hamburger groups stay expanded. Resize both ways and switch account. | Pending |
| Layout | Phone, real iPad and desktop: long names wrap; controls fit; profile dropdown below 700px and inline navigation from 700px. | Pending |
| Modal / keyboard | Modal scrolls; background is locked; focus enters/stays/returns; virtual keyboard does not trap Save/Cancel. | Pending |
| Back / swipe | List → detail → nested flow, native Back/Forward and edge swipe; edit cancellation preserves draft. Android detail Back returns within app. | Pending |
| Installation | Trusted HTTPS; install/Add to Home Screen; icon, splash, standalone launch and dashboard entry. | Pending |
| Offline reopen | Open online until installed; go offline; fully reopen and visit a previously unvisited hash route. App shell and local demo records render. | Pending |
| Update | Open an old build in browser and standalone mode; publish full new build; reopen/check for update; existing edit remains intact. Close all app windows, reopen, verify new build. | Pending |
| Failure / retry | Failed update or temporary network loss leaves the working release usable; reconnect and retry. No need to clear all browser data. | Pending |
| Media | Browser-local attachment playback remains usable where supported; record capture/codec/storage limitations separately. | Pending |

Also check Android hardware Back at the dashboard and record any premature app exit
as unresolved. Ordinary browser tests do not establish the physical OS/PWA behaviour.

## PWA release and offline contract

- `vite.config.js` derives the worker revision from the deployment directory, worker template and every
  published static file, including HTML, hashed JS/CSS, icons, logo and manifest.
- Install fetches the entire listed shell with HTTP-cache revalidation bypassed.
  A failed resource rejects installation; a working active worker is retained.
- The active worker serves its own matching HTML/assets. It does not mix a newly
  fetched document with an older cached shell.
- New workers wait until all existing app windows close. There is no automatic
  reload or forced worker activation during a draft. Registration checks bypass
  the HTTP cache for `sw.js`; long-running windows receive changes on later checks/reopening.
- Activation deletes only old `fitfinity-react-shell-<encoded app directory>-*` caches. Other app directories and legacy unscoped caches are retained. It does not clear
  other CacheStorage namespaces, localStorage or IndexedDB.
- Only the app-directory document and explicitly built static assets are cached.
  API/auth paths, query URLs, POSTs, range requests, remote content and runtime
  uploaded media are not cached by this worker. Private media must never be placed in `public/`.
- Offline support here means reopening the shell and continuing the existing local
  demo. It does not mean offline authentication, reliable camera capture, cloud
  uploads, queued backend mutations or multi-device sync. M5 must define authenticated
  offline data handling and online-only mutations before live data is introduced.
- Browser storage can be evicted; an offline first visit cannot install the app.
  On reconnection, revisit to install/recover. Avoid clearing site storage as a routine
  update mechanism because that removes browser-local demo records and media.
- Publish the complete generated `dist/` as one release. Pages is a demo acceptance host; its deployment directory is read from Pages metadata. Root deployment remains the default for a future dedicated staff origin.
- Production hosting must support worker revalidation/no-cache and retention of previous hashed bundles across rollout. This workflow does not configure custom cache headers or old-bundle retention on Pages; those remain production hosting requirements. See [GITHUB_PAGES.md](GITHUB_PAGES.md).

macOS WebKit keyboard-test reference: [Playwright discussion #5609](https://github.com/microsoft/playwright/issues/5609).

Service-worker lifecycle reference:
[MDN: Using Service Workers](https://developer.mozilla.org/en-US/docs/Web/API/Service_Worker_API/Using_Service_Workers).

## Accepted boundaries and open work

The user has deferred the public website, website Content Management and Glofox member
access until the staff portal is finished. Before that integration, verify account/API
entitlement, supported login methods and any vendor fees with Glofox. Keep future
member identity and eligibility separate from owner/trainer permissions. Use a dedicated
backend adapter and private-media delivery; do not duplicate the staff exercise catalogue.

Owner Profile is a read-only view of existing account data. Additional fields/editing
remain unspecified. Mock password change and sign-out are implemented; production auth is M5. Session filming
remains partial and production media is M7. No additional Setup pages are included.

A final M4 record requires reconciled scope, this device evidence and the full green
candidate gate. Commit/tag/push requires milestone authorization in the active session;
this routine readiness installer performs none of those actions.
