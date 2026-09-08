# Fitfinity migration status — M4.3 Pages readiness

M3 is frozen at `7d114a14630f5c17ab2c761626695dd655a847c1` on `main`, tagged
`m3-operations-frontend`. Its 159-file release fingerprint is
`9648fe7a4801b90ef947d47bd2a009ff4396966420c55b0261afeb174d983ba6`.
The verified M3 Mac result was 212/212 unit tests in 47 files, build passed,
and 357/357 browser cases (119 per project).

M4.3 prepares the **staff portal** for hosted demo acceptance. It is not a final M4 freeze,
a production authentication release, or a completed public website.

## Milestones

| Milestone | Status / scope |
|---|---|
| M0 | Frozen v0.57 behavioural reference; later user requirements supersede old rules. |
| M1 | Completed: React shell, navigation, mock persistence, profiles and permissions. |
| M2 | Frozen: sessions, planning, outcomes, package-credit invariants and responsive flows. |
| M3 | Pushed: onboarding, approvals/Messages, remuneration, exercise management, Packages and shared UI. |
| M4 | In progress: staff frontend acceptance, PWA release handling, documentation and device verification. |
| M5 | Backend/auth foundation, DB migrations, `/me` and server authorization. |
| M6 | Replace mock services with domain APIs. |
| M7 | Backend events, scheduled notifications and cloud media pipeline. |
| M8 | Production-like staging and owner/trainer UAT. |
| M9 | Production launch, monitoring, backups and runbook. |

## M4 scope reconciliation

| Area | Current disposition |
|---|---|
| Dashboard / Messages | Renewal inbox preview above Weekly/Monthly calendars; no daily agenda or Today button. Shared profile navigation for categories, combined filters and category URLs; date-triggered session popup with existing history and modal owners; shared message list/dialog/history and persisted read/unread state. |
| Operational staff workflows | Existing M3 scenario intent retained. Weekly/monthly calendar uses scoped sessions and live business dates. |
| Client signing / progress | Drawn evidence saved with completion; clear/review/reopen supported. Measured results update charts and CSV; repeat saves never add a second debit. |
| Owner Profile | M4.1 shows the stored name, role and status using shared profile components. Read-only; no contact details invented. Account editing is not claimed complete. |
| Main navigation | Fixed sidebar sections start collapsed above 780px; independently toggle; destination section reveals on navigation; hamburger groups stay expanded. UI state is generated from the existing role navigation and resets for another account. |
| Trainer Profile | Existing sections, permission model and edit flows retained. |
| Content Management | Owner can create/edit, preview, search and archive generic content entries. Public publishing is deferred. |
| Public website and Glofox member access | User-agreed deferral until the staff portal is finished. Not part of staff M4 acceptance. |
| Change Password / Sign Out | Functional mock account flows with session expiry, current-password checks, dirty-edit guard and retries. Production identity starts at M5. |
| Exercise Library | Staff management remains in scope; attachments are browser-local. |
| Session filming | Async media callbacks, abortable preparation, persistent blob saves, safe replacement rollback and metadata cleanup. Real-device capture and production processing remain open. |
| Additional Setup pages | No expansion approved beyond Packages. |
| PWA | M4.1 adds build-derived precaching and safe update lifecycle. Physical installation, OS gestures and updates require device evidence. |

No new complete v0.57 screen-by-screen visual comparison is claimed by M4.1.
The current source, updated handoff and existing scenario intent are the acceptance baseline.
Record any additional parity discrepancy before final freeze.

## Current business rules

- Packages: 12/24/36 sessions with 90/180/270-day validity. Frequency is independent;
  two or more weekly sessions includes gym membership. Preserve purchased terms/version.
- Approval-needed checked means direct action is disallowed. Pending changes do not
  mutate the business record. Resolution must remain atomic and reject stale actions.
- One completed session consumes at most one package credit. Preserve past evidence.
- Remuneration uses Singapore session start time: weekdays 06:30–08:30 and
  18:00–20:30, ends exclusive; weekends peak all day. Cycle: 16th to next 15th.
- Keep one edit guard, confirmation provider, notification provider, modal layer and
  history owner. Modify canonical service/component/style owners in place.

## Evidence and remaining acceptance

The M4.1B Mac baseline passed 219 unit tests in 48 files and 372 browser cases.
The uploaded M4.2 Mac run passed 243 unit tests / 53 files and build, with
**375 passed and 18 failed out of 393 browser cases**. M4.2A addresses account and
profile readiness, a future schedule fixture with an expired end date, the read-order
fixture clock, and the media-specific saved Message expectation. Original scenarios remain.
The latest M4.2A Mac result is **247 unit tests / 54 files and build passed;
401 passed / 1 failed out of 402 browser cases**. The remaining tablet Tab-order
assertion is retained in a dedicated hardware-keyboard context in M4.2B; touch
sidebar scenarios remain.
The M4.2B Mac run passed **252 unit tests / 54 files and build**, but finished
**411 passed / 3 failed out of 414 browser cases**. M4.2C adds the missing compact
calendar date action and corrects macOS WebKit keyboard traversal without removing
focus assertions.
The uploaded M4.2C Mac receipt is **all gates passed: 255 unit tests / 54 files,
build, 420 browser cases and integrity/code health**, fingerprint
`e5b553501cbc8ae74259f87f1277dc549786262d0a0fffb877733920eca76317`.
M4.2D makes the full renewal follow-up total prominent, adds View day actions and
a five-card calendar preview with +N more, renames All Sessions to Sessions and
removes instructional form copy. Password requirements use loaded policy in
notifications. The full day popup remains unlimited and trainer-scoped.
M4.2D passes **257 unit/component tests in 54 files** and builds in this workspace.
Its Mac run then stopped at Vitest: **255 passed / 2 calendar timeouts out of
257 tests**. Build and Playwright execution did not start.
M4.2E separates the context/hook into `src/hooks/usePortalData.js`, leaving the
provider module with only its React component export. The calendar tests query
explicit button labels and the mode-control group to reduce month-grid scanning,
with all assertions and the default timeout retained. Signature queries are also
scoped to their active dialog after a full workspace run exposed a timeout there.
M4.2E passes **257 unit/component tests in 54 files** and builds in this workspace.
The uploaded M4.2E Mac receipt passed **all gates: 257 unit tests / 54 files, build,
423 browser cases and integrity/code health**, candidate
`89de2e49de4a68a3b4466f9fd6e1698ef749bf40853ded32e0a802e6ed5da6e4`.

M4.3 makes assets, manifest, worker scope and cache ownership follow the deployment
directory. GitHub Actions verifies tests before building for the Pages metadata
path and publishing the complete release. Local root hosting remains supported.
The new unit result is **264 tests / 54 files passed**; full Mac execution of the
**432-case browser inventory (144 per project)**, the first hosted deployment and
physical PWA acceptance remain pending. Follow [GITHUB_PAGES.md](GITHUB_PAGES.md).
Browser inventory and installer-fixture tests are not application browser evidence.
Physical acceptance and a complete visual comparison remain pending.

Owner-profile editing fields, existing-client package renewal rules and a Copy
Previous Plan UI remain undecided expansions from the audit. They are not claimed
implemented. No payment or overlapping-package rules were invented.

See [FRONTEND_SERVICE_CONTRACT.md](FRONTEND_SERVICE_CONTRACT.md) for adapter and
configuration contracts. Record actual device results in [M4_ACCEPTANCE.md](M4_ACCEPTANCE.md).

Follow [PRODUCTION_ARCHITECTURE.md](PRODUCTION_ARCHITECTURE.md) before M5.
