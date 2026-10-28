# Fitfinity business rules

This document owns current business requirements, design constraints and acceptance rules. Stable **BR-001–BR-064** IDs and anchors are preserved. [API contracts](api-contracts.md) owns the 55-operation inventory and detailed HTTP/schema reference; [Journey](journey.md) preserves the complete dated history. [AGENTS](../AGENTS.md) owns engineering instructions, [ADR](architecture/adr.md) owns stack rationale and [Progress](../PROGRESS.md) owns current status and remaining work. Current rules override superseded historical instructions and counts.

## Current business rules

Stable rule-group IDs identify the existing paragraphs below; they do not change their requirements. Keep IDs when editing or moving a rule, never reuse retired IDs, and allocate the next unused ID for a new rule. A group may include its immediately following table. The [55-operation matrix](api-contracts.md#domain-operation-inventory), milestone IDs and [complete journey](journey.md) retain their separate identities. [Code ownership mapping](code-owners.md#11-business-rule-to-owner-index) links every BR ID to implementation or an explicitly labelled operational/planned owner.

### Service boundary

<a id="br-001"></a>

**BR-001** — The React UI calls asynchronous services through `createPortalServices`. Explicit demo mode uses the prototype adapter; API mode uses `apiPortalAdapter` and never falls back to demo storage. `load()` returns the authorized user, policy, capabilities and data snapshot; `invoke()` returns the canonical saved record or declared domain result. Unsupported operations fail explicitly and their controls remain unavailable. Capabilities describe the current API surface, not a client-side permission grant.

<a id="br-002"></a>

**BR-002** — Authentication and session/calendar reads are additional acceptance requirements, outside the 55 named domain operations. Reads return only authorized records; client selectors may select locally from that scoped snapshot. `trainerService.isSelectableForAvailability` is a local predicate, not an HTTP write or substitute for server conflict checks.

### Authority and privacy

<a id="br-003"></a>

**BR-003** — Owner/Admin manage operations; Trainers act only within current assignment and policy. Recheck active account, assignment, versions and permissions inside the write transaction. Historical coverage/read access does not confer mutation rights.
<a id="br-004"></a>

**BR-004** — The initial **11 assessment forms are Owner/Admin-only**. Current assigned Trainers may read/edit general health notes separately. Report history and clinical access retain their distinct permission checks.
<a id="br-005"></a>

**BR-005** — Rates are Owner-only to change; Admin cannot read rate/remuneration data. Remuneration approval is Owner-only. Trainer request cancellation is restricted to the originating Trainer and a pending request.
<a id="br-006"></a>

**BR-006** — Trainer login/recovery email changes verify the new address with a code before switching. Do not infer completion of all Trainer profile fields from one implemented branch.
<a id="br-007"></a>

**BR-007** — Verified identity, HTTP-only cookies, CSRF and server-side authorization protect API writes. Browser roles, record IDs and hidden controls are never authority. Media access must be authorized; no private credentials, health data or tokens in diagnostics.

<a id="br-008"></a>

**BR-008** — **Lost authenticator — operator-assisted policy.** Recovery uses an independently authorized operator, identity verification against existing trusted records, an audit reference and fresh MFA enrollment; the staff app receives no Cognito administrator recovery powers. Keep pool-wide MFA required and preserve the existing staff identity and provider subject. Password recovery and MFA-preference reconciliation do not recover a lost TOTP factor. Prepare user-specific recovery with session/flow revocation, controlled re-enrollment, exact target binding and explicit handling of uncertain provider outcomes. Never collect passwords, TOTP seeds or codes in source, logs or chat. Real provider execution and live acceptance require separate authorization. AWS now documents [AdminDeleteSoftwareToken](https://docs.aws.amazon.com/cognito-user-identity-pools/latest/APIReference/API_AdminDeleteSoftwareToken.html) for removing a lost factor and [required-MFA re-enrollment](https://docs.aws.amazon.com/cognito/latest/developerguide/user-pool-settings-mfa-totp.html); the [operator procedure](runbook.md#52-operator-assisted-lost-authenticator-recovery) and synthetic drill are separate from live recovery acceptance.

### Persistence, conflicts and recovery

<a id="br-009"></a>

**BR-009** — A reviewed command binds its exact intent, current versions and actor-scoped idempotency key. Validate conflicts and authority again at commit; commit business records, version changes, history/notices and durable receipt atomically where the command requires them. A definitive rejection changes nothing. A lost response is an unknown outcome: reconcile the original receipt and retain the original intent/key; never automatically issue a replacement write. A failed refresh after a committed save does not turn that save into a failure. Ordinary same-client background versions must not discard an active editor: retain its reviewed snapshot and enforce stale-write checks, while changed identity, assignment or active status immediately retires private state. Cancelling a notes, client-information, Trainer-information/rates/approval or package-setup editor does not cancel an already-sent command. Same-login recovery remains available across routes after editing ends. Background refresh lists pending commands without consuming their receipts; an explicit Check reads the original receipt without writing, and only explicit retry confirmation may resume the original immutable body/key. An active creation editor retains its original command for Save again, preventing a background check from turning a retry into a new creation. Concurrent explicit retries stay guarded through the receipt read.

<a id="br-010"></a>

**BR-010** — Session editors likewise retain their reviewed values through ordinary background versions and temporary detail outages; Retry remains operable within the active edit. A changed session/client/purchase identity, assignment, finality or active scope retires the old editor, including loss of permanent client assignment for completed-session corrections. Definitive access denial clears private detail; Cancel reloads current values. A background read never silently replaces an unsaved booking time. Confirmations belong to their requesting screen and reviewed edit: unmount, session termination or a retired navigation edit cancels the pending decision and removes private previews without issuing a write. Late callbacks from retired screens and old abort signals cannot reopen or decide a newer confirmation. Delayed opening reviews for assignment, account/package lifecycle and weekly schedules must not claim the editor after their control retires or another edit disables it, even if that intervening edit has subsequently ended.

<a id="br-011"></a>

**BR-011** — Errors retain a readable message and stable error code. Session expiry clears private UI; account/generation changes reject stale replies. Missing/foreign records must not leak private scope. Stale reviews require a fresh review after a definitive conflict. Pending proposals leave the current booking unchanged until an authorized decision. Approval/Undo controls require their own connected operation and evidence.

### Product invariants

<a id="br-012"></a>

**BR-012** — Purchased package terms are immutable snapshots. Standard validity is 12 sessions/90 days, 24/180 and 36/270; inclusive end is start plus validity minus one. Catalogue edits do not rewrite purchased/custom terms, used credits or prior evidence.
<a id="br-013"></a>

**BR-013** — Add Client/Add Package share the reviewed matching wizard: Continue/Back/Edit do not persist. Revalidate active/versioned package, preference, availability, full cadence, validity and client/Trainer conflicts at final save. Queued purchases do not overlap existing eligible purchase validity and activate in Singapore business time under the retained lifecycle rules.
<a id="br-014"></a>

**BR-014** — Open sessions have stable identity but no date/time or chronological session number. Scheduling preserves purchase identity, purchased validity and credits. Postponement returns only the eligible target to Open; subsequent positions may change without moving other bookings. Scheduling reads do not complete scheduling writes.
<a id="br-015"></a>

**BR-015** — Supervised Trainer changes require an Owner/Admin operations decision; autonomous changes still require current assignment, policy and conflicts. Permanent reassignment and fixed weekly edits retain their separate scopes and reviewed evidence.
<a id="br-016"></a>

**BR-016** — Completed/acknowledged evidence is immutable under its domain rules. Acknowledgement and package Add/Deactivate do not have generic Undo. The distinct Delete Upcoming Sessions action retains its permitted 24-hour reversal without reactivating the purchase. Reactivation preserves expiry, credits and completed history and does not recreate deleted sessions.
<a id="br-017"></a>

**BR-017** — Package deletion retains stable session identities, typed booking archives, plans/results and audit records. Only Open or strictly future unacknowledged bookings qualify; completed/cancelled sessions, credits and approved-pay evidence remain protected. Separate deletion requires an inactive purchase and permits operations-only Undo within24 hours, subject to unchanged purchase/client/session evidence and actual unexpired media bytes. Restoration keeps original IDs/creation times, increases versions and never reactivates the purchase. Pending requests are rejected atomically; original decision history is retained. Cleanup keeps its immutable original reason and respects the earlier of the Undo hold and original media expiry. Generic Undo acceptance still requires all other permitted operation kinds.
<a id="br-018"></a>

**BR-018** — Previous Plan uses a preview and explicit confirmation before replacing the target plan (YS,23 October). That decision supersedes the historical undecided UI note; its source acceptance is recorded in the matrix. Copy prescriptions and details into new exercise identities; videos retain their original session ownership. Source selection uses the latest readable nonempty plan on a strictly earlier calendar date, excluding Open sessions.
<a id="br-019"></a>

**BR-019** — Plans, outcomes, summaries, credit accounting, remuneration, reports and media require their own durable workflows; database models alone do not complete them. Never fabricate WhatsApp/native-share sent or delivered states.
<a id="br-020"></a>

**BR-020** — General health-note and remarks drafts may survive a transient connection failure in memory only. Hide private UI while identity is unverified; restore only for the same verified user, role and login generation, retaining the original reviewed version. Clear drafts on logout, changed authority, explicit discard or successful save. This is not offline persistence or permission to replay an uncertain write.
<a id="br-021"></a>

**BR-021** — Preserve approved prototype appearance, navigation and workflow parity. Account-scoped Back/Forward/view state uses one navigation owner; editable drafts stay local and guarded. Client/person, couple identity, onboarding fields, signatures and detailed display decisions are retained in the [retained design history](journey.md#complete-journey); later explicit decisions take precedence.

### Permitted Undo

<a id="br-022"></a>

**BR-022** — Undo is an explicit reviewed compensating transaction within 24 hours of the original server write. Owner/Admin or the original active Trainer must still have current record scope and applicable scheduling autonomy. A visible message alone grants no write authority. Current domain state, child records, dependent bookings, pending proposals and original media must still match the reviewed change; reverse later dependent changes first. Started schedules, acknowledged/credited scheduling changes and approved pay-cycle changes cannot be reversed through Undo.

<a id="br-023"></a>

**BR-023** — Retain typed immutable before/after records, original command receipts, event/decision history and identities. Compensation advances versions, appends lifecycle/assignment/outcome evidence and never rewinds credits or revives revoked logins. A pending supervised proposal becomes cancelled with a new event; an approved decision remains approved with a separate reversal projection. Restoring recordings requires verified original bytes, current access, no cleanup lease and the unchanged original expiry. Handoff reversal cannot recall an external message or establish delivery. Package creation/status and acknowledgements are excluded; deleted package-session restoration remains in its separate package lifecycle owner.

<a id="br-024"></a>

**BR-024** — One actor-private original key governs an interrupted Undo. Recover its receipt before another write; changed intent, competing commands, expired windows and lost authority reject without partial effects. PR80 provides source acceptance for full permitted Undo; browser, PostgreSQL, migration and full final-head CI evidence is retained in [Journey](journey.md). Deployment and live acceptance remain separate.

### Reviewed acknowledgement and credit accounting

<a id="br-025"></a>

**BR-025** — Completion binds the current session, client, purchase, plan/results, Singapore business date and used-credit balance. Only signature or late/no-show is accepted; signatures require actual bounded ink and a signer name. The server rejects future/open/cancelled sessions, inactive records and unauthorized/foreign targets. No-show may be corrected only to a signature, preserving both immutable acknowledgement records and exactly one debit. Completed ad-hoc cover remains read-only.

<a id="br-026"></a>

**BR-026** — Acknowledgement, completion, any legacy numeric plan measurements, one credit debit, the two-credit renewal notice and the actor-private original-command receipt share one transaction. An explicitly saved empty outcome stays empty. A later active purchase suppresses renewal; an existing purchase notice is not duplicated. No external message or delivery is recorded. Lost responses freeze the original intent until recovery, and replay does not reauthorize a new write or debit again. Populated receipt downgrades refuse evidence loss. PR72 provides source acceptance; deployment and live acceptance remain separate.

### Report actions and retained history

<a id="br-027"></a>

**BR-027** — Report audit writes record PDF export/share or legacy WhatsApp opening, never delivery or receipt by a client. The browser performs the explicit device action once; saving or recovering its audit must not repeat a download/share. Each new action has a stable UUID, explicit client/purchase membership and server-derived actor/time. Reusing an action ID with different intent or another actor conflicts without disclosing the prior private receipt. Audit and its internal notice commit together. Historical/inactive report access remains distinct from current coaching-write authority.

<a id="br-028"></a>

**BR-028** — Only Owner/Admin may read report history. Filtering by purchase must not mix another purchase or client. Existing CSV and legacy unassigned-purchase evidence remain readable; new CSV actions and new actions without a purchase are rejected. History is immutable, deterministically ordered and fails closed if it cannot be returned completely within its bounded contract. Unknown writes freeze audit intent and can recover after a focus refresh without repeating the native action. Physical-device sharing and actual provider delivery remain separate acceptance.

### Legacy session opening compatibility

<a id="br-029"></a>

**BR-029** — API-backed sessions with integrated summary support may export the existing PDF when current scope, active lifecycle and training date permit; unavailable mutations remain disabled. `markWhatsAppOpened` remains an explicit compatibility action; the current PDF UI does not call it or display a WhatsApp button. Its server review binds the session, client/purchase lifecycle and Singapore business date. New actions reject foreign, Open, future and inactive records; terminal historical cover remains read-only. One intent increments the opening count/time and version, records truthful audit/internal notice evidence and stores the actor-private original result atomically. Replaying that intent never adds another opening, and conflicting key reuse is rejected. Completion, signatures, credits and remuneration remain unchanged. This records an opening, never sending or delivery. No real messaging provider is called.

### Authentication and additional routes

<a id="br-030"></a>

**BR-030** — Trainer email correction: Managers must review the current pending request and Trainer version before replacing a stable requested/pending address. Sending/verifying ambiguity blocks correction. Superseded commands stay immutable, and earlier destinations remain reserved until the replacement is provider-verified; the database releases the entire predecessor chain with completion, including completion by the outgoing application. Corrections inherit send budgets/cooldowns and do not send mail. Only the account holder can send/verify a fresh code, and stale forms cannot verify a superseded request. Local login/recovery stays unchanged until verified provider readback and atomic completion revoke existing sessions. Creation is disabled by default until compatible-runtime cutover; after any correction exists, use only correction-aware rollback code. The completion compatibility regression covers reservation release, not old pending-request readers. PR77 provides source acceptance.

<a id="br-031"></a>

**BR-031** — Authentication includes enrollment/challenges, repeated login, session refresh/expiry, logout, password recovery and verified email changes. Evidence owners are [stored session lifecycle and races](../backend/tests/test_auth_sessions.py), [HTTP/JWT/cookie/CSRF security](../backend/tests/test_auth_security.py), [bootstrap and expiry](../backend/tests/test_auth_bootstrap.py), [enrollment/password/navigation browser workflows](../tests-api/authentication.spec.js), [verified email browser workflows](../tests-api/email-corrections.spec.js), [operator recovery drill](../backend/tests/test_mfa_recovery_drill.py) and [actual process restart](../backend/tests/test_process_restart.py). These use isolated storage and synthetic provider responses; live Cognito and physical-device receipts remain separate. See the implemented OpenAPI schema and [architecture explanation](architecture/adr.md). Session/calendar reads expose persisted assigned/authorized records and stable IDs; they do not add operations to this matrix. Assessment history and scoped directory routes likewise support the owning domain workflows.


### Outcome corrections and persisted progress

<a id="br-032"></a>

**BR-032** — Reviewed outcome saves retain measured loads/reps/sets and comments, deriving duration from the booking. Corrected or removed measurements retain stable identities and immutable prior revisions. They do not change completion status, signatures, acknowledgement history, package credits or remuneration approval evidence. Owner/Admin and the current assigned Trainer may correct eligible records; completed/cancelled ad-hoc cover remains read-only. Inactive clients/purchases reject writes. Original actor/key recovery remains possible after reassignment without granting new edit authority.

<a id="br-033"></a>

**BR-033** — Only signed completed attended results contribute to purchase-scoped progress; no-shows are excluded. An explicitly saved empty outcome never resurrects prescription defaults. Current full-profile scope and session visibility both apply to the projection; cover-session access does not grant full client progress. Outcome persistence and progress reads do not complete summary, acknowledgement, report-export/history or media operations. The matrix records source acceptance separately from deployment.

### Client-facing summaries

<a id="br-034"></a>

**BR-034** — A summary is reviewed client-facing text, saved separately from measured outcomes and completion. Replacing it retains immutable prior text, actor/time and the original command receipt. Current session assignment and active client/purchase authority apply; completed/cancelled ad-hoc cover remains read-only. A summary save never changes signatures, credits, measurements, or WhatsApp/share/delivery state. The editor requires nonblank text; the server enforces the bounded text contract and stale-version rejection. Source acceptance remains governed by the operation matrix.

### Product scope and retained design decisions

<a id="br-035"></a>

**BR-035** — **Scope and authority.** The staff portal preserves approved appearance, navigation and Owner/Admin/Trainer workflows. Public pages (Home, Gym Membership, Personal Training, About and agreed supporting content), the Glofox purchase handoff and website-specific content management remain a separate deliverable after the portal. Public members do not enter the staff portal. Cognito authenticates members; the backend checks Glofox entitlement for the member Exercise Library. Glofox credentials stay server-side; API entitlement, branch identifiers and fees remain prerequisites. Instructional library media and private session recordings are distinct.

<a id="br-036"></a>

**BR-036** — **Undecided scope.** Owner Profile remains read-only; additional Setup pages, payment collection and commercial overlapping-package eligibility are not inferred from existing services. Copy Previous Plan is now decided: preview, then confirm replacement. Session filming and production media processing still need separate acceptance.

<a id="br-037"></a>

**BR-037** — **Identity and personal fields.** Staff passwords are 15–128 characters without whitespace; long passphrases are allowed without a mandatory character-class mix or routine forced rotation. Staff MFA remains required. New-client onboarding requires type and each person's name, phone country code/number, email, birthday, gender and complete emergency contact; both members of a couple retain their own identity. Health/limitation notes and shared remarks are optional. New Trainers require name, email, phone, birthday, gender and type; qualifications are optional and Public profile defaults Visible. Trim names and reject blanks; display-name corrections preserve stable IDs, signatures and audit names. A couple display name never overwrites either person's name.

<a id="br-038"></a>

**BR-038** — **Onboarding and purchases.** Validate one wizard section at a time and preserve Back/Edit drafts; save only after final confirmation. Session counts accept bounded integers, not decimals, signed or exponential notation. Add Package reuses onboarding steps 2–5. Match an active template by saved ID, or unambiguous legacy session-count/validity; otherwise require selection. Prefill preferences, availability, exact weekly slots and Trainer. Propose a start after every noninactive purchase's inclusive end and no earlier than today. Additional purchases retain independent terms and settings until once-only business-date activation; inactive clients/purchases cannot activate. Existing sessions, personal data, original client start date, signatures and credits remain unchanged. Revalidate actual bookings and purchase overlap even when the older purchase has no remaining sessions.

<a id="br-039"></a>

**BR-039** — **Lifecycle and scope.** Owner/Admin lifecycle operations retain actor, time, reason and history. Historical assignment grants scoped read access, not mutation authority. Client/purchase inactivity blocks all content, scheduling, media, outcome, summary, acknowledgement and handoff mutations, including checks after asynchronous storage. Authorized read/report audits remain separate.

| Record | Deactivation | Reactivation |
| --- | --- | --- |
| Client | Freeze the client and its active purchases; retain sessions and history by default. | Restore only purchases disabled by that client action. Independently inactive purchases and ambiguous legacy provenance stay inactive; deleted sessions are not recreated. Revalidate retained scheduling without resetting expiry or used credits. |
| Trainer | Require an active, conflict-free replacement for every unfinished/non-cancelled session on an active client and active purchase, including Open sessions. Reassign the complete reviewed set and deactivate the Trainer/linked application account atomically; revoke existing login sessions. Permanent client reassignment remains a separate operation. | Restore the Trainer and linked application account without reclaiming reassigned sessions or changing purchases/history. Fresh sign-in is required; never revive closed sessions, create a missing provider account or re-enable a separately disabled provider identity. |
| Purchased package | Freeze only that purchase; retain terms, expiry, credits and sessions by default. Explicit deletion can remove eligible upcoming/Open bookings; deactivation itself has no generic Undo. | Restore only the reviewed purchase after scheduling checks, preserving expiry and used credits. Never recreate deleted bookings. |
| Catalogue package | Remove the template from new-purchase selection without changing existing purchased snapshots. | Restore catalogue eligibility without rewriting purchased terms or creating purchases. |

<a id="br-040"></a>

**BR-040** — Only strictly future bookings or Open sessions that are unfinished/non-cancelled and have no acknowledgement history or credit transactions qualify for explicit deletion. Cleanup rejects related pending requests and queues durable media deletion atomically; an empty retry adds no duplicate history. The separate Delete Upcoming Sessions action retains its conditional24-hour Undo, restoring original sessions while leaving the purchase inactive. Full deletion/media safeguards are stated under Product invariants above.


<a id="br-041"></a>

**BR-041** — **Reassignment and weekly schedules.** Permanent reassignment updates current and noninactive additional purchases plus eligible upcoming sessions, preserving times, terms, results and completed/started/cancelled evidence. It validates replacement availability/preferences and supersedes affected pending proposals. Weekly edits affect eligible current-schedule bookings, including unambiguous older-purchase records, without changing dates, IDs or Trainer assignments; separately scheduled additional purchases keep their own times. Resolve legacy slots by explicit slot ID, weekday, sole slot, then unique old time; ambiguity or conflicts reject the whole change. Duration derives from each booking's From/To times, not a stale stored duration.

<a id="br-042"></a>

**BR-042** — **Requests.** Time changes require both old and proposed starts strictly after the server's Singapore business time. Completed/cancelled bookings cannot be changed through these requests. Supervised proposals preserve underlying records until approval; autonomous changes still revalidate current scope and conflicts. Approval rechecks the frozen proposal and current state atomically. Stale pending requests may be rejected or cancelled without applying them. Only the originating active Trainer can cancel a pending request; terminal requests cannot be withdrawn. Cancellation preserves proposal, IDs and read state, records actor/time and one notice per recipient, never reverses domain effects, and races with decisions to one authoritative winner.

<a id="br-043"></a>

**BR-043** — **Completion, credits and remuneration.** Signature/no-show and legacy handoff actions unlock on the gym-local training date, not before it. A signature requires signer name and actual normalized finite SVG ink on a 600×200 surface with bounded strokes/points. Saved signatures are read-only; no-show may be corrected only to a signature, retaining both snapshots and actor/time. Completion consumes at most one credit; retries/corrections never debit or pay twice. Outcome duration and WhatsApp are not completion prerequisites. Signed attended results drive progress by stable session/result identity; no-shows do not. Explicitly empty results stay empty; numeric plan loads supply legacy results only when a result list is absent. Blank or nonnumeric loads are not measurements.

<a id="br-044"></a>

**BR-044** — Use saved rates and gym-local start time. Weekday peak windows are 06:30–08:30 and 18:00–20:30 with exclusive ends; weekends are peak all day. The pay cycle runs from the 16th through the next 15th and closes after that day. No-shows receive the applicable full rate with no attended minutes. Incomplete, invalid or future completion evidence prevents approval; frozen unfinished inactive records neither earn pay nor block approval. Approval retains its amount/evidence snapshot, rejects stale/duplicate approval and displays later source differences separately. Owner-only rates/approval and Admin financial restrictions above supersede older role descriptions in history. An API approval binds the reviewed cycle, trainer and source fingerprint; approval, typed lines, internal notice and recipient records commit together. Its actor-private receipt recovers the original approval after a lost response. This records approved remuneration, not a transfer or provider payment. Later rate/name changes leave the approved amount and names fixed; later attendance/booking evidence differences are shown separately. Financial reads are loaded on the remuneration route, not included in the general directory.

<a id="br-045"></a>

**BR-045** — **Messages and renewal reminders.** Read/unread belongs independently to each recipient; category/filter navigation does not mark records read. Typed metadata, not titles, determines categories. A fresh credit debit creates a single package-instance reminder at the configured remaining-session threshold (two: 10/12, 22/24, 34/36), atomically with usage. Retries and no-show corrections cannot duplicate it. Existing reminders survive later usage and reads; an old-package debit never notifies for a new purchase. Dashboard previews show at most three rows while totals include every visible reminder. Reading a reminder does not resolve it. Legacy normalization preserves unrelated records and publishes only after successful persistence.

<a id="br-046"></a>

**BR-046** — **Reports and sharing.** Every session, debit, result and new report audit carries its purchase identity. Resolve legacy links only from reliable provenance or one unambiguous purchase; retain unresolved evidence outside visible progress, never guess an exported purchase. Reports and history are purchase-scoped with independent ten-row pagination and retained Back/filter/selected-exercise state. Only one exercise chart expands; exports include all recorded exercises. Owner/Admin history remains out of Trainer snapshots. Reports use the canonical chart/PDF renderer, with serial rendering to bound memory.

<a id="br-047"></a>

**BR-047** — Download and Share PDF use the same prepared file. Equivalent refreshes retain it; content/purchase changes invalidate it and late work cannot replace it. Native sharing must retain user activation and check actual file support; failure offers Download/Open PDF and rendering failure offers Retry PDF. Cancellation/rejection records no share. Record `pdf_share_opened` only after native share resolves; it proves neither WhatsApp selection nor delivery. Failed audit persistence retries the same action ID without sharing/downloading again. Legacy CSV/WhatsApp events retain truthful labels; new CSV actions are rejected. Current session PDF export selects video captions and an optional checked-by-default client summary; no content means Continue disabled. Captions do not attach video bytes, and this export does not update legacy WhatsApp handoff fields.

<a id="br-048"></a>

**BR-048** — **Exercise Library.** Owner/Admin manage metadata and attachments; authenticated Trainers receive active catalogue entries only. Normalize names and reject duplicates/reserved custom names; retain approved categories, 180-character names and 2,000-character descriptions. Existing saved session plans retain their names and identities. Reference attachments accept nonempty JPEG/PNG/WebP/MP4/WebM/MOV up to50MiB. Reserve an actor-private immutable original command and unique object key before upload; short-lived conditional signatures bind length/type/checksum. Publish only after verifying stored bytes and rechecking current authority/version. An interrupted save reconciles its original key and bytes; different intents cannot reuse it. Notices and the final receipt commit atomically with the exercise. Reads require a current permitted attachment and a post-fetch scope check; signed URLs and bytes never enter durable browser snapshots. Replacements/removals deny new reads immediately but queue physical deletion until every upload lease expires. Abandoned uploads expire into durable cleanup; leased work survives lost responses and process death. Signature/header validation is not codec/transcoding or AWS deployment acceptance. Production activation and scheduling remain separate.

<a id="br-049"></a>

**BR-049** — **Session recording.** Reserve an actor-private frozen command and unique immutable object before uploading; verify stored bytes and recheck current session, plan, client/purchase and staff authority before publication. Replacement/removal preserves exercise identities and purchased credits. Publication fixes expiry to seven days from its server transaction; only that pending-to-ready transition can finalize expiry, and later edits/Undo never extend it. Read leases end by original expiry and playback requires a post-download scope/version check. Abandoned uploads and detached originals retain durable cleanup work, upload-lease protection and applicable Undo holds. Client-reported duration/audio/processing metadata is not verified transcoding evidence; M7 processing and physical capture acceptance remain separate.

<a id="br-050"></a>

**BR-050** — **Media.** Saved session media retains service-assigned attachment/expiry times and original session ownership. Completed-session playback may remain available, but replacement/removal controls obey finality. Check permission and expiry before and after fetching bytes; failed deletions remain retryable. The demo accepts nonempty video up to 5 MiB and normally readable duration up to 60 seconds; deferred processing/audio/unknown-duration fallbacks do not establish production compliance. Production requires protected storage, server-time expiry denial, lifecycle/orphan cleanup and separately accepted processing/capture behavior. Missing bytes must not produce successful metadata. Never treat local browser storage as durable production media.

<a id="br-051"></a>

**BR-051** — **Navigation, calendar and controls.** One owner manages account-scoped history, edit guards, confirmations and modals. Tabs, filters, pagination, scroll and selected charts survive Back/Forward/reload; drafts stay local and guarded. Async results cannot update another account or route. Navigation starts collapsed and allows one expanded category. Sessions initially show nearest Upcoming; All orders date/start descending with stable ID ties. Open sessions have no chronological number. Weekly calendar starts today and spans seven consecutive days; arrows move seven days. Monthly uses actual dates with Monday alignment and blank outside cells. Empty dates have no count/focus action; Trainer Weekly lists every session without a preview cap. Day routes preserve calendar context and role scope.

<a id="br-052"></a>

**BR-052** — Use shared SelectField, DateField and SuggestionField behavior, keyboard/disabled semantics, viewport-bounded menus and the existing modal/edit owner. Required controls start with the approved pink border; invalid controls strengthen it and optional controls remain neutral. Keep compact operational rows, approved dark palette, responsive profile navigation and accessible full labels. Installed touch PWAs prefer portrait with an isolated rotation fallback that preserves drafts; keyboard-reduced viewport size must not masquerade as rotation. Real Samsung/iPad picker, capture, sharing, orientation and scrolling behavior needs physical acceptance. Private APIs/media must not become offline cached public content.

<a id="br-053"></a>

**BR-053** — **Trainer attribution and assignment evidence.** Preserve three distinct identities: the original session Trainer, the current assignee and the Trainer credited at completion. The Owner/Admin who records acknowledgement is not the performer. Reassignment and Undo never rewrite original attribution, completed performer evidence or approved remuneration. Append assignment edges with their original actor, timestamp and reason; supervised changes also retain the request and initiating/approving actors. Historical session reads may consult original/assigned/performed Trainers and assignment history, but they do not grant broad client-profile access or current write authority. Keep original/performer evidence against the stable session identity so deletion and restoration of a live booking cannot erase it. Backfill only supported facts: completed assignments are protected evidence; a purchase snapshot alone does not prove original session ownership. Explicitly flag unresolved legacy originals rather than infer them. Preserve the outgoing assignment column during additive migration and reject a populated downgrade that would discard attribution.

<a id="br-054"></a>

**BR-054** — **Schema and design.** Identity, assignment, scheduling, packages, credits and money stay typed relational data. JSONB is limited to approved optional metadata and versioned validated assessment answers; sensitive answers retain explicit access control. Keep frontend/domain/persistence/infrastructure boundaries and one canonical code owner. Stateless application compute and stable HTTP contracts permit future hosting changes without buying idle capacity now.

### Assessment records, business policy and retained capacity decisions

<a id="br-055"></a>

**BR-055** — Each assessment belongs to one `client_people` person and one occasion, never a couple's shared account. The approved registry has 11 forms and 303 unique paper fields with immutable form/layout/PDF digests and retained render assets. Relational headers and immutable versioned JSONB revisions retain assessor, recording actor, displayed name/DOB and server time. Explicit Save appends a draft; completion appends a completed snapshot; corrections require a reason and retain submitted identity; reasoned void is terminal. Reassessment creates a new occasion. Commit revision and current pointer atomically with optimistic version checks and actor/operation/target/body-scoped retry evidence. Do not autosave a revision per keystroke or import browser records automatically.

<a id="br-056"></a>

**BR-056** — Version-1 answers reject unknown keys, invalid options/types/ranges, nonfinite numbers and oversized payloads. Missing answers remain absent, zero remains zero, checked boxes retain `"Yes"`, and unchecked boxes are absent. Text is bounded to 500 characters, textarea answers to 4,000 and each answer object to 65,536 UTF-8 bytes. Drafts may be empty; completion requires an answer except an explicitly saved unchecked six-checkbox hurdle checklist. No diagnosis, clinical clearance, compulsory-form policy, reassessment cadence or training block is inferred. Preserve genuine legacy supplementary answers for explicit import review without inventing questions or silently discarding evidence. Initial-form access remains Owner/Admin only; assigned general health notes are separate.

<a id="br-057"></a>

**BR-057** — Business time is `Asia/Singapore`, locale `en-SG` and currency SGD. Package counts are integers 1–365; standard validity is 90 days per 12 sessions rounded up, including the explicit 12/24/36 mappings above. Weekly frequency is 1–7; gym inclusion starts at two sessions per week. Renewal threshold is loaded policy, default two. Session video retention defaults to seven days from save, preserving original expiry after later configuration changes. Pay-cycle payout is the 16th. Loaded policy is authoritative for display; the server rechecks time and rules on writes. Missing records never invent an Owner, catalogue or purchased package.

<a id="br-058"></a>

**BR-058** — The retained initial capacity design is private encrypted Singapore PostgreSQL, TLS, separate migration/runtime identities and least privilege; Single-AZ `db.t4g.micro`, 20 GiB gp3 and a reviewed autoscaling ceiling are planning choices, not current capacity proof. The 14-day backup/PITR target, measured restore objectives, retention and any Multi-AZ promotion require release review. The S$60–90/month target is conditional historical budgeting, not a current quote; it assumed the reviewed NAT-instance option and excludes separate staging, substantial media traffic and labour. Re-price before provisioning. Private Lambda-to-RDS traffic needs no NAT; external calls need reviewed egress. No extra document database, managed proxy or search engine is selected. Avoid blanket JSONB indexes without measured queries; any longitudinal assessment projections must be unit/version-aware derivatives of canonical answers.

### Deployment, migration and acceptance

<a id="br-059"></a>

**BR-059** — AWS image publication requires manual initiation for an explicitly entered main commit SHA, complete frontend/backend/API-browser verification of that same SHA, and the existing protected AWS environment approval. Ordinary verification/demo publishing must not wait on image approval. New manual candidate receipts bind the canonical workflow, run/attempt, source, artifact and image digest; historical candidates retain their original evidence rules. Publication is separate from Lambda deployment and migrations.

<a id="br-060"></a>

**BR-060** — Preserve existing database, Cognito pool/Owner, retained buckets and successful edge. Historical creation, deletion and replacement procedures are completed evidence, not steps to replay. New source needs a matching reviewed artifact/image, provenance/security review, populated-database migration/grant/backup/recovery plan and applicable authorization. Old source/image manifests must reject incompatible new bytes. Historical security exceptions have expired; neither renewal nor teardown is implied.

<a id="br-061"></a>

**BR-061** — Applied migrations are immutable. Additive schema changes must tolerate existing rows and outgoing code; review locking/runtime costs. Destructive evolution uses expand → compatible code/backfill → verified transition → later contract after the rollback window. Alembic success does not prove application compatibility, and downgrade cannot reconstruct deleted data. Code rollback does not reverse financial/database effects. Resource/network identity, least privilege, secret protection, capacity and cost remain part of release review; selected WAF/throttling or observability designs do not establish deployed controls.

### Milestones and retained acceptance criteria

<a id="br-062"></a>

**BR-062** — The [full milestone overview in Journey](journey.md#full-milestone-roadmap) owns M0–M10 scope and milestone exit criteria; [Progress](../PROGRESS.md) owns current status. This section owns the cross-cutting acceptance requirements. The 55-operation matrix does not replace later event/media, public-site, staging or launch acceptance.

<a id="br-063"></a>

**BR-063** — The staff-portal goal is all 55 matrix operations, plus authentication and route parity. Completion needs durable behavior, server permissions, prototype parity and meaningful real-database evidence, not an endpoint or API-enabled flag. Shared data must survive reload, sign-out, another browser/device and service restart. Conflict, idempotency and unknown-write recovery must preserve intent and exactly-once effects. Equivalent data must demonstrate layout, navigation, filters, pagination, Back behavior, accessibility and responsive parity without fabricated schedules or missing workflows.

<a id="br-064"></a>

**BR-064** — All final-head frontend/backend/API-browser CI must pass. Real enrollment/login/refresh/expiry/sign-out, account lifecycle and secure lost-authenticator recovery, physical desktop/Samsung/iPad checks, populated recovery and release acceptance remain separately evidenced. Preserve historic milestone IDs and criteria in [Journey](journey.md); no blanket M4/M5/M6 closure follows from a source increment. Public-site design/content/routes, Glofox handoff, member authorization and authorized publication have their own acceptance after portal completion.



