# Portal service contracts

## Accepted lifecycle and infrastructure-first continuation — 1 October 2026

The user reports the complete session lifecycle gates passed at 03:21 Singapore for the 500-file `7208b97902ebecfc83458be0003bf2c5acc00201dd7b4cbb7595034aa6b24ad3` source. The six-flow review is closed for its documented scope. Earlier pending lifecycle statements below are historical; the failed 714/717 browser receipt and focused 9/9 diagnostic remain recorded in Journey.

The user now prioritizes **infrastructure → first Owner/live authentication → automated application deployment**, then remaining M6.1 business integration. Creating an Owner does not depend on client/trainer/package writes or assessment integration. `app.auth.admin.bootstrap-owner` already provides guarded identity linking; preserve the single-Owner concurrency guard and exact verified Cognito identity requirements. Creating/linking that identity is an explicit one-time operation, never an automatic release step. Authentication policy, CSRF/cookie/session authority and Owner/Admin assessment permissions are unchanged.

The new image candidate command (`deploy.py image-candidate --actions --receipt <new-file>`) builds/publishes/scans only the verified main commit after all shared CI gates and explicit activation. It uses a separate image role, exact ECR repository and current scan policy. Its receipt explicitly leaves application deployment and live authentication acceptance false. It does not call application APIs, migrate the database, create staff or send email. It cannot reuse the expired historical image exception. The complete release command remains blocked; current-image runtime proof, Owner/live sign-in, hosting, migration/recovery, rollout/smoke and verified GitHub controls remain acceptance work.

The user accepted the image-tooling candidate at **08:04 Singapore** with all native gates passed by report: **767 units / 84 files, 416 backend/PostgreSQL, 408 infrastructure, 717 browser, 33 quality and 20 health-tooling** plus supporting gates. Its 504-file source fingerprint is `15997d6b7ef42c558763a9bd8cfeaea053fc8f7661a595387c838d9054c8df02`.

Native setup receipt `Fitfinity_AWS_GitHub_Setup_2026-10-01.2gmeXz.json` verifies the GitHub OIDC provider, separate image/verification roles, main-only `aws-test` environment and main history protection at **22:07:30 Singapore**. Image publication is disabled. Required PR/CI enforcement and actual workflow OIDC use remain pending; no live Owner or application deployment is claimed.

The agreed release workflow is **feature branch → PR → complete CI → required checks green → merge to main → deployment of the verified main commit**. PR preparation updates only the three canonical documents before publishing the accepted source. Existing service contracts, API availability, application code, dependencies, migrations and test policy remain unchanged. The authoritative continuation order and activation runbook are at the top of Rules and Architecture.

## Session lifecycle review contract — 1 October 2026

The user reports **all gates passed** for `Fitfinity_Session_Lifecycle_Fixes_2026-09-30.sh` at 01:45 Singapore on 1 October 2026. The accepted baseline is the complete **500-file** revision `2aaebdd38b4ebc69f814c7bf68971fa6e33b3c651f923f39e5850bd26f783632`: 758 units / 84 files, 416 backend/PostgreSQL, 378 infrastructure, 714 browser, 25 quality and 20 health-tooling cases plus supporting gates. All 500 local hashes were verified before edits. This is user-reported native acceptance, without a new raw log or physical-device receipt. It supersedes the A12/A13 pending status below.

This bounded review covers sign-in, sign-out, password changes, refresh, pending submissions and recovery. It adds nine unit cases in existing owners and one browser scenario, and strengthens four existing PostgreSQL session tests. Four desired-behavior checks failed before their corresponding fixes:

- **Session establishment:** clearing local credentials previously erased the evidence needed to recognize the next login as a new session. A delayed anonymous `/me` expiry could clear completed MFA; delayed sign-in/recovery-start responses could also survive a newer verified login. `apiClient` now advances the local generation when authority is established after a clear. Initial bootstrap and same-session reads retain their existing behavior. `apiPortalAdapter` coalesces account loads only within the same generation, so completed MFA can load its account while an earlier anonymous read remains pending.
- **Password-form ownership:** the same user's replacement session retained the prior password draft and pending state. The existing `ChangePasswordPage` is now keyed by the verified session generation. Replacement removes those secrets and provides a fresh form; delayed logout/password completion cannot clear the replacement's form.

These are local concurrency guards, not credentials or caller authority. No generation is sent to the server. The server still decides whether a session is valid. Successful password change/reset revokes all existing sessions for that account; only a login established after that operation, or an unaffected account, is expected to survive. A13 still prevents delayed response deletion of replacement cookies. These checks do not claim global ordering of concurrent cookie-issuing sign-ins across tabs: the browser applies actual Set-Cookie responses, and account reads must verify the resulting cookie.

Normal refresh coalescing, ambiguous-mutation non-replay, bound Admin/password/logout preflights, server revocation, HTTP-only cookies, in-memory CSRF and stable explicit Admin retry keys remain required. A directory read cannot authorize an old form under a replacement login. A new authenticated account load must not join a pending anonymous load. Password secrets and pending state belong to the verified session generation, including when the replacement has the same user ID.

The candidate `Fitfinity_Session_Lifecycle_Review_2026-10-01.sh` remains pending native acceptance. Required targets are **767 units / 84 files, 416 backend/PostgreSQL, 378 infrastructure, 717 browser, 25 quality and 20 health-tooling** plus supporting gates. See the latest [Journey entry](./FITFINITY_JOURNEY.md) for the complete six-flow matrix, local evidence, browser/PostgreSQL limits and exit criterion. No production backend/API schema, authorization policy, dependency, migration or deployment change is included.

## A12/A13 session lifecycle correction — 30 September 2026

The user authorized fixing A12/A13 after accepting `Fitfinity_Browser_Fixture_Repair_2026-09-30.sh`. The last accepted Mac baseline is the complete **500-file** revision `eea270c5337d6f2628ce1ea3cb89667570fbdd79c8499a221143ac3fb5cdd3c8`, on the user's all-gates-passed report. This new candidate is **`Fitfinity_Session_Lifecycle_Fixes_2026-09-30.sh`**. Its full native acceptance remains **pending**; the previous pass does not certify these changes.

- **A12 implemented:** `portalService.js` supplies session-bound service closures to `PortalDataProvider` for each rendered API snapshot. The local generation is a concurrency guard, never an actor/role claim, request-body field, HTTP header or credential. `apiPortalAdapter` checks that initiating generation both before and after session preflight for Admin creation, password change and sign-out. A replacement discovered by the action itself or by a background directory load stops the old action before POST. The provider retires the old Admin recovery store, removes the old private view and re-verifies the account; a directory failure leaves an explicit Retry path. Old closures remain stale after a replacement load. Same-session actions, stable retry keys and the existing demo service boundary remain intact.
- **A13 implemented:** `auth.routes` no longer emits cookie deletion on successful logout, password change/reset or flow completion. Superseded `AuthResult.clear_session/clear_flow` fields and their callers are removed. Server-side logout revocation, account-epoch invalidation, refresh revocation and flow consumption remain authoritative and unchanged. A revoked cookie may remain in the browser until expiry/replacement; it cannot restore the revoked server session. New session/flow issuance retains HttpOnly, Secure, SameSite, Path and lifetime controls. Avoiding unconditional deletion prevents a delayed successful old response from erasing a newer cookie. Existing late-expiry protections remain.

### Scoped regression and verification evidence

Eight frontend cases cover replacement before submit, during preflight, while directory recovery is pending/fails, a role change, and session-bound Admin/password/logout commands including stale callbacks and valid new-session actions. Five assembled-app regressions fail against the old runtime. Three new real-HTTP response/cookie tests cover delayed logout, password-change and password-reset success; all three fail against the old service/response contract. These use controlled authentication callbacks and the actual idempotent logout result with a fake absent-row transaction; they do not claim live password-provider or PostgreSQL execution. Existing PostgreSQL revocation/flow-consumption assertions remain in the native suite, with obsolete cookie-clear-flag assertions replaced by the public signedOut result.

Observed local passes: **758 frontend units / 84 files** in **45.15 seconds**; **62 backend HTTP/security cases** in **2.08 seconds**; **378 offline infrastructure cases**; **25 quality + 20 health-tooling cases**; semantic/Hooks lint on **300 files**; Ruff/format on **116 backend files**; **28 API operations**; **11 forms / 303 fields**; source health (**167 reachable runtime modules**) and unchanged CSS (**948 rules / 3347 declarations**); root/Pages/API builds and all PWA checks. Seven actual HTTP-fixture checks also pass without importing Playwright. Full backend collection is **416**; collection is not a PostgreSQL execution receipt. The first focused frontend run exposed that rebinding unscoped demo services bypassed injected test/service wrappers; scoping is now limited to snapshots carrying the API generation, and the complete suite passes. One test import-order lint error was corrected; no gate was relaxed.

One new browser scenario covers replacement discovered at Admin submit followed by exactly one valid new-session creation. The existing authentication browser scenario now verifies no deletion header, the retained HttpOnly cookie, and sign-in after logout/reload, proving fixture revocation rather than cookie erasure. The fixture follows the same response contract; prior real-HTTP delay/cleanup behavior remains. Browser execution/discovery/installation remains user/CI-owned. Required native targets are **758 units / 84 files; 416 backend/PostgreSQL; 378 infrastructure; 714 browser (238 per project); 25 quality; 20 health-tooling**, plus all existing supporting gates. Receipt checks reject the older 750-unit/711-browser inventories. No timeout, retry, worker, skip or coverage setting changes.

### Acceptance and next step

The installer recognizes the complete accepted baseline, the complete documentation-only audit snapshot, or its own exact rerun. It preserves dependency-free source checks, pinned dependency restore, full-source backup, coloured verbose full gates, Git/index preservation and final integrity. The 22 isolated installer safety checks verify all 500 backup files and reject partial/unknown/edited/missing/redirected/staged/drifted sources and incorrect Git/environment state. No cloud, real email, publication, data reset, migration rewrite or deployment is included.

This is the bounded A12/A13 correction. After its unchanged native gates pass and the documented scenarios are accepted, continue remaining M6.1 integration; do not automatically start another unrestricted audit. Concrete new defects still warrant triage. A3–A5 deployment/evidence work remains separate. Preserve the corrected accepted assessment policy: Owner/Admin access, actual actor evidence and no expanded trainer health access; frontend API assessment integration remains pending.

## Accepted browser-fixture repair and follow-up audit — 30 September 2026

The user reports **all gates passed** for `Fitfinity_Browser_Fixture_Repair_2026-09-30.sh` at 23:39 Singapore time. The accepted baseline is **500 files**, fingerprint `eea270c5337d6f2628ce1ea3cb89667570fbdd79c8499a221143ac3fb5cdd3c8`. All 500 local source hashes match that installer revision. This is **user-reported native acceptance**; no new raw gate log or physical-device receipt accompanied the report. The accepted targets remain **750 frontend units / 84 files; 413 backend/PostgreSQL; 378 infrastructure; 711 browser (237 per project); 25 quality; 20 health-tooling**, plus the established lint, forms, contract, builds/PWA and integrity gates. This entry supersedes the pending status below; the earlier failed native receipt remains historical evidence.

The A10 outage navigation correction and A11 late-expiry correction are accepted for their covered cases. A targeted follow-up source audit reproduces two additional boundaries:

- **A12 / P2 — Admin submission can adopt a replacement session.** `apiPortalAdapter.invoke()` takes the generation returned by its own fresh `/me` preflight and immediately submits the existing draft under it, without binding that action to the session which owns the displayed form. Replace the same Owner's cookie before this tab finishes a refresh, then submit: the old draft is POSTed with the new CSRF token. The subsequent successful reload retires the old recovery store, leaving a blank form and discarding the successful creation result. The assembled-app observation verifies one POST of the old payload under token B and the missing success message; the unchanged-session control preserves the success result. Bind the workflow/action to its initiating verified session across preflight and reconcile a replacement before dispatch. Backend Owner authorization remains enforced; this is not an established privilege escalation.
- **A13 / P2 — Delayed successful logout deletes a newer login cookie.** `AuthService.sign_out(..., everywhere=False)` revokes the captured handle, then returns `clear_session=True, clear_flow=True`. `auth.routes._response()` emits unconditional cookie deletion. Hold that old logout, complete a newer login, then deliver the old success: the real HTTP cookie jar loses the fresh cookie and `/me` returns 401. Restoring the fresh handle makes `/me` succeed, showing the newer session was lost at the cookie boundary. JavaScript generation checks occur after cookie processing and cannot repair this. Preserve authoritative logout revocation while preventing stale completion from deleting a replacement login/flow. Review related successful password/session transitions for the same shared-cookie mechanism; only delayed sign-out is newly reproduced here.

**Assessment-policy documentation correction:** Earlier September 30 audit summaries incorrectly said backend assessments remain Owner-only. The accepted September 24 Admin capability table explicitly permits Admin assessment access and changes. The canonical backend uses `Principal.operations()` and `test_admin_assessments_record_the_actual_admin_and_completed_sessions_remain_read_only` verifies Admin creation with the actual Admin actor. Preserve that accepted Owner/Admin behavior; trainer health access is not broadened, and frontend API assessment integration is still pending. This corrects the earlier audit wording, not runtime permissions. The older Owner-only statements below are superseded by this correction. The existing PostgreSQL test was inspected, not newly executed during this audit.

These findings are **open, not fixed**. Seven focused checks pass as observations/controls: two assembled React/adapter observations, one delayed-logout HTTP observation, the three existing delayed-expiry HTTP controls, and one existing security-template control. Observation passes demonstrate the defect, not desired-behavior regression acceptance. HTTP authentication is stubbed at the service boundary; no PostgreSQL, Cognito, email or browser behavior is claimed from these observations. No critical/high-severity issue or authorization bypass was established in the inspected paths; this is not an exhaustive security certification.

This audit changes only the three canonical documents. Runtime, tests, configuration, dependencies, migrations, Git HEAD and index remain unchanged. Preserve the accepted manifest separately from this documentation-only snapshot for the next guarded correction. No new installer or repeated full gate run is required just to read this audit. The existing audit-to-release process applies to A12/A13; remaining M6.1 integration and the separate A3–A5 deployment/evidence backlog are unchanged. No assistant Playwright execution/discovery/installation, AWS call, real email, Git publication, data reset or deployment occurred.

## Native gate follow-up: browser fixture only

The first A10/A11 native receipt passed 750 units, 413 backend/PostgreSQL and 378 offline infrastructure checks, then stopped at **709 browser passes / 2 WebKit timeouts** in the new session-race test. It is not full acceptance. `Fitfinity_Browser_Fixture_Repair_2026-09-30.sh` changes the existing HTTP fixture and browser scenario, plus records this receipt; production service/transport/provider/cookie contracts below remain unchanged.

The delayed old-session expiry now comes from the fixture's actual HTTP server after its cookie/CSRF/role/input checks, allowing independent new-session verification before release. Browser assertions cover the same retained draft/new-session behavior, explicitly check both HTTP requests and exactly one account, and retain all 711 cases and existing timing policies. Seven local HTTP checks verify this fixture/transport sequence without Playwright. Native WebKit acceptance remains pending; see the latest Journey entry for the evidence and installed-source guard.

## A10/A11 correction candidate

The current candidate `Fitfinity_Boundary_Fixes_2026-09-30.sh` implements A10/A11 against the accepted 500-file recovery baseline described below. Native acceptance remains pending. Observed verification is 750 frontend units, 59 backend HTTP/security cases, 378 offline infrastructure cases and the existing supporting checks. Full native targets are 750 units / 84 files, 413 backend/PostgreSQL and 711 browser (237 per project), with unchanged 25 quality and 20 health-tooling gates. See the latest Journey entry for scope and evidence; previous open-finding statements below are historical.

## Accepted recovery checkpoint and follow-up audit

Updated 30 September 2026 after the user's **all gates passed** report for the 500-file A7–A9 recovery correction (`2e2914687c9c14deedb08aed24d360cb871cc0b9380035c7b14c5c8a8f80bb11`, `Fitfinity_Audit_Recovery_2026-09-30.sh`). Accepted inventory includes 734 unit cases in 84 files; the full counts and source provenance are at the top of [Rules and Architecture](./FITFINITY_RULES_AND_ARCHITECTURE.md). The latest [Journey entry](./FITFINITY_JOURNEY.md) records the follow-up audit. This is user-reported acceptance, not a newly observed native receipt. Older pending/count references are historical.

M6.1 remains partially complete. Authentication/transport, directory reads (including package data in the loaded snapshot) and Owner Admin creation are integrated; real client/trainer/package writes and durable assessment workflow integration remain pending. Backend assessment endpoints already exist, but the frontend assessment service is unavailable in API mode. Unsupported operations must continue to fail before HTTP, without a demo fallback. HTTP-fixture browser acceptance is separate from a real Cognito/FastAPI/PostgreSQL browser receipt.

A1/A2 and A8/A9 remain fixed and accepted. Original A7 refresh-only recovery is fixed, but the audit confirms A10 (Back during an outage bypasses the guard and discards the retained workflow) and A11 (a delayed old-session expiry can invalidate a newer verified session). The audit recorded these as open; the candidate above now implements both with permanent regressions and updated exact inventories. Existing operation permissions and API availability remain unchanged; A3–A5 remain separate release blockers.

The infrastructure CLI deliberately refuses full deployment. Actions currently publishes the Pages demo after checks; its separate AWS workflow verifies metadata only. Green service tests do not implement production endpoints or renew the expired historical image exception.

The UI calls the services created by `createPortalServices`. Every method returns a Promise and accepts one named input object. There is no positional actor argument or compatibility overload. No-argument reads and sign-out default to `{}`.

`clientService.update({ id, patch })` becomes `adapter.invoke({ service: 'clientService', operation: 'update', input: { id, patch } })`. Account methods use `adapter.session({ operation, input })`. `load()` and `reset()` remain separate lifecycle methods.

## Ownership

| Module | Responsibility |
| --- | --- |
| `portalContracts.js` | Closed operation catalog, named input envelopes, shallow field/type validation, adapter availability and documented resolved values. |
| `portalService.js` | Async public facade; passes values and errors through without transport or permission knowledge. |
| `mockPortalAdapter.js` | Obtains current identity, validates the request, authorizes, invokes the named handler and applies Admin result projection. |
| `portalAuthorization.js` | Named operation and resource access policies. Domain services still enforce stored actor identity, transaction invariants and business validation. |
| `mockPortalOperations.js` | Explicit translation from named input plus adapter-owned `{ actor }` context to existing domain functions. No argument-index table or arbitrary method dispatch. |
| `apiPortalAdapter.js` | Validates availability before HTTP; maps supported inputs to existing endpoints. The server owns production authorization. |

Caller input never supplies actor, user, role or execution context at the request boundary. Unknown service/method names, inherited object methods and unknown input fields cannot dispatch. Top-level input must be an ordinary record; required fields have shallow types. Optional fields may be omitted or null. Nested drafts, patches, optimistic versions, money, dates and conflicts retain their existing domain validators. These guards supplement the backend; client-side authorization alone is not a production security boundary.

The API currently supports client/trainer directory reads and Owner Admin creation. Other domain operations fail with `OPERATION_UNAVAILABLE` before session bootstrap or HTTP. This change does not implement the remaining production workflows or enable AWS app deployment.

## Recovery and validation boundaries

`PortalDataProvider` owns one in-memory Admin creation state per verified Owner and transport session generation. A directory error removes private UI but preserves same-Owner workflow state and unload protection. Successful reload must verify the same Owner before the dialog resumes. Sign-out, expired/recheck sessions, changed Owner/role and forbidden creation retire the workflow; late callbacks cannot restore it. `apiPortalAdapter.load()` errors can carry a minimal `verifiedIdentity` (`id`, `role`, `sessionGeneration`) when session verification succeeded but directory loading failed. This evidence can only discard an old recovery scope, never authorize a private view or write. Deliberate, confirmed navigation away must reset the workflow. `PortalWorkspace` keeps the one canonical native-history owner mounted while a same-session Owner workflow survives a directory outage. Back, Forward and direct hash navigation use the existing confirmation; Cancel retains the workflow, and only accepted departure resets it. This recovery mechanism does not write its draft/key/PII to browser storage; a closed or reloaded tab does not retain it. Existing demo business-record persistence is unchanged.

Client General Information uses `clientStepErrors(..., { requireComplete: false })` to allow missing legacy values while validating every supplied contact/date/enum value. The demo commit owner applies the same checks atomically. Individual scalar contact updates synchronize `people`; Couple contact updates require `people` and reject ambiguous scalar-only contact patches. Saved assessments remain protected from contact edits. Real API client writes remain unavailable.

The directory DTO owns wire-to-domain conversion: `public_profile` must be a boolean, then becomes `publicProfile: 'Visible' | 'Hidden'`. Consumers render the existing domain value without adding alternate display logic.

Session verification must distinguish the session that issued a request from a replacement session, including a new login for the same staff ID. Replacing a known CSRF token or verified principal advances the transport generation. Stale responses reject as SESSION_CHANGED before session effects; response validation/session acceptance run synchronously with that check. API session reads return a local nonsecret sessionGeneration, and follow-up reads/mutations must match it. API snapshots and verified-identity error metadata carry that generation to retire replaced Owner workflows, including same-account logins. Provider operations capture their starting identity/session scope before applying terminal effects. AuthError responses never change cookies; explicit successful auth transitions retain their cookie ownership. Genuine current-session expiry remains enforced by backend authorization and frontend sign-out behavior.

## Results and failures

Records are the existing domain records, including their established IDs, versions and dates. `ScheduleResult<T>` contains `outcome` and the corresponding `client`, `trainer` or `session`. `AcknowledgementResult` contains `session` and `transactions`. `MediaReference` is `{ id }`. Admin creation returns `{ id, name, email, role, invitation }`; API responses retain their strict field validation. Request decisions now return the decided Message and remuneration approvals return the approved record, instead of returning the whole mock database. These are the only narrowed domain result shapes in this refactor; UI callers refresh after success.

`load()` resolves a snapshot with `user`, `data`, `policy`, `accounts` and `capabilities`; signed-out snapshots have null user/data. Demo snapshots may include `demoPassword`; API snapshots may include `authNotice` and the local nonsecret `sessionGeneration` (not a backend authority credential). Capability flags remain the UI's environment controls. Mock reset resolves a fresh snapshot; API reset is unavailable. Authentication intentionally differs: demo sign-in resolves a User, whereas real sign-in resolves an AuthChallenge and requires MFA. This distinction is exposed by `realAuthentication` capabilities, not inferred from user role.

| Failure | Behaviour |
| --- | --- |
| `INVALID_REQUEST` | Reject malformed envelopes, identity fields, missing/wrong shallow field types or ambiguous challenge answers before dispatch. |
| `OPERATION_UNAVAILABLE` | Reject unknown or environment-disabled operations before domain/HTTP dispatch. |
| `FORBIDDEN` | Mock boundary access policy denies the operation or resource. |
| Domain rejection | Preserve the original error/message; no rewriting of conflict, stale-version, storage or business errors. |
| API/session failure | Preserve the existing ApiError code, status and request ID, including `SESSION_EXPIRED`, `NETWORK_ERROR` and `API_RESPONSE`. |
| Refresh after successful write | Preserve the successful write/retry identity and report refresh failure separately. Admin creation now retains its draft, original request key/body, pending state and confirmed result independently of directory-view unmounts. No automatic mutation replay; explicit reconciliation uses the same request key. |

The test receipt gate also rejects standalone browser Error lines; its earlier trailing word-boundary bug is covered by a negative receipt test.

Result names below document resolved values. They do not add a validator after a committed mock mutation: a post-write shape error could falsely suggest that the write failed. Existing domain tests and new boundary tests verify persistence, identity and record results; API wire responses keep their existing validation.

## Trainer permissions and booking invariants

The public facade still takes named inputs only. The mock adapter supplies the authenticated actor to internal domain operations; caller input cannot choose it. Generic trainer updates allow only `name`, `phone`, `email`, `birthday`, `gender`, `trainerType`, `qualifications`, `publicProfile`, plus Owner-only `rates`. Any unknown or protected key rejects the entire patch, including an otherwise valid profile edit. Trainers can edit their own active profile but cannot change their name. Approval, availability and status changes use dedicated operations.

`trainerService.updateAutonomy({ id, approvalNeeded })` requires an active stored Owner/Admin and exactly the four defined boolean approval controls. Trainers cannot use this action or the generic patch to change approvals. `update`, `updateAutonomy` and `deactivate` recheck the stored active actor inside the mutation after the simulated transport delay.

`app/bookingAvailability.js` owns the shared occupancy rule: completed/no-show records retain their full scheduled interval, including inactive client/package history; cancelled and inactive unfinished records do not reserve time. On the same date, overlapping trainer or client intervals are blocked; touching boundaries are allowed. Schedule patches cannot change the client identity used by this check.

New-client creation, renewals, individual/weekly schedule changes, approvals, permanent reassignment and trainer deactivation validate against the prospective calendar before committing. Deactivation checks all replacement choices together; it does not require declared weekly hours for individual cover. Matching uses actual purchased session dates and the full calendar, including other clients. Stale UI choices cannot bypass save-time checks. The mutation publishes neither partial bookings nor partial messages on failure. Production write operations shown as unavailable below remain unavailable.

## Personal message receipts

`messageService.markRead({ id })` and `markUnread({ id })` resolve to `PersonalMessage`: message content plus the authenticated recipient's `read` and optional `readAt`. A missing or inaccessible message rejects with `FORBIDDEN`; caller input cannot select a different user. The domain operation checks the stored active actor and recipient relationship inside the mutation after its delay.

Persistence uses `message.readBy[userId]`; an absent entry means unread. Reading creates or preserves only that user's receipt; marking unread deletes only that entry. The mock snapshot and request decision/cancellation results remove all receipt maps and expose the current user's projection. Inbox visibility, navigation badges and service authorization share `app/messageInbox.js`, preserving additive renewal routing and Admin financial restrictions. Request decisions remain shared independently of read state.

Legacy global flags are removed during atomic normalization. An individually attributable read can be retained; ambiguous role/shared flags become unread once. Existing personal receipts are never reconstructed from old flags. The PostgreSQL receipt model already separates users, but production message APIs remain unavailable in this frontend adapter.

## Domain operation inventory

The catalog is canonical. Each input lists `field: type`; `?` marks optional fields. All operations support the demo adapter; the API column identifies the currently implemented subset.

| Service.operation | Named input | Resolves to | Access policy | API |
| --- | --- | --- | --- | --- |
| `staffService.createAdmin` | `body: object, requestKey: string` | AdminInvitation | owner | Yes |
| `contentService.save` | `id?: string, expectedVersion?: number, draft: object` | ContentEntry | operations | Unavailable |
| `clientService.getAll` | `{}` | Client[] | authenticated | Yes |
| `clientService.getById` | `id: string` | Client \| null | authenticated | Yes |
| `clientService.create` | `draft: object` | Client | operations | Unavailable |
| `clientService.renewPackage` | `id: string, draft: object` | Client | operations | Unavailable |
| `clientService.deactivatePackage` | `id: string, options: object` | Client | operations | Unavailable |
| `clientService.deletePackageSessions` | `id: string, options: object` | Client | operations | Unavailable |
| `clientService.update` | `id: string, patch: object` | Client | clientEdit | Unavailable |
| `clientService.saveAssessment` | `id: string, assessment: object` | AssessmentRecord | operations | Unavailable |
| `clientService.saveFixedWeeklySchedule` | `id: string, slots: array` | `ScheduleResult<Client>` | assignedClient | Unavailable |
| `clientService.reassignTrainer` | `id: string, draft: object` | Client | operations | Unavailable |
| `clientService.recordProgressReportAction` | `id: string, action: object` | ProgressReportEvent | reportClient | Unavailable |
| `clientService.progressReportHistory` | `id: string, packageId?: string` | ProgressReportEvent[] | operations | Unavailable |
| `clientService.deactivate` | `id: string` | Client | operations | Unavailable |
| `clientService.reactivate` | `id: string, dates?: object, expected?: object` | Client | operations | Unavailable |
| `trainerService.create` | `draft: object` | Trainer | trainerCreate | Unavailable |
| `trainerService.saveAvailability` | `id: string, blocks: array` | `ScheduleResult<Trainer>` | assignedTrainer | Unavailable |
| `trainerService.getAll` | `{}` | Trainer[] | authenticated | Yes |
| `trainerService.getActive` | `{}` | Trainer[] | authenticated | Yes |
| `trainerService.getById` | `id: string` | Trainer \| null | authenticated | Yes |
| `trainerService.isSelectableForAvailability` | `trainer: object` | boolean | authenticated | Unavailable |
| `trainerService.update` | `id: string, patch: object` | Trainer | trainerEdit | Unavailable |
| `trainerService.updateAutonomy` | `id: string, approvalNeeded: object` | Trainer | operations | Unavailable |
| `trainerService.deactivate` | `id: string, replacements?: object` | Trainer | operations | Unavailable |
| `trainerService.reactivate` | `id: string` | Trainer | operations | Unavailable |
| `sessionService.loadVideo` | `sessionId: string, exerciseId: string` | Blob \| null | session | Unavailable |
| `sessionService.saveVideo` | `sessionId: string, exerciseId: string, file: blob, metadata: object` | MediaReference | session | Unavailable |
| `sessionService.removeVideo` | `sessionId: string, exerciseId: string` | void | session | Unavailable |
| `sessionService.updateDetails` | `sessionId: string, patch: object` | Session | operationsSession | Unavailable |
| `sessionService.requestTimeChange` | `sessionId: string, patch: object` | `ScheduleResult<Session>` | session | Unavailable |
| `sessionService.requestTrainerChange` | `sessionId: string, replacementTrainerId: string` | `ScheduleResult<Session>` | session | Unavailable |
| `sessionService.saveExercisePlan` | `sessionId: string, items: array` | Session | session | Unavailable |
| `sessionService.previousPlanFor` | `sessionId: string` | ExercisePlanItem[] | session | Unavailable |
| `sessionService.copyPreviousPlan` | `sessionId: string` | Session | session | Unavailable |
| `sessionService.saveOutcome` | `sessionId: string, outcome: object` | Session | session | Unavailable |
| `sessionService.saveClientSummary` | `sessionId: string, summary: string` | Session | session | Unavailable |
| `sessionService.markWhatsAppOpened` | `sessionId: string` | Session | session | Unavailable |
| `sessionService.acknowledge` | `sessionId: string, acknowledgement: object` | AcknowledgementResult | session | Unavailable |
| `packageService.save` | `id?: string, expectedVersion?: number, draft: object` | PackageDefinition | operations | Unavailable |
| `exerciseLibraryService.loadMedia` | `id: string` | Blob \| null | authenticated | Unavailable |
| `exerciseLibraryService.getAll` | `{}` | LibraryExercise[] | authenticated | Unavailable |
| `exerciseLibraryService.save` | `id?: string, expectedVersion?: number, draft: object, mediaFile?: blob, removeMedia?: boolean` | LibraryExercise | operations | Unavailable |
| `messageService.markRead` | `id: string` | PersonalMessage | message | Unavailable |
| `messageService.markUnread` | `id: string` | PersonalMessage | message | Unavailable |
| `requestService.resolve` | `id: string, decision: string` | Message | operations | Unavailable |
| `requestService.cancel` | `id: string` | Message | authenticated | Unavailable |
| `remunerationService.list` | `{}` | RemunerationCycle[] | remuneration | Unavailable |
| `remunerationService.detail` | `cycle: string, trainerId: string` | RemunerationRecord | remuneration | Unavailable |
| `remunerationService.approve` | `cycle: string, trainerId: string, revision: string` | RemunerationApproval | approveRemuneration | Unavailable |

Operations means Owner/Admin. Assigned-client edits require the current trainer; progress report access also recognizes historical assignment. Assigned-trainer edits require self or operations access. Session access requires the session's assigned trainer or operations access; direct details edits require operations access. Trainer rates remain Owner-only for writes and unavailable to Admin for reads. Remuneration remains unavailable to Admin; approval is Owner-only. Domain validators enforce the finer rules, including operations-only report history and trainer-owned cancellation. All session mutations recheck the active stored identity and current assignment inside the mutation. Video replacement checks again after upload; client creation/edits and trainer reactivation recheck at commit as well.

## Client reactivation review

`clientService.reactivate({ id, dates, expected })` accepts a map of session IDs to replacement ISO dates plus the scheduling snapshot from `clientReactivationSnapshot`. The UI reviews all retained unfinished sessions becoming active. Date moves require matching reviewed evidence; even a matching review is rechecked against the current competing calendar. Id-only reactivation remains available only when the retained calendar is conflict-free. Unknown/locked sessions, invalid dates, inactive trainers, stale evidence and trainer/client overlaps reject the entire transaction. Date changes preserve trainer, time, original package and existing offline contract rules, and append date history. Completed/cancelled sessions, separately inactive packages and deleted bookings are never recreated or moved by this action.

Admin media loads return the original Blob. The recursive Admin projection continues removing trainer pay/remuneration fields from records. Public inputs never accept an actor; internal domain calls require the adapter-sourced identity.

## Account operation inventory

| Operation | Named input | Resolves to | Environment |
| --- | --- | --- | --- |
| `signIn` | `identifier: string, password: string` | User \| AuthChallenge | both |
| `challenge` | `code?: string, newPassword?: string` | AuthChallenge \| AuthSession | api |
| `forgotPassword` | `identifier: string` | PasswordRecovery | api |
| `resetPassword` | `code: string, newPassword: string, confirmation?: string` | PasswordReset | api |
| `signOut` | `{}` | void \| SignedOut | both |
| `switchDemoIdentity` | `userId: string` | User | mock |
| `changePassword` | `currentPassword: string, newPassword: string, confirmation?: string` | PasswordChange | both |

Challenge requires exactly one of code/newPassword. Demo identity switching is unavailable in API mode. Password confirmation is local verification data; API password requests continue to send only their supported backend fields.

## Required quality gates

- `npm run verify:lint`: pinned ESLint 10 semantic/JSX checks and React Hooks rules/dependencies. No warnings or inline disable comments are accepted. React rules apply to React source; Playwright fixture callbacks named use are not React Hooks. The two intentional control-character regexes have narrow file-scoped exceptions.
- `npm run verify:quality-checker`: 25 checks exercise lint diagnostics, fixture compatibility, exact test receipts, workflow gate removal/weakening and direct dependency ownership.
- `npm run verify:health-checker` and `npm run verify:health`: 20 existing rejection fixtures plus source inventory, portable paths, syntax, imports, layering, cycles, runtime reachability and CSS checks.
- Full native inventories: **711 unit tests in 84 files; 410 backend/PostgreSQL; 378 offline infrastructure; 708 browser cases**. Root/Pages/API builds and PWA checks, immutable 11-form/303-field parity, and backend Ruff/contract checks remain required.

`.github/workflows/verify.yml` is the shared frontend and backend gate. `pages.yml` calls it on PRs to main, pushes to main and manual runs. Frontend runs on macOS for the established WebKit coverage; backend uses isolated Docker/PostgreSQL and the offline infrastructure suite. PR verification has no deployment credentials. Pages build/publish run only for main outside PR events and depend on all verification jobs passing. `infrastructure.yml` remains callable/manual for the existing AWS metadata audit; it no longer duplicates PR checks already included in the backend gate. Enabling required checks in GitHub branch protection is a separate repository setting; this installer does not change it.

ESLint, Hooks, globals, YAML, rolldown and css-tree are direct pinned dev dependencies in the lockfile. Existing dependency versions are retained. Use Node 24 as configured by CI. The installer installs the lockfile with npm ci after dependency-free source preflight, before complete preflight and apply, then runs the new gates alongside all native gates. It never stages, commits, pushes, deploys or calls AWS.

Hooks fixes preserve drafts during snapshot/policy refreshes, refresh read-only fields, keep navigation scroll restoration tied to history traversal and load media only when its resource changes. New refresh regressions check these behaviours. CSS remains unchanged. Booking-integrity coverage adds two browser scenarios across the existing three projects. Browser/native acceptance must come from the user's installer run; assistant unit/lint/build checks are not a device receipt.

References: [ESLint 10 JSX scope tracking](https://eslint.org/docs/latest/use/migrate-to-10.0.0), [React effect dependencies](https://react.dev/reference/eslint-plugin-react-hooks/lints/exhaustive-deps), [GitHub reusable workflows](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows).
