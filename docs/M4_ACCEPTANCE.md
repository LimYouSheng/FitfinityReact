# M4 staff portal acceptance record

Status: **M4 deployed at de257440 (deployment success reported by user). Physical testing found the issues below; the report-history repair passed its full Mac gate. The previous calendar candidate passed 470/471 browser cases. This Oracle calendar replacement requires its own full Mac browser gate and physical check. Final M4 freeze remains pending.**

## Automated evidence

- Baseline: M3 `7d114a1`, tag `m3-operations-frontend`, 159-file fingerprint
  `9648fe7a4801b90ef947d47bd2a009ff4396966420c55b0261afeb174d983ba6`.
- Candidate receipt: use the fingerprint printed by the latest calendar installer, including
  README, docs, public files, configuration, source and tests.
- Required gate: 289/289 unit tests (57 files), root/repository-path builds and PWA verification, 471/471 browser cases
  (157 per configured desktop Chromium, phone WebKit and tablet WebKit project), then integrity/code health.
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
- M4.3 and follow-up media/client-refresh Mac gates: **264 unit tests / 54 files and 432 browser cases passed**. Latest deployed source: `de257440787b88470d4ee096115abb9df2061acf`, fingerprint `d32f6ede6bee04bcdaedc585ee8d883860507c7bd018901ef63b3eea05cdd906`.
- Physical testing (2026-09-08) reported: redundant trainer filter; Back losing client-history tab; completion missing strength progress; future signature/WhatsApp actions; fixed package-count choices; mobile sections needing collapse.
- Physical repair workspace: **275 unit tests / 55 files passed**; browser inventory is **462 cases (154 per project)**. The subsequent Mac result is recorded below.
- Physical repair Mac run (074801 receipt): **275/275 units in 55 files passed; 446 passed / 16 failed browser cases**. Candidate `5aab54801d3f7f53a48b5f618987b260e282e8774286a74ee43e06b69c0fb855` remains uncommitted. Failures exposed fixture updates after app startup, stale clock state after hash navigation, a pristine-editor discard expectation, the mobile helper leaving its drawer open, and an obsolete six-exercise expectation.
- Follow-up repairs seed the complete browser snapshot before startup, trigger the normal focus refresh after changing the test clock, dirty content before testing discard, restore the helper's original drawer state, and assert all nine fixture exercise names. No cases are skipped and no retries or timeouts are increased.
- Renewal tracking adds six service cases, one assembled-app case, and two scenarios on all three browser projects. Required total: **282 unit tests / 55 files; 468 browser cases (156 per project)**. This workflow was subsequently superseded by owner-only report action history.
- Renewal follow-up Mac run (081401 receipt): **282/282 units in 55 files passed; 456 passed / 12 failed browser cases**. Candidate `c1730b69e9f457644f8b724990bcdcbec97a0064141b398aa1236351f53b5644` remains uncommitted. Failures: mismatched DOM text APIs in the Back assertion, an unrelated-trainer access expectation, contact-row count after adding renewal fields, early calendar input, and unnecessary mobile drawer close/reopen steps.
- User removed the manual renewal workflow. General Information returns to its original eight information rows. Owner Progress now displays timestamped CSV export / WhatsApp-open actions, including assigned-trainer activity. Six service and one app renewal cases were replaced with action-history coverage; four focused report UI cases and one first-frame navigation case were added. Two renewal browser scenarios were replaced by three history scenarios. **287 units / 56 files pass; 471 browser cases are required.**
- Navigation installs its history owner before first paint, protecting early calendar selections. The browser Back assertion consistently compares textContent; navigation helpers leave the drawer open while using its links and close inspection-only drawers in the exposed center area. No timeouts/retries were increased and no tests skipped.

- Report-history Mac run (083541 receipt): **all gates passed — 287 units / 56 files, root/Pages builds and PWA checks, 471 browser cases, integrity/code health**. Candidate `ddebf8a2aee5d031293b11bd5f42050053198a405e144f4af14e1ca24a84ddf3`; deployed HEAD/tree/index unchanged and local source still uncommitted.
- Previous calendar candidate `231d9c58efe32ba26a0f6eed909bac0d4f2d6099a74d1be7f744955448c7d9a7` passed **289 units / 57 files** in this workspace. Mac run (130708 receipt) passed those units and builds, then **470/471 browser cases**. The desktop exercise rename/deactivation scenario timed out waiting for the Exercise status filter after cancelling the session plan. This is not a green receipt and the final code-health gate did not run.
- That browser scenario now explicitly waits for the plan's read view and released edit lock before changing the hash, then asserts the destination heading. No timeout, retry or skipped-case changes were made; the underlying exercise mutation assertions remain.
- The user superseded the preview-card layout: owner Weekly/Monthly and trainer Monthly now show only counts with day popups; trainer Weekly shows all sessions in compact rows grouped by day. Owner popups group sessions by trainer. Canonical Oracle count styling replaces the previous styling, and preview limits, overflow controls and viewport-subscription code are removed.
- Existing calendar unit and browser cases were rewritten for counts, empty days, every weekly row, trainer grouping, role scoping, popup completeness and retained Back state. **289 unit tests / 57 files pass in this workspace; 471 browser cases still require full execution on Mac/CI.**



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
| Calendar | Oracle count styling; owner Weekly/Monthly and trainer Monthly have seven-column count grids; tap a number (including zero) for a complete day. Owner popup groups by trainer. Trainer Weekly shows every session in one compact time/client row, grouped by day. No previews or +more. Check both roles on phone/tablet/desktop, period/date changes, Close/Escape/native Back/Forward and session Back retaining date/mode. | Pending |
| Account | Sign in, reject bad password, show loaded password requirements in notifications, reject invalid drafts without losing them, change password, dirty Sign Out cancellation, sign out/reload, expire/deactivate session. | Pending |
| Client signature | Finger/stylus/mouse drawing; blank blocked; Clear/Redraw; review/cancel/save/reopen; one credit debit on repeat completion; late/no-show without signature. Signature and WhatsApp blocked before the training date and enabled on that date in the gym timezone. | Pending |
| Content | Create, preview safe text, save, reopen/edit/archive, search/status filters; trainer denied. | Pending |
| Measured progress | Sign a session with numeric plan loads and inspect chart/CSV; explicit recorded results win; correct results without duplicate points/debits; no-shows excluded; refresh older signed history. | Pending |
| Owner profile | Open from profile menu; name/role/status visible; native Back returns to the previous page. | Pending |
| Onboarding | Add Client/Trainer, revisit sections, edit from Review, cancel confirmation, then confirm once. Draft retained; no duplicate creation. | Pending |
| Packages | Check four-field onboarding row; independent frequency; free integer count 1–365, reject blank/fractional/exponential/out-of-range values, review proportional validity, retain purchased snapshots and action gaps. | Pending |
| Dashboard renewals / category filters | Prominent full follow-up count, unchanged by marking read; zero state and trainer scoping; up to three renewal Messages above calendar; open/read/unread/related record/Back; View All Renewals keeps category after reload. Shared client/trainer navigation (row from 700px, selected-label dropdown below) combines with text/date filtering and resets pagination; no page overflow. | Pending |
| Approvals / Messages | Inspect old/new details and record links; cancel/approve/reject; pending indicators and read/unread state remain correct. | Pending |
| Progress report history | Owner Progress → View Export/WhatsApp History; CSV and WhatsApp opened actions record gym-local timestamps and owner/trainer names. Reload, per-client isolation, pagination, empty history, failed save retry without re-export, blocked popup produces no event. Trainer cannot view history. General Information has no renewal controls. | Pending |
| Remuneration | Eye control at top right on phone; one compact session row; approval confirmation and stale protection. | Pending |
| Sidebar sections | All groups initially collapsed at sign-in/reload/account change; independently collapse each group by click/tap/Enter/Space on desktop, iPad and mobile; hidden links leave tab order; destination group opens on navigation. Mobile hamburger sections also start collapsed. Resize both ways and switch account. | Pending |
| Layout | Phone, real iPad and desktop: long names wrap; controls fit; profile dropdown below 700px and inline navigation from 700px. | Pending |
| Modal / keyboard | Modal scrolls; background is locked; focus enters/stays/returns; virtual keyboard does not trap Save/Cancel. | Pending |
| Back / swipe | Client History page 2 → Session → Back restores History page 2 and scroll; trainer Assigned Clients → Client → Session → Back twice restores its filters; all list searches/filters and selected progress exercise survive Back/Forward/reload; edit cancellation preserves draft. Android detail Back returns within app. | Pending |
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
