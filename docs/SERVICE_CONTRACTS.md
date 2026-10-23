# Portal service contracts

[Architecture](Architecture/README.md) · [Diagrams](Architecture/diagram.md) · [North Star](../NORTH_STAR.md) · [Progress](../PROGRESS.md)

This document owns current service rules and the **single 55-operation matrix**. The registry in [`portalContracts.js`](../src/services/portalContracts.js) owns named inputs/results; [`openapi.json`](../backend/contracts/openapi.json) describes implemented HTTP schemas. Progress owns revision-specific CI, merge and deployment receipts. Neither a route nor a schema establishes completed integration.

## Service boundary

The React UI calls asynchronous services through `createPortalServices`. Explicit demo mode uses the prototype adapter; API mode uses `apiPortalAdapter` and never falls back to demo storage. `load()` returns the authorized user, policy, capabilities and data snapshot; `invoke()` returns the canonical saved record or declared domain result. Unsupported operations fail explicitly and their controls remain unavailable. Capabilities describe the current API surface, not a client-side permission grant.

Authentication and session/calendar reads are additional acceptance requirements, outside the 55 named domain operations. Reads return only authorized records; client selectors may select locally from that scoped snapshot. `trainerService.isSelectableForAvailability` is a local predicate, not an HTTP write or substitute for server conflict checks.

## Authority and privacy

- Owner/Admin manage operations; Trainers act only within current assignment and policy. Recheck active account, assignment, versions and permissions inside the write transaction. Historical coverage/read access does not confer mutation rights.
- The initial **11 assessment forms are Owner/Admin-only**. Current assigned Trainers may read/edit general health notes separately. Report history and clinical access retain their distinct permission checks.
- Rates are Owner-only to change; Admin cannot read rate/remuneration data. Remuneration approval is Owner-only. Trainer request cancellation is restricted to the originating Trainer and a pending request.
- Trainer login/recovery email changes verify the new address with a code before switching. Do not infer completion of all Trainer profile fields from one implemented branch.
- Verified identity, HTTP-only cookies, CSRF and server-side authorization protect API writes. Browser roles, record IDs and hidden controls are never authority. Media access must be authorized; no private credentials, health data or tokens in diagnostics.

## Persistence, conflicts and recovery

A reviewed command binds its exact intent, current versions and actor-scoped idempotency key. Validate conflicts and authority again at commit; commit business records, version changes, history/notices and durable receipt atomically where the command requires them. A definitive rejection changes nothing. A lost response is an unknown outcome: reconcile the original receipt and retain the original intent/key; never automatically issue a replacement write. A failed refresh after a committed save does not turn that save into a failure.

Errors retain a readable message and stable error code. Session expiry clears private UI; account/generation changes reject stale replies. Missing/foreign records must not leak private scope. Stale reviews require a fresh review after a definitive conflict. Pending proposals leave the current booking unchanged until an authorized decision. Approval/Undo controls require their own connected operation and evidence.

## Product invariants

- Purchased package terms are immutable snapshots. Standard validity is 12 sessions/90 days, 24/180 and 36/270; inclusive end is start plus validity minus one. Catalogue edits do not rewrite purchased/custom terms, used credits or prior evidence.
- Add Client/Add Package share the reviewed matching wizard: Continue/Back/Edit do not persist. Revalidate active/versioned package, preference, availability, full cadence, validity and client/Trainer conflicts at final save. Queued purchases do not overlap existing eligible purchase validity and activate in Singapore business time under the retained lifecycle rules.
- Open sessions have stable identity but no date/time or chronological session number. Scheduling preserves purchase identity, purchased validity and credits. Postponement returns only the eligible target to Open; subsequent positions may change without moving other bookings. Scheduling reads do not complete scheduling writes.
- Supervised Trainer changes require an Owner/Admin operations decision; autonomous changes still require current assignment, policy and conflicts. Permanent reassignment and fixed weekly edits retain their separate scopes and reviewed evidence.
- Completed/acknowledged evidence is immutable under its domain rules. Acknowledgement and package Add/Deactivate do not have generic Undo. The distinct Delete Upcoming Sessions action retains its permitted 24-hour reversal without reactivating the purchase. Reactivation preserves expiry, credits and completed history and does not recreate deleted sessions.
- Plans, outcomes, summaries, credit accounting, remuneration, reports and media require their own durable workflows; database models alone do not complete them. Never fabricate WhatsApp/native-share sent or delivered states.
- Preserve approved prototype appearance, navigation and workflow parity. Account-scoped Back/Forward/view state uses one navigation owner; editable drafts stay local and guarded. Client/person, couple identity, onboarding fields, signatures and detailed display decisions are retained in the [product decision history](history/rules-and-architecture-2026-10-23.md#frontend-architecture); later explicit decisions take precedence.

## Domain operation inventory

**27/55 accepted in merged source: 26 server-connected and one local predicate.** 28 remain unaccepted, including partial Trainer update. Three scheduling operations and request resolution have unmerged candidates. This is source integration, not deployed or production acceptance. PR60 added real PostgreSQL coverage without adding named operations. Current validation and proposed increments belong only in [Progress](../PROGRESS.md).

Each connected server row names actual PostgreSQL/HTTP and real-API browser evidence owners. Browser scenarios can cover several operations. Simulator tests supplement these tests; they do not establish persistence. Local execution uses temporary Docker PostgreSQL, synthetic records and a local signed-token Cognito substitute. Real Cognito, restart, physical devices and deployment acceptance remain separate.

| Named operation | Source status | Permission policy | Real API evidence owners |
| --- | --- | --- | --- |
| `staffService.createAdmin` | Connected | owner | [`test_admin_api.py`](../backend/tests/test_admin_api.py); [`staff.spec.js`](../tests-api/staff.spec.js) |
| `contentService.save` | Connected | Owner/Admin | [`test_content_api.py`](../backend/tests/test_content_api.py); [`records.spec.js`](../tests-api/records.spec.js) |
| `clientService.getAll` | Connected | authenticated | [`test_directory_api.py`](../backend/tests/test_directory_api.py); [`records.spec.js`](../tests-api/records.spec.js) |
| `clientService.getById` | Connected | authenticated | [`test_directory_api.py`](../backend/tests/test_directory_api.py); [`test_client_notes.py`](../backend/tests/test_client_notes.py); [`records.spec.js`](../tests-api/records.spec.js) |
| `clientService.create` | Connected | operations | [`test_client_creation.py`](../backend/tests/test_client_creation.py); [`test_client_matching.py`](../backend/tests/test_client_matching.py); [`records.spec.js`](../tests-api/records.spec.js) |
| `clientService.renewPackage` | Connected | Owner/Admin | [`test_client_renewal_review.py`](../backend/tests/test_client_renewal_review.py); [`test_client_renewal_save.py`](../backend/tests/test_client_renewal_save.py); [`test_purchase_activation.py`](../backend/tests/test_purchase_activation.py); [`records.spec.js`](../tests-api/records.spec.js) |
| `clientService.deactivatePackage` | Missing | operations | Pending API acceptance |
| `clientService.reactivatePackage` | Connected | Owner/Admin | [`test_package_reactivation_review.py`](../backend/tests/test_package_reactivation_review.py); [`test_package_reactivation_save.py`](../backend/tests/test_package_reactivation_save.py); [`records.spec.js`](../tests-api/records.spec.js) |
| `clientService.deletePackageSessions` | Missing | operations | Pending API acceptance |
| `clientService.update` | Connected: contacts, optional fields, general health notes and remarks | Owner/Admin contact edits; current assigned Trainer may edit general notes; assessment forms remain Owner/Admin | [`test_client_details.py`](../backend/tests/test_client_details.py); [`test_client_notes.py`](../backend/tests/test_client_notes.py); [`records.spec.js`](../tests-api/records.spec.js) |
| `clientService.saveAssessment` | Connected | Owner/Admin only; inactive records read-only | [`test_assessment_workflows.py`](../backend/tests/test_assessment_workflows.py); [`records.spec.js`](../tests-api/records.spec.js) |
| `clientService.saveFixedWeeklySchedule` | Connected | Owner/Admin or current assigned active Trainer; Trainer approval control enforced server-side | [`test_client_weekly_schedule.py`](../backend/tests/test_client_weekly_schedule.py); [`records.spec.js`](../tests-api/records.spec.js) |
| `clientService.reassignTrainer` | Connected | Owner/Admin only; active client and replacement | [`test_client_assignment_review.py`](../backend/tests/test_client_assignment_review.py); [`test_client_assignment_save.py`](../backend/tests/test_client_assignment_save.py); [`records.spec.js`](../tests-api/records.spec.js) |
| `clientService.recordProgressReportAction` | Missing | reportClient | Pending API acceptance |
| `clientService.progressReportHistory` | Missing | operations | Pending API acceptance |
| `clientService.deactivate` | Connected | Owner/Admin | [`test_client_deactivation_api.py`](../backend/tests/test_client_deactivation_api.py); [`records.spec.js`](../tests-api/records.spec.js) |
| `clientService.reactivate` | Connected; open-session retention | Owner/Admin | [`test_client_reactivation_review.py`](../backend/tests/test_client_reactivation_review.py); [`test_client_reactivation_save.py`](../backend/tests/test_client_reactivation_save.py); [`records.spec.js`](../tests-api/records.spec.js) |
| `trainerService.create` | Connected | Owner/Admin; Owner-only submitted rates, Admin server defaults with no financial projection | [`test_trainer_creation.py`](../backend/tests/test_trainer_creation.py); [`staff.spec.js`](../tests-api/staff.spec.js) |
| `trainerService.saveAvailability` | Connected | active Trainer editing self | [`test_trainer_availability.py`](../backend/tests/test_trainer_availability.py); [`records.spec.js`](../tests-api/records.spec.js) |
| `trainerService.getAll` | Connected | authenticated | [`test_directory_api.py`](../backend/tests/test_directory_api.py); [`records.spec.js`](../tests-api/records.spec.js) |
| `trainerService.getActive` | Connected | authenticated | [`test_directory_api.py`](../backend/tests/test_directory_api.py); [`records.spec.js`](../tests-api/records.spec.js) |
| `trainerService.getById` | Connected | authenticated | [`test_directory_api.py`](../backend/tests/test_directory_api.py); [`records.spec.js`](../tests-api/records.spec.js) |
| `trainerService.isSelectableForAvailability` | Local | authenticated | [directory unit tests](../src/services/apiDirectory.test.js); no HTTP operation |
| `trainerService.update` | Partial: profile, Owner rates and verified-email candidates; unresolved-email correction pending | Manager profile/name edits; own active Trainer non-name profile fields; Owner rates | Pending API acceptance |
| `trainerService.updateAutonomy` | Connected | Owner/Admin only | [`test_trainer_approvals.py`](../backend/tests/test_trainer_approvals.py); [`records.spec.js`](../tests-api/records.spec.js) |
| `trainerService.deactivate` | Connected | Owner/Admin only; all remaining active-client/purchase sessions require available replacements | [`test_trainer_deactivation.py`](../backend/tests/test_trainer_deactivation.py); [`records.spec.js`](../tests-api/records.spec.js) |
| `trainerService.reactivate` | Connected | Owner/Admin | [`test_trainer_reactivation.py`](../backend/tests/test_trainer_reactivation.py); [`records.spec.js`](../tests-api/records.spec.js) |
| `sessionService.previewPostponement` | Candidate; acceptance pending | session | [backend](../backend/tests/test_session_postponement_api.py); [browser](../tests-api/session-postponement.spec.js); see Progress |
| `sessionService.postpone` | Candidate; acceptance pending | session | [backend](../backend/tests/test_session_postponement_api.py); [browser](../tests-api/session-postponement.spec.js); see Progress |
| `sessionService.loadVideo` | Missing | session | Pending API acceptance |
| `sessionService.saveVideo` | Missing | session | Pending API acceptance |
| `sessionService.removeVideo` | Missing | session | Pending API acceptance |
| `sessionService.updateDetails` | Candidate; acceptance pending | operationsSession | [backend](../backend/tests/test_session_booking_api.py); [browser](../tests-api/session-booking.spec.js); see Progress |
| `sessionService.requestTimeChange` | Missing | session | Pending API acceptance |
| `sessionService.requestTrainerChange` | Missing | session | Pending API acceptance |
| `sessionService.saveExercisePlan` | Missing | session | Pending API acceptance |
| `sessionService.previousPlanFor` | Missing | session | Pending API acceptance |
| `sessionService.copyPreviousPlan` | Missing | session | Pending API acceptance |
| `sessionService.saveOutcome` | Missing | session | Pending API acceptance |
| `sessionService.saveClientSummary` | Missing | session | Pending API acceptance |
| `sessionService.markWhatsAppOpened` | Missing | session | Pending API acceptance |
| `sessionService.acknowledge` | Missing | session | Pending API acceptance |
| `packageService.save` | Connected | operations | [`test_package_api.py`](../backend/tests/test_package_api.py); [`persistence.spec.js`](../tests-api/persistence.spec.js) |
| `exerciseLibraryService.loadMedia` | Missing | authenticated | Pending API acceptance |
| `exerciseLibraryService.getAll` | Missing | authenticated | Pending API acceptance |
| `exerciseLibraryService.save` | Missing | operations | Pending API acceptance |
| `messageService.dismissRenewal` | Connected | visible renewal; Owner/Admin or current assigned Trainer | [`test_renewal_dismissal_api.py`](../backend/tests/test_renewal_dismissal_api.py); [`records.spec.js`](../tests-api/records.spec.js) |
| `messageService.undo` | Missing | message | Pending API acceptance |
| `messageService.markRead` | Connected | current message visibility; independent recipient state | [`test_message_api.py`](../backend/tests/test_message_api.py); [`records.spec.js`](../tests-api/records.spec.js) |
| `messageService.markUnread` | Connected | current message visibility; independent recipient state | [`test_message_api.py`](../backend/tests/test_message_api.py); [`records.spec.js`](../tests-api/records.spec.js) |
| `requestService.resolve` | Candidate; final API acceptance pending | Owner/Admin; atomic current-state approval or rejection | [`test_request_resolution.py`](../backend/tests/test_request_resolution.py); [`request-resolution.spec.js`](../tests-api/request-resolution.spec.js); not accepted main |
| `requestService.cancel` | Connected | active requesting Trainer | [`test_request_cancellation.py`](../backend/tests/test_request_cancellation.py); [`records.spec.js`](../tests-api/records.spec.js) |
| `remunerationService.list` | Missing | remuneration | Pending API acceptance |
| `remunerationService.detail` | Missing | remuneration | Pending API acceptance |
| `remunerationService.approve` | Missing | approveRemuneration | Pending API acceptance |

Operations means Owner/Admin. Assigned-client edits require current assignment; historical report access is a separate read permission. Assigned-trainer edits require self or operations access. Session commands require the current assigned Trainer or operations access; direct booking-detail edits require operations access. Finer domain validators remain mandatory.

## Authentication and additional routes

Authentication includes enrollment/challenges, repeated login, session refresh/expiry, logout, password recovery and verified email changes. See the implemented OpenAPI schema and [authentication explanation](Architecture/README.md#identity-and-authorization). Session/calendar reads expose persisted assigned/authorized records and stable IDs; they do not add operations to this matrix. Assessment history and scoped directory routes likewise support the owning domain workflows.

## Acceptance and retained detail

Completion requires durable behavior, server permissions, prototype parity, real API/PostgreSQL evidence and all final-head frontend/backend/api-browser CI gates. Every new write includes UI save/reload or fresh-context persistence, stale/conflicting requests, interrupted-write recovery, unauthorized access and foreign records. [AGENTS](../AGENTS.md) owns verification and merge authority; [CODEX_CLOUD](CODEX_CLOUD.md) owns commands. Source merge does not authorize deployment or paid services.

Detailed dated DTO decisions, original failures and historical receipts are preserved in [service decision history](history/service-contracts-2026-10-23.md), [product/architecture decision history](history/rules-and-architecture-2026-10-23.md) and [Journey](FITFINITY_JOURNEY.md). Consult the relevant decision without treating old counts, candidate labels or permissions as current. Architecture explanations and planned observability are not claims of production acceptance.
