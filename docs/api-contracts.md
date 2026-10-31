# Fitfinity API contracts

This document owns the **55 named domain operations**, current HTTP contract index and schema reference. [Business rules](business-rules.md) owns permissions and business invariants; [Journey](journey.md) retains all detailed historical API decisions and receipts, including superseded DTOs and incomplete checkpoints. [Progress](../PROGRESS.md) owns current acceptance. A historical candidate contract does not override the implemented schema.

The frontend [portal contract](../src/services/portalContracts.js) defines named operations; [OpenAPI JSON](../backend/contracts/openapi.json) records HTTP methods, paths, operation IDs, request/response fields, constraints and security. Supporting reads, reviews, receipts, authentication and media transport mean the HTTP route count is larger than55; do not invent additional named operations from those routes.

## Domain operation inventory

**55/55 accepted in merged source: 54 server-connected operations and one local predicate.** PR80 completed full permitted Undo after all required final-head gates passed. Each row below retains its real API evidence owners; full dated implementation, failure, repair and merge receipts remain in [Journey](journey.md). This is source integration, not deployment or production/provider/device acceptance. [Progress](../PROGRESS.md) owns remaining milestone work.

Each connected server row names actual PostgreSQL/HTTP and real-API browser evidence owners. Browser scenarios can cover several operations. Simulator tests supplement these tests; they do not establish persistence. Local execution uses temporary Docker PostgreSQL, synthetic records and a local signed-token Cognito substitute. Real Cognito, restart, physical devices and deployment acceptance remain separate.

| Named operation | Source status | Permission policy | Real API evidence owners |
| --- | --- | --- | --- |
| `staffService.createAdmin` | Connected | owner | [`test_admin_api.py`](../backend/tests/test_admin_api.py); [`staff.spec.js`](../tests-api/staff.spec.js) |
| `contentService.save` | Connected | Owner/Admin | [`test_content_api.py`](../backend/tests/test_content_api.py); [`records.spec.js`](../tests-api/records.spec.js) |
| `clientService.getAll` | Connected | authenticated | [`test_directory_api.py`](../backend/tests/test_directory_api.py); [`records.spec.js`](../tests-api/records.spec.js) |
| `clientService.getById` | Connected | authenticated | [`test_directory_api.py`](../backend/tests/test_directory_api.py); [`test_client_notes.py`](../backend/tests/test_client_notes.py); [`records.spec.js`](../tests-api/records.spec.js) |
| `clientService.create` | Connected | operations | [`test_client_creation.py`](../backend/tests/test_client_creation.py); [`test_client_matching.py`](../backend/tests/test_client_matching.py); [`records.spec.js`](../tests-api/records.spec.js) |
| `clientService.renewPackage` | Connected | Owner/Admin | [`test_client_renewal_review.py`](../backend/tests/test_client_renewal_review.py); [`test_client_renewal_save.py`](../backend/tests/test_client_renewal_save.py); [`test_purchase_activation.py`](../backend/tests/test_purchase_activation.py); [`records.spec.js`](../tests-api/records.spec.js) |
| `clientService.deactivatePackage` | Connected | Owner/Admin | [backend](../backend/tests/test_package_actions.py); [media](../backend/tests/test_package_media.py); [browser](../tests-api/package-actions.spec.js); PR78 source accepted |
| `clientService.reactivatePackage` | Connected | Owner/Admin | [`test_package_reactivation_review.py`](../backend/tests/test_package_reactivation_review.py); [`test_package_reactivation_save.py`](../backend/tests/test_package_reactivation_save.py); [`records.spec.js`](../tests-api/records.spec.js) |
| `clientService.deletePackageSessions` | Connected | Owner/Admin | [backend](../backend/tests/test_package_actions.py); [media](../backend/tests/test_package_media.py); [browser](../tests-api/package-actions.spec.js); PR78 source accepted |
| `clientService.update` | Connected: contacts, optional fields, general health notes and remarks | Owner/Admin contact edits; current assigned Trainer may edit general notes; assessment forms remain Owner/Admin | [`test_client_details.py`](../backend/tests/test_client_details.py); [`test_client_notes.py`](../backend/tests/test_client_notes.py); [`records.spec.js`](../tests-api/records.spec.js) |
| `clientService.saveAssessment` | Connected | Owner/Admin only; inactive records read-only | [`test_assessment_workflows.py`](../backend/tests/test_assessment_workflows.py); [`records.spec.js`](../tests-api/records.spec.js) |
| `clientService.saveFixedWeeklySchedule` | Connected | Owner/Admin or current assigned active Trainer; Trainer approval control enforced server-side | [`test_client_weekly_schedule.py`](../backend/tests/test_client_weekly_schedule.py); [`records.spec.js`](../tests-api/records.spec.js) |
| `clientService.reassignTrainer` | Connected | Owner/Admin only; active client and replacement | [`test_client_assignment_review.py`](../backend/tests/test_client_assignment_review.py); [`test_client_assignment_save.py`](../backend/tests/test_client_assignment_save.py); [`records.spec.js`](../tests-api/records.spec.js) |
| `clientService.recordProgressReportAction` | Connected | Scoped client report access, including retained historical/inactive reads | [backend](../backend/tests/test_progress_reports_api.py); [browser](../tests-api/progress-reports.spec.js) |
| `clientService.progressReportHistory` | Connected | Owner/Admin only | [backend](../backend/tests/test_progress_reports_api.py); [browser](../tests-api/progress-reports.spec.js) |
| `clientService.deactivate` | Connected | Owner/Admin | [`test_client_deactivation_api.py`](../backend/tests/test_client_deactivation_api.py); [`records.spec.js`](../tests-api/records.spec.js) |
| `clientService.reactivate` | Connected; open-session retention | Owner/Admin | [`test_client_reactivation_review.py`](../backend/tests/test_client_reactivation_review.py); [`test_client_reactivation_save.py`](../backend/tests/test_client_reactivation_save.py); [`records.spec.js`](../tests-api/records.spec.js) |
| `trainerService.create` | Connected | Owner/Admin; Owner-only submitted rates, Admin server defaults with no financial projection | [`test_trainer_creation.py`](../backend/tests/test_trainer_creation.py); [`staff.spec.js`](../tests-api/staff.spec.js) |
| `trainerService.saveAvailability` | Connected | active Trainer editing self | [`test_trainer_availability.py`](../backend/tests/test_trainer_availability.py); [`records.spec.js`](../tests-api/records.spec.js) |
| `trainerService.getAll` | Connected | authenticated | [`test_directory_api.py`](../backend/tests/test_directory_api.py); [`records.spec.js`](../tests-api/records.spec.js) |
| `trainerService.getActive` | Connected | authenticated | [`test_directory_api.py`](../backend/tests/test_directory_api.py); [`records.spec.js`](../tests-api/records.spec.js) |
| `trainerService.getById` | Connected | authenticated | [`test_directory_api.py`](../backend/tests/test_directory_api.py); [`records.spec.js`](../tests-api/records.spec.js) |
| `trainerService.isSelectableForAvailability` | Local | authenticated | [directory unit tests](../src/services/apiDirectory.test.js); no HTTP operation |
| `trainerService.update` | Connected | Manager profile/name edits; own active Trainer non-name profile fields; Owner rates; verified email before switching | [profile](../backend/tests/test_trainer_details.py); [rates](../backend/tests/test_trainer_rates.py); [email](../backend/tests/test_email_corrections.py); [browser](../tests-api/email-corrections.spec.js); PR77 accepted |
| `trainerService.updateAutonomy` | Connected | Owner/Admin only | [`test_trainer_approvals.py`](../backend/tests/test_trainer_approvals.py); [`records.spec.js`](../tests-api/records.spec.js) |
| `trainerService.deactivate` | Connected | Owner/Admin only; all remaining active-client/purchase sessions require available replacements | [`test_trainer_deactivation.py`](../backend/tests/test_trainer_deactivation.py); [`records.spec.js`](../tests-api/records.spec.js) |
| `trainerService.reactivate` | Connected | Owner/Admin | [`test_trainer_reactivation.py`](../backend/tests/test_trainer_reactivation.py); [`records.spec.js`](../tests-api/records.spec.js) |
| `sessionService.previewPostponement` | Connected | session | [backend](../backend/tests/test_session_postponement_api.py); [browser](../tests-api/session-postponement.spec.js); see Progress |
| `sessionService.postpone` | Connected | session | [backend](../backend/tests/test_session_postponement_api.py); [browser](../tests-api/session-postponement.spec.js); see Progress |
| `sessionService.loadVideo` | Connected | Current scoped reads; Owner/Admin or assigned Trainer writes; final/inactive records read-only | [backend](../backend/tests/test_session_media_api.py); [browser](../tests-api/session-media.spec.js); PR79 accepted |
| `sessionService.saveVideo` | Connected | Current scoped reads; Owner/Admin or assigned Trainer writes; final/inactive records read-only | [backend](../backend/tests/test_session_media_api.py); [browser](../tests-api/session-media.spec.js); PR79 accepted |
| `sessionService.removeVideo` | Connected | Current scoped reads; Owner/Admin or assigned Trainer writes; final/inactive records read-only | [backend](../backend/tests/test_session_media_api.py); [browser](../tests-api/session-media.spec.js); PR79 accepted |
| `sessionService.updateDetails` | Connected | operationsSession | [backend](../backend/tests/test_session_booking_api.py); [browser](../tests-api/session-booking.spec.js); see Progress |
| `sessionService.requestTimeChange` | Connected | Current assigned active Trainer; server approval policy | [backend](../backend/tests/test_session_changes_api.py); [browser](../tests-api/session-changes.spec.js); see Progress |
| `sessionService.requestTrainerChange` | Connected | Current assigned active Trainer; active replacement and server approval policy | [backend](../backend/tests/test_session_changes_api.py); [browser](../tests-api/session-changes.spec.js); see Progress |
| `sessionService.saveExercisePlan` | Connected | Owner/Admin or current assigned active Trainer; active editable session | [backend](../backend/tests/test_session_plans_api.py); [browser](../tests-api/session-plans.spec.js); PR67 accepted |
| `sessionService.previousPlanFor` | Connected | Current assigned Trainer or operations; reviewed source/target scope | [backend](../backend/tests/test_previous_session_plan_api.py); [browser](../tests-api/previous-plan.spec.js); PR70 accepted |
| `sessionService.copyPreviousPlan` | Connected | Current assigned Trainer or operations; reviewed source/target scope | [backend](../backend/tests/test_previous_session_plan_api.py); [browser](../tests-api/previous-plan.spec.js); PR70 accepted |
| `sessionService.saveOutcome` | Connected | Owner/Admin or currently assigned active Trainer; terminal ad-hoc cover stays read-only | [backend](../backend/tests/test_session_outcomes_api.py); [browser](../tests-api/session-outcomes.spec.js); PR70 accepted |
| `sessionService.saveClientSummary` | Connected | Owner/Admin or current assigned active Trainer; terminal cover read-only | [backend](../backend/tests/test_session_summaries_api.py); [browser](../tests-api/session-summaries.spec.js); PR71 accepted |
| `sessionService.markWhatsAppOpened` | Connected | Current assigned Trainer or Owner/Admin; active client/purchase; training date reached | [backend](../backend/tests/test_session_handoffs_api.py); [browser](../tests-api/session-handoffs.spec.js); PR75 accepted; opening compatibility only, no delivery claim |
| `sessionService.acknowledge` | Connected | Current assigned Trainer or operations; terminal cover read-only | [backend](../backend/tests/test_session_acknowledgements_api.py); [browser](../tests-api/session-acknowledgements.spec.js); PR72 accepted |
| `packageService.save` | Connected | operations | [`test_package_api.py`](../backend/tests/test_package_api.py); [`persistence.spec.js`](../tests-api/persistence.spec.js) |
| `exerciseLibraryService.loadMedia` | Connected | authenticated | [backend](../backend/tests/test_exercise_library_api.py); [storage](../backend/tests/test_media_storage.py); [browser](../tests-api/exercise-library.spec.js); PR77 source accepted |
| `exerciseLibraryService.getAll` | Connected | authenticated | [backend](../backend/tests/test_exercise_library_api.py); [storage](../backend/tests/test_media_storage.py); [browser](../tests-api/exercise-library.spec.js); PR77 source accepted |
| `exerciseLibraryService.save` | Connected | operations | [backend](../backend/tests/test_exercise_library_api.py); [storage](../backend/tests/test_media_storage.py); [browser](../tests-api/exercise-library.spec.js); PR77 source accepted |
| `messageService.dismissRenewal` | Connected | visible renewal; Owner/Admin or current assigned Trainer | [`test_renewal_dismissal_api.py`](../backend/tests/test_renewal_dismissal_api.py); [`records.spec.js`](../tests-api/records.spec.js) |
| `messageService.undo` | Connected | Visible original change; Owner/Admin or original active Trainer with current scope | [backend](../backend/tests/test_session_undo_api.py); [resilience](../backend/tests/test_session_undo_resilience.py); [browser](../tests-api/session-undo.spec.js); PR80 source accepted |
| `messageService.markRead` | Connected | current message visibility; independent recipient state | [`test_message_api.py`](../backend/tests/test_message_api.py); [`records.spec.js`](../tests-api/records.spec.js) |
| `messageService.markUnread` | Connected | current message visibility; independent recipient state | [`test_message_api.py`](../backend/tests/test_message_api.py); [`records.spec.js`](../tests-api/records.spec.js) |
| `requestService.resolve` | Connected | Owner/Admin; atomic current-state approval or rejection | [`test_request_resolution.py`](../backend/tests/test_request_resolution.py); [`request-resolution.spec.js`](../tests-api/request-resolution.spec.js) |
| `requestService.cancel` | Connected | active requesting Trainer | [`test_request_cancellation.py`](../backend/tests/test_request_cancellation.py); [`records.spec.js`](../tests-api/records.spec.js) |
| `remunerationService.list` | Connected | Owner all Trainers; Trainer self only; Admin forbidden | [backend](../backend/tests/test_remuneration_api.py); [browser](../tests-api/remuneration.spec.js); PR75 accepted |
| `remunerationService.detail` | Connected | Owner all Trainers; Trainer self only; Admin forbidden | [backend](../backend/tests/test_remuneration_api.py); [browser](../tests-api/remuneration.spec.js); PR75 accepted |
| `remunerationService.approve` | Connected | Owner only; reviewed closed cycle, immutable approval and private recovery | [backend](../backend/tests/test_remuneration_api.py); [browser](../tests-api/remuneration.spec.js); PR75 accepted |

Operations means Owner/Admin. Assigned-client edits require current assignment; historical report access is a separate read permission. Assigned-trainer edits require self or operations access. Session commands require the current assigned Trainer or operations access; direct booking-detail edits require operations access. Finer domain validators remain mandatory.


## Detailed API contracts

### Transport, authority and recovery

| Concern | Contract owner and interpretation |
| --- | --- |
| Frontend composition | [BR-001](business-rules.md#br-001): asynchronous `load()` / `invoke()` boundary; explicit API/demo mode, no silent fallback. |
| Authentication | OpenAPI security schemes distinguish staff-session cookie, temporary challenge-flow cookie and session-bound `X-CSRF-Token`. Protected domain writes use current server authority; public health/auth routes and flow operations have their declared exceptions. See [auth routes](../backend/app/auth/routes.py) and [OpenAPI configuration](../backend/app/api/openapi.py). |
| Origin and secrets | POST operations declare the configured staff `Origin`; credentials remain server-side. Actual cookie/origin enforcement belongs to [auth security](../backend/app/auth/security.py) and settings. |
| Request bodies | Each route links its strict schema below. Required/optional/nullable fields, enums, size bounds and UUID/date formats must be read from the exact schema; optional is not equivalent to nullable. Domain validation can be stricter than schema validation. |
| Versions and idempotency | [BR-009–011](business-rules.md#br-009) govern reviewed intent, commit-time authority/version checks, actor-private receipt recovery and conflicts. Required key headers are identified per endpoint below; do not assume every read or authentication call accepts an idempotency key. |
| Errors | [ErrorEnvelope](../backend/app/api/schemas.py) and OpenAPI response codes define safe `error.code`, `error.message`, `error.requestId`. Responses declare server `X-Request-ID` and `Cache-Control: no-store`; missing/foreign records must not leak scope. Per-endpoint error codes remain in the schema and implementation. |
| Media | Upload-intent endpoints and metadata responses are API contracts; signed object transfers use private storage constraints and checksum verification. See [storage owner](../backend/app/media_storage.py) and [ADR-006](architecture/adr.md#adr-006). |
| Acceptance | Evidence owners in the matrix exercise actual isolated PostgreSQL/HTTP and browser persistence. Provider, physical-device and deployment acceptance remain separate. |

**Worked contract examples — synthetic data only.** These are illustrative fixtures, not captured traffic, available records or instructions to invoke a live endpoint. The package catalogue is a representative transactional workflow; session/media/authentication operations have their own schemas and recovery owners. Cookie values, CSRF tokens and credentials are omitted. All POST examples assume a valid current operations session, exact configured `Origin`, JSON content type, session-bound `X-CSRF-Token` and the actor's UUID `Idempotency-Key`. Responses carry the server-generated `X-Request-ID` and `Cache-Control: no-store`; `example-request-id` below is a fictional support ID, not an authentication value.

**Create and successful response.** `POST /api/packages`, with `Idempotency-Key: 11111111-1111-4111-8111-111111111111`, accepts `{"draft":{"name":"Example Strength Package","total":12,"status":"active"}}`. Illustrative HTTP200: `{"id":"22222222-2222-4222-8222-222222222222","version":1,"revision":1,"status":"active","name":"Example Strength Package","total_sessions":12,"validity_days":90}`. The server derives90 validity days from12 sessions and supplies identity/version/revision. Existing purchased packages are not rewritten. See [package command owner](../backend/app/api/packages.py) and [HTTP registration](../backend/app/api/routes.py).

**Reviewed update and stale rejection.** An update uses a new command key and the reviewed version: `{"id":"22222222-2222-4222-8222-222222222222","expectedVersion":1,"draft":{"name":"Example Strength Package","total":24,"status":"active"}}`. If another actor has already advanced the version, HTTP409 is `{"error":{"code":"state_conflict","message":"Record changed or is read-only. Refresh and review it.","requestId":"example-request-id"}}`. Do not resubmit the stale draft with an invented version. Refresh and let the user review the new state; only a definitive rejection permits a newly reviewed intent. No write from this rejected attempt is committed.

**Key conflict and permission rejection.** Reusing a successfully recorded key with a different body returns HTTP409: `{"error":{"code":"idempotency_conflict","message":"Review this request before retrying.","requestId":"example-request-id"}}`. This says the requested replacement was rejected; it does not erase the earlier successful command. A Trainer attempting the operations-only package save receives HTTP403: `{"error":{"code":"forbidden","message":"This action requires operational access.","requestId":"example-request-id"}}`. Neither hidden buttons nor a guessed package ID grants access. Missing/foreign-record handling in other domains may intentionally use404 instead of exposing existence.

**Input rejection and expired session.** A package total outside1–365 or an update missing its paired ID/version is rejected as HTTP422: `{"error":{"code":"validation_error","message":"Request validation failed.","requestId":"example-request-id"}}`. A no-longer-valid session can receive HTTP401: `{"error":{"code":"SESSION_EXPIRED","message":"Your session has ended. Sign in again.","requestId":"example-request-id"}}`. Retire private UI and follow sign-in recovery; do not adopt another account's outstanding command or infer that an earlier ambiguous write did not commit.

**Uncertain outcome and original receipt.** A timeout, `ECONNRESET` or lost HTTP response has **no trustworthy response body**; there is no invented `unknown` server status or JSON success envelope. Freeze the original body/key. An explicit Check reads `GET /api/packages/saves/11111111-1111-4111-8111-111111111111` using the original actor's current authorized session. HTTP200 returns the original `DirectoryPackage` result shown above, even if a subsequent edit changed the live record; it is a receipt, not a fresh directory snapshot. Refresh the directory separately. If the receipt read succeeds but the refresh fails, preserve committed status and offer refresh recovery instead of saving again.

**Receipt not found versus receipt unavailable.** The package reconciliation route serializes with its command's catalogue lock. A definitive authorized HTTP404 is `{"error":{"code":"not_found","message":"The requested resource was not found.","requestId":"example-request-id"}}`. Only this matching owner/command recovery path may then allow an explicit confirmed retry of the same original body/key after current-authority checks; an arbitrary404 or an unreadable/expired/forbidden receipt is not proof of no effect. Identical replay returns the original result without another version, notice or purchase change. A repeat network error or503 leaves the outcome unresolved; do not issue a new key, alter the frozen intent or run an automatic retry loop.

**State interpretation.** Reviewed draft → explicit submission → committed result or definitive rejection. Submission with no trustworthy result → unknown, original intent frozen → explicit receipt Check → committed receipt or the operation-specific safe retry decision. Committed receipt → fresh display read; a failed display read stays committed. Changed identity/authority retires private UI and may prevent further recovery without undoing the server commit. This explains the existing [BR-009–011](business-rules.md#persistence-conflicts-and-recovery) and [adapter recovery](../src/services/apiCommand.js); it adds no new state enum or API route. Specific provider/authentication ambiguity must follow its own owner, not the catalogue's receipt rules.


**Scheduling decision — approval, rejection and recovery.** An Owner/Admin reviewing pending request `00000003-1111-4111-8111-111111111111` at version 1 submits `POST /api/requests/{request_id}/resolve` with its own new command UUID and `{"expectedVersion":1,"decision":"approved"}`. Illustrative HTTP200: `{"id":"00000003-1111-4111-8111-111111111111","version":2,"status":"approved","at":"2026-10-28T02:00:00Z","by":{"id":"00000004-1111-4111-8111-111111111111","name":"Example Owner"}}`. Approval rechecks current proposal, Trainer availability and domain constraints under the decision lock; it commits the supported change and decision notice atomically. Choosing `{"expectedVersion":1,"decision":"rejected"}` for a still-pending version-1 proposal instead returns the same response shape with `status: "rejected"`, without applying the requested schedule change. These are alternative scenarios, not two sequential decisions on one proposal. A competing decision or changed scheduling evidence returns HTTP409 `{"error":{"code":"state_conflict","message":"Record changed or is read-only. Refresh and review it.","requestId":"example-request-id"}}`. Do not fabricate version 2 to force a second decision. A Trainer cannot approve/reject through this operations-only route; the operations permission rejection is HTTP403 as shown above.

If the decision response is lost, `GET /api/request-resolutions/{request_key}` returns the original actor's `ResolutionState` without applying the proposal again. Another actor's missing receipt does not establish that the decision never happened. Changed key intent returns HTTP409 `{"error":{"code":"idempotency_conflict","message":"Check the original request decision.","requestId":"example-request-id"}}`. Preserve the original decision and key while recovery is unavailable. See [decision implementation](../backend/app/api/request_resolution.py) and [real-API browser evidence](../tests-api/request-resolution.spec.js).

**Acknowledgement and exactly-once credits.** First read `GET /api/sessions/{session_id}/acknowledgement-review`; use its returned `expected` unchanged. For an eligible past/current session, a no-show example is `POST /api/sessions/{session_id}/acknowledgement` with `{"expected":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","method":"late_no_show","note":"Example missed session"}`. The repeated `a` value is a schema-valid placeholder, not a valid live review fingerprint. Illustrative HTTP200: `{"sessionId":"00000005-1111-4111-8111-111111111111","version":4,"acknowledgementId":"00000006-1111-4111-8111-111111111111","method":"late_no_show","sequence":1,"used":1,"savedAt":"2026-10-28T02:00:00Z"}`. Here `used: 1` assumes no prior debit on that purchase; the server calculates the actual balance. The acknowledgement, one debit, eligible renewal notice and receipt commit together. No external message delivery is implied.

Future/Open/cancelled sessions, a changed review or exhausted eligible credits reject through the domain conflict path; invalid method or missing/invalid required signature evidence returns HTTP422 `{"error":{"code":"validation_error","message":"Request validation failed.","requestId":"example-request-id"}}`. A signature must contain actual bounded ink and a signer name; a fake signature payload is intentionally not supplied. An eligible later no-show-to-signature correction has a fresh reviewed intent and a new immutable acknowledgement, while retaining the original and exactly one debit. There is no generic acknowledgement Undo. For a lost response, `GET /api/session-acknowledgements/{request_key}` returns the original `AcknowledgementSaved`; neither receipt read nor identical replay adds a debit. Follow [acknowledgement implementation](../backend/app/api/session_acknowledgements.py) and [browser evidence](../tests-api/session-acknowledgements.spec.js).

**Private recording — reserve, upload and commit are separate.** After a current video review, `POST /api/session-media/intents` with `Idempotency-Key: 00000007-1111-4111-8111-111111111111` accepts `{"sessionId":"00000005-1111-4111-8111-111111111111","exerciseId":"00000008-1111-4111-8111-111111111111","expected":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","remove":false,"upload":{"name":"example-recording.mp4","type":"video/mp4","size":1024,"sha256":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"},"duration":10,"source":"attached","caption":"Example exercise","processingStatus":"deferred","audioIncluded":false}`. The review digest and checksum are illustrative placeholders; a real upload must match actual bytes and the current server review. HTTP200 reservation example: `{"key":"00000007-1111-4111-8111-111111111111","state":"pending","uploadUntil":"2026-10-28T02:05:00Z","result":null}`. Pending means an intent exists, not a published recording.

`POST /api/session-media/intents/{key}/upload` takes `{}` and the same key in the URL and `Idempotency-Key` header. It returns an `UploadLease`; use its exact URL/fields and signed transfer constraints, without persisting credentials or changing the frozen metadata. No reusable signed URL is included here. After transfer, `POST /api/session-media/intents/{key}/commit` takes the same empty object/key. The server verifies bytes outside the transaction, then rechecks current authority and original evidence before publishing. Illustrative HTTP200: `{"sessionId":"00000005-1111-4111-8111-111111111111","exerciseId":"00000008-1111-4111-8111-111111111111","version":5,"savedAt":"2026-10-28T02:01:00Z","media":{"id":"00000009-1111-4111-8111-111111111111","name":"example-recording.mp4","type":"video/mp4","size":1024,"attachedAt":"2026-10-28T02:01:00Z","expiresAt":"2026-11-04T02:01:00Z"}}`. Expiry is seven days from commit, not from the browser clock or later playback. Client duration/audio/processing claims do not prove transcoding. Successful browser conversion submits `processingStatus: "complete"` and `audioIncluded: false` for unchecked audio or `true` for the selected original-audio option; an unconverted original submits `processingStatus: "deferred"` and `audioIncluded: null`. This describes the client preparation result, not an assertion that a silent source contains speech. `RecordingMedia` does not project these processing fields; use the protected saved bytes to verify actual playback. The seven-day read cutoff remains separate from the selected monthly physical cleanup policy in [Business rules](business-rules.md#br-049).

**Recording uncertainty and expiry.** If reserve/commit loses its response, `GET /api/session-media/intents/{key}` can return the pending shape above, or `{"key":"00000007-1111-4111-8111-111111111111","state":"completed","uploadUntil":"2026-10-28T02:05:00Z","result":{"sessionId":"00000005-1111-4111-8111-111111111111","exerciseId":"00000008-1111-4111-8111-111111111111","version":5,"savedAt":"2026-10-28T02:01:00Z","media":{"id":"00000009-1111-4111-8111-111111111111","name":"example-recording.mp4","type":"video/mp4","size":1024,"attachedAt":"2026-10-28T02:01:00Z","expiresAt":"2026-11-04T02:01:00Z"}}}`. A completed result ends original-command recovery; do not create a replacement upload/key to discover whether the first save committed. A pending result alone does not prove that object bytes are absent. An expired pending command rejects preparation/commit with HTTP409 `{"error":{"code":"SAVE_EXPIRED","message":"The original recording save expired.","requestId":"example-request-id"}}`. An intent may still project `pending` after its deadline until cleanup marks it expired; the deadline is nevertheless enforced on preparation. A mismatched path/header key or changed review returns the domain conflict response. Reusing the reserved key with different metadata returns HTTP409 `{"error":{"code":"idempotency_conflict","message":"Check the original recording save.","requestId":"example-request-id"}}`. Expiry or changed authority does not authorize attaching stale bytes; recover/review through this domain's own lifecycle. See [recording routes](../backend/app/api/session_media_routes.py), [intent owner](../backend/app/api/session_media.py) and [browser evidence](../tests-api/session-media.spec.js).

### HTTP endpoint index

Snapshot derived from `backend/contracts/openapi.json` in accepted application source `1246fb815b1240a92fd953b85abc05f18f46bc73`: **159 method/path operations across147 paths**, with246 schema definitions. Schema SHA-256: `24b8a8bacb029b014448630de0c0d32f255fb66cfb5cb21b2a5f9719a7e058a0`. Refresh this index when the schema changes; do not edit it as an independent API specification. Schema links target the checked-in JSON lines; [route registration](../backend/app/api/routes.py) and [additional routers](../backend/app/main.py) own implementation.

Body and success columns name exact schemas. Parameters identify location/name and `*` means required. Error responses, field bounds and security alternatives remain in the linked OpenAPI operation/schema. `StaffSession + SessionCSRF` means both are required; domain roles and record scope are enforced beyond the transport declaration.

| Method / path / operation ID | Parameters | Body | Success response | Transport security |
| --- | --- | --- | --- | --- |
| [`GET /api/assessment-forms`](../backend/contracts/openapi.json#L10822) · `listAssessmentForms` | query: `limit`, query: `offset` | — | 200: [Page_FormDefinition_](../backend/contracts/openapi.json#L5446) | StaffSession |
| [`GET /api/assessment-saves/{request_key}`](../backend/contracts/openapi.json#L11262) · `reconcileAssessmentSave` | path: `request_key`* | — | 200: [AssessmentRevision](../backend/contracts/openapi.json#L214) | StaffSession |
| [`GET /api/assessments/{assessment_id}`](../backend/contracts/openapi.json#L11688) · `getAssessment` | path: `assessment_id`* | — | 200: [AssessmentRevision](../backend/contracts/openapi.json#L214) | StaffSession |
| [`GET /api/assessments/{assessment_id}/revisions`](../backend/contracts/openapi.json#L12114) · `listAssessmentHistory` | path: `assessment_id`*, query: `limit`, query: `offset` | — | 200: [Page_AssessmentRevision_](../backend/contracts/openapi.json#L5382) | StaffSession |
| [`POST /api/assessments/{assessment_id}/revisions`](../backend/contracts/openapi.json#L12114) · `saveAssessmentRevision` | path: `assessment_id`*, header: `Idempotency-Key`*, header: `Origin`* | [SaveAssessment](../backend/contracts/openapi.json#L8246) | 200: [AssessmentRevision](../backend/contracts/openapi.json#L214) | SessionCSRF + StaffSession |
| [`GET /api/client-creations/{request_key}`](../backend/contracts/openapi.json#L13021) · `reconcileClientCreation` | path: `request_key`* | — | 200: [CreatedClient](../backend/contracts/openapi.json#L2217) | StaffSession |
| [`GET /api/client-deactivations/{request_key}`](../backend/contracts/openapi.json#L13446) · `reconcileClientDeactivation` | path: `request_key`* | — | 200: [DeactivationState](../backend/contracts/openapi.json#L2314) | StaffSession |
| [`GET /api/client-detail-saves/{request_key}`](../backend/contracts/openapi.json#L13871) · `reconcileClientPersonalDetails` | path: `request_key`* | — | 200: [ClientDetailState](../backend/contracts/openapi.json#L1464) | StaffSession |
| [`GET /api/client-note-saves/{request_key}`](../backend/contracts/openapi.json#L14296) · `reconcileClientNotes` | path: `request_key`* | — | 200: [NoteState](../backend/contracts/openapi.json#L4612) | StaffSession |
| [`POST /api/client-onboarding/matches`](../backend/contracts/openapi.json#L14721) · `previewClientTrainerMatches` | header: `Idempotency-Key`*, header: `Origin`* | [MatchRequest](../backend/contracts/openapi.json#L3750) | 200: [MatchResult](../backend/contracts/openapi.json#L3804) | SessionCSRF + StaffSession |
| [`GET /api/client-reactivations/{request_key}`](../backend/contracts/openapi.json#L15169) · `reconcileClientReactivation` | path: `request_key`* | — | 200: [ClientReactivationState](../backend/contracts/openapi.json#L1647) | StaffSession |
| [`GET /api/client-renewals/{request_key}`](../backend/contracts/openapi.json#L15594) · `reconcileClientRenewal` | path: `request_key`* | — | 200: [ClientRenewalState](../backend/contracts/openapi.json#L1674) | StaffSession |
| [`GET /api/client-trainer-assignments/{request_key}`](../backend/contracts/openapi.json#L16019) · `reconcileClientTrainerAssignment` | path: `request_key`* | — | 200: [AssignmentState](../backend/contracts/openapi.json#L670) | StaffSession |
| [`GET /api/client-weekly-schedules/{request_key}`](../backend/contracts/openapi.json#L16444) · `reconcileClientWeeklySchedule` | path: `request_key`* | — | 200: [ClientWeeklyState](../backend/contracts/openapi.json#L1945) | StaffSession |
| [`GET /api/clients`](../backend/contracts/openapi.json#L16869) · `listClients` | query: `limit`, query: `offset` | — | 200: [Page_ClientSummary_](../backend/contracts/openapi.json#L5414) | StaffSession |
| [`POST /api/clients`](../backend/contracts/openapi.json#L16869) · `createClient` | header: `Idempotency-Key`*, header: `Origin`* | [CreateClient](../backend/contracts/openapi.json#L2116) | 200: [CreatedClient](../backend/contracts/openapi.json#L2217) | SessionCSRF + StaffSession |
| [`GET /api/clients/{client_id}`](../backend/contracts/openapi.json#L17754) · `getClient` | path: `client_id`* | — | 200: [ClientDetail](../backend/contracts/openapi.json#L1407) | StaffSession |
| [`GET /api/clients/{client_id}/assessment-records`](../backend/contracts/openapi.json#L18179) · `getClientAssessmentRecords` | path: `client_id`* | — | 200: [ClientAssessmentRecords](../backend/contracts/openapi.json#L1373) | StaffSession |
| [`GET /api/clients/{client_id}/deactivation`](../backend/contracts/openapi.json#L18605) · `reviewClientDeactivation` | path: `client_id`* | — | 200: [DeactivationReview](../backend/contracts/openapi.json#L2273) | StaffSession |
| [`POST /api/clients/{client_id}/deactivation`](../backend/contracts/openapi.json#L18605) · `deactivateClient` | path: `client_id`*, header: `Idempotency-Key`*, header: `Origin`* | [DeactivateClient](../backend/contracts/openapi.json#L2243) | 200: [DeactivationState](../backend/contracts/openapi.json#L2314) | SessionCSRF + StaffSession |
| [`GET /api/clients/{client_id}/notes`](../backend/contracts/openapi.json#L19486) · `getClientNotes` | path: `client_id`* | — | 200: [NoteView](../backend/contracts/openapi.json#L4632) | StaffSession |
| [`POST /api/clients/{client_id}/notes`](../backend/contracts/openapi.json#L19486) · `saveClientNotes` | path: `client_id`*, header: `Idempotency-Key`*, header: `Origin`* | [SaveNotes](../backend/contracts/openapi.json#L8578) | 200: [NoteState](../backend/contracts/openapi.json#L4612) | SessionCSRF + StaffSession |
| [`POST /api/clients/{client_id}/packages`](../backend/contracts/openapi.json#L20367) · `renewClientPackage` | path: `client_id`*, header: `Idempotency-Key`*, header: `Origin`* | [RenewPackage](../backend/contracts/openapi.json#L7462) | 200: [ClientRenewalState](../backend/contracts/openapi.json#L1674) | SessionCSRF + StaffSession |
| [`POST /api/clients/{client_id}/packages/{purchase_id}/reactivation`](../backend/contracts/openapi.json#L20825) · `reactivatePackage` | path: `client_id`*, path: `purchase_id`*, header: `Idempotency-Key`*, header: `Origin`* | [ReactivationDates](../backend/contracts/openapi.json#L7062) | 200: [PackageReactivationState](../backend/contracts/openapi.json#L5270) | SessionCSRF + StaffSession |
| [`GET /api/clients/{client_id}/packages/{purchase_id}/reactivation-review`](../backend/contracts/openapi.json#L21293) · `reviewPackageReactivation` | path: `client_id`*, path: `purchase_id`* | — | 200: [PackageReactivationReview](../backend/contracts/openapi.json#L5205) | StaffSession |
| [`POST /api/clients/{client_id}/packages/{purchase_id}/reactivation-review`](../backend/contracts/openapi.json#L21293) · `previewPackageReactivationDates` | path: `client_id`*, path: `purchase_id`*, header: `Idempotency-Key`*, header: `Origin`* | [ReactivationDates](../backend/contracts/openapi.json#L7062) | 200: [PackageReactivationReview](../backend/contracts/openapi.json#L5205) | SessionCSRF + StaffSession |
| [`POST /api/clients/{client_id}/personal-details`](../backend/contracts/openapi.json#L22194) · `saveClientPersonalDetails` | path: `client_id`*, header: `Idempotency-Key`*, header: `Origin`* | [SaveClientDetails](../backend/contracts/openapi.json#L8372) | 200: [ClientDetailState](../backend/contracts/openapi.json#L1464) | SessionCSRF + StaffSession |
| [`GET /api/clients/{client_id}/progress`](../backend/contracts/openapi.json#L22652) · `read_client_progress_api_clients__client_id__progress_get` | path: `client_id`* | — | 200: [ClientProgress](../backend/contracts/openapi.json#L1565) | StaffSession |
| [`GET /api/clients/{client_id}/purchases/{purchase_id}/action-review`](../backend/contracts/openapi.json#L23077) · `reviewPackageAction` | path: `client_id`*, path: `purchase_id`*, query: `operation`* | — | 200: [PackageActionReview](../backend/contracts/openapi.json#L4999) | StaffSession |
| [`POST /api/clients/{client_id}/purchases/{purchase_id}/actions`](../backend/contracts/openapi.json#L23525) · `savePackageAction` | path: `client_id`*, path: `purchase_id`*, header: `Idempotency-Key`*, header: `Origin`* | [SavePackageAction](../backend/contracts/openapi.json#L8664) | 200: [PackageActionState](../backend/contracts/openapi.json#L5066) | SessionCSRF + StaffSession |
| [`POST /api/clients/{client_id}/reactivation`](../backend/contracts/openapi.json#L23993) · `reactivateClient` | path: `client_id`*, header: `Idempotency-Key`*, header: `Origin`* | [ReactivationDates](../backend/contracts/openapi.json#L7062) | 200: [ClientReactivationState](../backend/contracts/openapi.json#L1647) | SessionCSRF + StaffSession |
| [`GET /api/clients/{client_id}/reactivation-review`](../backend/contracts/openapi.json#L24451) · `reviewClientReactivation` | path: `client_id`* | — | 200: [ClientReactivationReview](../backend/contracts/openapi.json#L1588) | StaffSession |
| [`POST /api/clients/{client_id}/reactivation-review`](../backend/contracts/openapi.json#L24451) · `previewClientReactivationDates` | path: `client_id`*, header: `Idempotency-Key`*, header: `Origin`* | [ReactivationDates](../backend/contracts/openapi.json#L7062) | 200: [ClientReactivationReview](../backend/contracts/openapi.json#L1588) | SessionCSRF + StaffSession |
| [`POST /api/clients/{client_id}/renewal-matches`](../backend/contracts/openapi.json#L25332) · `previewClientRenewalMatches` | path: `client_id`*, header: `Idempotency-Key`*, header: `Origin`* | [RenewalMatchRequest](../backend/contracts/openapi.json#L7544) | 200: [MatchResult](../backend/contracts/openapi.json#L3804) | SessionCSRF + StaffSession |
| [`GET /api/clients/{client_id}/renewal-review`](../backend/contracts/openapi.json#L25790) · `reviewClientPackageRenewal` | path: `client_id`* | — | 200: [RenewalReview](../backend/contracts/openapi.json#L7685) | StaffSession |
| [`POST /api/clients/{client_id}/report-actions`](../backend/contracts/openapi.json#L26215) · `record_progress_report_api_clients__client_id__report_actions_post` | path: `client_id`*, header: `Idempotency-Key`*, header: `Origin`* | [ReportAction](../backend/contracts/openapi.json#L7829) | 200: [ReportEvent](../backend/contracts/openapi.json#L7874) | SessionCSRF + StaffSession |
| [`GET /api/clients/{client_id}/report-history`](../backend/contracts/openapi.json#L26673) · `read_progress_report_history_api_clients__client_id__report_history_get` | path: `client_id`*, query: `purchase_id` | — | 200: array of [ReportEvent](../backend/contracts/openapi.json#L7874) | StaffSession |
| [`POST /api/clients/{client_id}/trainer-assignment`](../backend/contracts/openapi.json#L27119) · `saveClientTrainerAssignment` | path: `client_id`*, header: `Idempotency-Key`*, header: `Origin`* | [SaveAssignment](../backend/contracts/openapi.json#L8327) | 200: [AssignmentState](../backend/contracts/openapi.json#L670) | SessionCSRF + StaffSession |
| [`GET /api/clients/{client_id}/trainer-assignment-review`](../backend/contracts/openapi.json#L27577) · `reviewClientTrainerAssignment` | path: `client_id`* | — | 200: [AssignmentReview](../backend/contracts/openapi.json#L525) | StaffSession |
| [`POST /api/clients/{client_id}/weekly-schedule`](../backend/contracts/openapi.json#L28002) · `saveClientWeeklySchedule` | path: `client_id`*, header: `Idempotency-Key`*, header: `Origin`* | [SaveClientWeeklySchedule](../backend/contracts/openapi.json#L8413) | 200: [ClientWeeklyState](../backend/contracts/openapi.json#L1945) | SessionCSRF + StaffSession |
| [`GET /api/clients/{client_id}/weekly-schedule-review`](../backend/contracts/openapi.json#L28460) · `reviewClientWeeklySchedule` | path: `client_id`* | — | 200: [ClientWeeklyReview](../backend/contracts/openapi.json#L1778) | StaffSession |
| [`POST /api/clients/{client_id}/weekly-schedule-review`](../backend/contracts/openapi.json#L28460) · `previewClientWeeklySchedule` | path: `client_id`*, header: `Idempotency-Key`*, header: `Origin`* | [SaveClientWeeklySchedule](../backend/contracts/openapi.json#L8413) | 200: [ClientWeeklyPreview](../backend/contracts/openapi.json#L1750) | SessionCSRF + StaffSession |
| [`GET /api/clock`](../backend/contracts/openapi.json#L29341) · `staffClock` | — | — | 200: [ServerClock](../backend/contracts/openapi.json#L8907) | StaffSession |
| [`GET /api/content`](../backend/contracts/openapi.json#L29754) · `staffContent` | — | — | 200: array of [ContentState](../backend/contracts/openapi.json#L2025) | StaffSession |
| [`POST /api/content`](../backend/contracts/openapi.json#L29754) · `saveContent` | header: `Idempotency-Key`*, header: `Origin`* | [SaveContent](../backend/contracts/openapi.json#L8438) | 200: [ContentState](../backend/contracts/openapi.json#L2025) | SessionCSRF + StaffSession |
| [`GET /api/content-saves/{request_key}`](../backend/contracts/openapi.json#L30617) · `reconcileContent` | path: `request_key`* | — | 200: [ContentState](../backend/contracts/openapi.json#L2025) | StaffSession |
| [`GET /api/directory`](../backend/contracts/openapi.json#L31042) · `staffDirectory` | — | — | 200: [DirectorySnapshot](../backend/contracts/openapi.json#L2709) | StaffSession |
| [`GET /api/exercise-library`](../backend/contracts/openapi.json#L31455) · `catalogue_api_exercise_library_get` | — | — | 200: [Catalogue](../backend/contracts/openapi.json#L1233) | StaffSession |
| [`GET /api/exercise-library/media/{identity}`](../backend/contracts/openapi.json#L31868) · `read_api_exercise_library_media__identity__get` | path: `identity`* | — | 200: [ReadLease](../backend/contracts/openapi.json#L7164) | StaffSession |
| [`GET /api/exercise-library/media/{identity}/check`](../backend/contracts/openapi.json#L32293) · `recheck_api_exercise_library_media__identity__check_get` | path: `identity`*, query: `version`* | — | 200: [MediaReadCheck](../backend/contracts/openapi.json#L3900) | StaffSession |
| [`POST /api/exercise-library/save-intents`](../backend/contracts/openapi.json#L32727) · `reserve_api_exercise_library_save_intents_post` | header: `Idempotency-Key`*, header: `Origin`* | [SaveLibrary](../backend/contracts/openapi.json#L8475) | 200: [LibraryIntentView](../backend/contracts/openapi.json#L3627) | SessionCSRF + StaffSession |
| [`GET /api/exercise-library/save-intents/{key}`](../backend/contracts/openapi.json#L33173) · `recover_api_exercise_library_save_intents__key__get` | path: `key`* | — | 200: [LibraryIntentView](../backend/contracts/openapi.json#L3627) | StaffSession |
| [`POST /api/exercise-library/save-intents/{key}/commit`](../backend/contracts/openapi.json#L33598) · `commit_api_exercise_library_save_intents__key__commit_post` | path: `key`*, header: `Idempotency-Key`*, header: `Origin`* | [OriginalLibraryAction](../backend/contracts/openapi.json#L4799) | 200: [LibraryExercise](../backend/contracts/openapi.json#L3560) | SessionCSRF + StaffSession |
| [`POST /api/exercise-library/save-intents/{key}/upload`](../backend/contracts/openapi.json#L34054) · `upload_api_exercise_library_save_intents__key__upload_post` | path: `key`*, header: `Idempotency-Key`*, header: `Origin`* | [OriginalLibraryAction](../backend/contracts/openapi.json#L4799) | 200: [UploadLease](../backend/contracts/openapi.json#L10752) | SessionCSRF + StaffSession |
| [`GET /api/message-read-saves/{request_key}`](../backend/contracts/openapi.json#L34510) · `reconcileMessageReadState` | path: `request_key`* | — | 200: [MessageReadState](../backend/contracts/openapi.json#L3915) | StaffSession |
| [`GET /api/messages`](../backend/contracts/openapi.json#L34935) · `personalMessages` | — | — | 200: array of [PersonalMessage](../backend/contracts/openapi.json#L6156) | StaffSession |
| [`POST /api/messages/{message_id}/dismiss-renewal`](../backend/contracts/openapi.json#L35352) · `dismissRenewal` | path: `message_id`*, header: `Idempotency-Key`*, header: `Origin`* | [DismissRenewal](../backend/contracts/openapi.json#L3147) | 200: [RenewalState](../backend/contracts/openapi.json#L7794) | SessionCSRF + StaffSession |
| [`POST /api/messages/{message_id}/read-state`](../backend/contracts/openapi.json#L35810) · `saveMessageReadState` | path: `message_id`*, header: `Idempotency-Key`*, header: `Origin`* | [SaveMessageRead](../backend/contracts/openapi.json#L8558) | 200: [MessageReadState](../backend/contracts/openapi.json#L3915) | SessionCSRF + StaffSession |
| [`POST /api/package-actions/{identity}/undo`](../backend/contracts/openapi.json#L36268) · `undo_api_package_actions__identity__undo_post` | path: `identity`*, header: `Idempotency-Key`*, header: `Origin`* | [UndoPackageDeletion](../backend/contracts/openapi.json#L10625) | 200: [PackageUndoState](../backend/contracts/openapi.json#L5355) | SessionCSRF + StaffSession |
| [`GET /api/package-actions/{identity}/undo-review`](../backend/contracts/openapi.json#L36726) · `undo_review_api_package_actions__identity__undo_review_get` | path: `identity`* | — | 200: [PackageUndoReview](../backend/contracts/openapi.json#L5303) | StaffSession |
| [`GET /api/package-actions/{key}`](../backend/contracts/openapi.json#L37151) · `reconcilePackageAction` | path: `key`* | — | 200: [PackageActionState](../backend/contracts/openapi.json#L5066) | StaffSession |
| [`GET /api/package-reactivations/{request_key}`](../backend/contracts/openapi.json#L37576) · `reconcilePackageReactivation` | path: `request_key`* | — | 200: [PackageReactivationState](../backend/contracts/openapi.json#L5270) | StaffSession |
| [`GET /api/package-undos/{key}`](../backend/contracts/openapi.json#L38001) · `undo_reconcile_api_package_undos__key__get` | path: `key`* | — | 200: [PackageUndoState](../backend/contracts/openapi.json#L5355) | StaffSession |
| [`POST /api/packages`](../backend/contracts/openapi.json#L38426) · `savePackage` | header: `Idempotency-Key`*, header: `Origin`* | [SavePackage](../backend/contracts/openapi.json#L8627) | 200: [DirectoryPackage](../backend/contracts/openapi.json#L2428) | SessionCSRF + StaffSession |
| [`GET /api/packages/saves/{request_key}`](../backend/contracts/openapi.json#L38874) · `reconcilePackageSave` | path: `request_key`* | — | 200: [DirectoryPackage](../backend/contracts/openapi.json#L2428) | StaffSession |
| [`GET /api/people/{person_id}/assessments`](../backend/contracts/openapi.json#L39299) · `listPersonAssessments` | path: `person_id`*, query: `limit`, query: `offset`, query: `formId` | — | 200: [Page_AssessmentRevision_](../backend/contracts/openapi.json#L5382) | StaffSession |
| [`POST /api/people/{person_id}/assessments`](../backend/contracts/openapi.json#L39299) · `createPersonAssessment` | path: `person_id`*, header: `Idempotency-Key`*, header: `Origin`* | [NewAssessment](../backend/contracts/openapi.json#L4327) | 200: [AssessmentRevision](../backend/contracts/openapi.json#L214) | SessionCSRF + StaffSession |
| [`GET /api/remuneration`](../backend/contracts/openapi.json#L40224) · `list_remuneration_api_remuneration_get` | — | — | 200: array of [PayView](../backend/contracts/openapi.json#L5910) | StaffSession |
| [`GET /api/remuneration-approvals/{request_key}`](../backend/contracts/openapi.json#L40641) · `remuneration_approval_receipt_api_remuneration_approvals__request_key__get` | path: `request_key`* | — | 200: [PaySaved](../backend/contracts/openapi.json#L5873) | StaffSession |
| [`GET /api/remuneration/{cycle_key}/{trainer_id}`](../backend/contracts/openapi.json#L41066) · `remuneration_detail_api_remuneration__cycle_key___trainer_id__get` | path: `cycle_key`*, path: `trainer_id`* | — | 200: [PayRecord](../backend/contracts/openapi.json#L5655) | StaffSession |
| [`POST /api/remuneration/{cycle_key}/{trainer_id}/approval`](../backend/contracts/openapi.json#L41500) · `approve_remuneration_api_remuneration__cycle_key___trainer_id__approval_post` | path: `cycle_key`*, path: `trainer_id`*, header: `Idempotency-Key`*, header: `Origin`* | [ApprovePay](../backend/contracts/openapi.json#L199) | 200: [PaySaved](../backend/contracts/openapi.json#L5873) | SessionCSRF + StaffSession |
| [`GET /api/renewal-dismissal-saves/{request_key}`](../backend/contracts/openapi.json#L41967) · `reconcileRenewalDismissal` | path: `request_key`* | — | 200: [RenewalState](../backend/contracts/openapi.json#L7794) | StaffSession |
| [`GET /api/report-actions/{request_key}`](../backend/contracts/openapi.json#L42392) · `recover_progress_report_api_report_actions__request_key__get` | path: `request_key`* | — | 200: [ReportEvent](../backend/contracts/openapi.json#L7874) | StaffSession |
| [`GET /api/request-cancellations/{request_key}`](../backend/contracts/openapi.json#L42817) · `reconcileRequestCancellation` | path: `request_key`* | — | 200: [CancellationState](../backend/contracts/openapi.json#L1196) | StaffSession |
| [`GET /api/request-resolutions/{request_key}`](../backend/contracts/openapi.json#L43242) · `reconcileRequestResolution` | path: `request_key`* | — | 200: [ResolutionState](../backend/contracts/openapi.json#L7996) | StaffSession |
| [`POST /api/requests/{request_id}/cancel`](../backend/contracts/openapi.json#L43667) · `cancelOwnedRequest` | path: `request_id`*, header: `Idempotency-Key`*, header: `Origin`* | [CancelRequest](../backend/contracts/openapi.json#L1181) | 200: [CancellationState](../backend/contracts/openapi.json#L1196) | SessionCSRF + StaffSession |
| [`POST /api/requests/{request_id}/resolve`](../backend/contracts/openapi.json#L44125) · `resolveStaffRequest` | path: `request_id`*, header: `Idempotency-Key`*, header: `Origin`* | [ResolveRequest](../backend/contracts/openapi.json#L8036) | 200: [ResolutionState](../backend/contracts/openapi.json#L7996) | SessionCSRF + StaffSession |
| [`GET /api/session-acknowledgements/{request_key}`](../backend/contracts/openapi.json#L44583) · `reconcile_session_acknowledgement_api_session_acknowledgements__request_key__get` | path: `request_key`* | — | 200: [AcknowledgementSaved](../backend/contracts/openapi.json#L52) | StaffSession |
| [`GET /api/session-booking-saves/{request_key}`](../backend/contracts/openapi.json#L45008) · `reconcileSessionBooking` | path: `request_key`* | — | 200: [SessionBookingState](../backend/contracts/openapi.json#L9087) | StaffSession |
| [`GET /api/session-calendar`](../backend/contracts/openapi.json#L45433) · `readSessionCalendar` | — | — | 200: [SessionCalendar](../backend/contracts/openapi.json#L9149) | StaffSession |
| [`POST /api/session-changes/{identity}/undo`](../backend/contracts/openapi.json#L45846) · `undo_api_session_changes__identity__undo_post` | path: `identity`*, header: `Idempotency-Key`*, header: `Origin`* | [UndoChange](../backend/contracts/openapi.json#L10610) | 200: [UndoSaved](../backend/contracts/openapi.json#L10677) | SessionCSRF + StaffSession |
| [`GET /api/session-changes/{identity}/undo-review`](../backend/contracts/openapi.json#L46304) · `review_api_session_changes__identity__undo_review_get` | path: `identity`* | — | 200: [UndoReview](../backend/contracts/openapi.json#L10640) | StaffSession |
| [`GET /api/session-changes/{request_key}`](../backend/contracts/openapi.json#L46729) · `reconcileTrainerSessionChange` | path: `request_key`* | — | 200: [SessionChangeState](../backend/contracts/openapi.json#L9273) | StaffSession |
| [`GET /api/session-handoffs/{request_key}`](../backend/contracts/openapi.json#L47154) · `recover_session_handoff_api_session_handoffs__request_key__get` | path: `request_key`* | — | 200: [HandoffSaved](../backend/contracts/openapi.json#L3491) | StaffSession |
| [`POST /api/session-media/intents`](../backend/contracts/openapi.json#L47579) · `reserve_api_session_media_intents_post` | header: `Idempotency-Key`*, header: `Origin`* | [SaveRecording](../backend/contracts/openapi.json#L8737) | 200: [RecordingIntent](../backend/contracts/openapi.json#L7213) | SessionCSRF + StaffSession |
| [`GET /api/session-media/intents/{key}`](../backend/contracts/openapi.json#L48027) · `recover_api_session_media_intents__key__get` | path: `key`* | — | 200: [RecordingIntent](../backend/contracts/openapi.json#L7213) | StaffSession |
| [`POST /api/session-media/intents/{key}/commit`](../backend/contracts/openapi.json#L48452) · `commit_api_session_media_intents__key__commit_post` | path: `key`*, header: `Idempotency-Key`*, header: `Origin`* | [OriginalLibraryAction](../backend/contracts/openapi.json#L4799) | 200: [RecordingSaved](../backend/contracts/openapi.json#L7339) | SessionCSRF + StaffSession |
| [`POST /api/session-media/intents/{key}/upload`](../backend/contracts/openapi.json#L48910) · `upload_api_session_media_intents__key__upload_post` | path: `key`*, header: `Idempotency-Key`*, header: `Origin`* | [OriginalLibraryAction](../backend/contracts/openapi.json#L4799) | 200: [UploadLease](../backend/contracts/openapi.json#L10752) | SessionCSRF + StaffSession |
| [`GET /api/session-outcomes/{request_key}`](../backend/contracts/openapi.json#L49368) · `reconcile_session_outcome_api_session_outcomes__request_key__get` | path: `request_key`* | — | 200: [OutcomeSaved](../backend/contracts/openapi.json#L4939) | StaffSession |
| [`GET /api/session-plans/{request_key}`](../backend/contracts/openapi.json#L49793) · `reconcile_session_plan_api_session_plans__request_key__get` | path: `request_key`* | — | 200: [PlanCopied](../backend/contracts/openapi.json#L6442) or [PlanSaved](../backend/contracts/openapi.json#L6594) | StaffSession |
| [`GET /api/session-postponements/{request_key}`](../backend/contracts/openapi.json#L50226) · `reconcileSessionPostponement` | path: `request_key`* | — | 200: [PostponementState](../backend/contracts/openapi.json#L6681) | StaffSession |
| [`GET /api/session-summaries/{request_key}`](../backend/contracts/openapi.json#L50651) · `reconcile_session_summary_api_session_summaries__request_key__get` | path: `request_key`* | — | 200: [SummarySaved](../backend/contracts/openapi.json#L10034) | StaffSession |
| [`GET /api/session-undos/{key}`](../backend/contracts/openapi.json#L51076) · `reconcile_api_session_undos__key__get` | path: `key`* | — | 200: [UndoSaved](../backend/contracts/openapi.json#L10677) | StaffSession |
| [`GET /api/sessions`](../backend/contracts/openapi.json#L51501) · `listSessions` | query: `limit`, query: `offset` | — | 200: [Page_SessionSummary_](../backend/contracts/openapi.json#L5478) | StaffSession |
| [`GET /api/sessions/{identity}/exercises/{item_id}/video`](../backend/contracts/openapi.json#L51940) · `read_api_sessions__identity__exercises__item_id__video_get` | path: `identity`*, path: `item_id`* | — | 200: [ReadLease](../backend/contracts/openapi.json#L7164) or `null` | StaffSession |
| [`GET /api/sessions/{identity}/exercises/{item_id}/video/check`](../backend/contracts/openapi.json#L52383) · `recheck_api_sessions__identity__exercises__item_id__video_check_get` | path: `identity`*, path: `item_id`*, query: `version`* | — | 200: [MediaReadCheck](../backend/contracts/openapi.json#L3900) | StaffSession |
| [`GET /api/sessions/{identity}/exercises/{item_id}/video/review`](../backend/contracts/openapi.json#L52827) · `review_api_sessions__identity__exercises__item_id__video_review_get` | path: `identity`*, path: `item_id`* | — | 200: [RecordingReview](../backend/contracts/openapi.json#L7297) | StaffSession |
| [`GET /api/sessions/{session_id}`](../backend/contracts/openapi.json#L53262) · `getSession` | path: `session_id`* | — | 200: [SessionSummary](../backend/contracts/openapi.json#L9754) | StaffSession |
| [`POST /api/sessions/{session_id}/acknowledgement`](../backend/contracts/openapi.json#L53687) · `save_session_acknowledgement_api_sessions__session_id__acknowledgement_post` | path: `session_id`*, header: `Idempotency-Key`*, header: `Origin`* | [SaveAcknowledgement](../backend/contracts/openapi.json#L8173) | 200: [AcknowledgementSaved](../backend/contracts/openapi.json#L52) | SessionCSRF + StaffSession |
| [`GET /api/sessions/{session_id}/acknowledgement-review`](../backend/contracts/openapi.json#L54145) · `review_session_acknowledgement_api_sessions__session_id__acknowledgement_review_get` | path: `session_id`* | — | 200: [AcknowledgementReview](../backend/contracts/openapi.json#L4) | StaffSession |
| [`GET /api/sessions/{session_id}/attribution`](../backend/contracts/openapi.json#L54570) · `readSessionAttribution` | path: `session_id`* | — | 200: [AttributionRead](../backend/contracts/openapi.json#L722) | StaffSession |
| [`POST /api/sessions/{session_id}/booking`](../backend/contracts/openapi.json#L54995) · `saveSessionBooking` | path: `session_id`*, header: `Idempotency-Key`*, header: `Origin`* | [SaveSessionBooking](../backend/contracts/openapi.json#L8827) | 200: [SessionBookingState](../backend/contracts/openapi.json#L9087) | SessionCSRF + StaffSession |
| [`GET /api/sessions/{session_id}/booking-review`](../backend/contracts/openapi.json#L55453) · `reviewSessionBooking` | path: `session_id`* | — | 200: [SessionBookingReview](../backend/contracts/openapi.json#L9028) | StaffSession |
| [`GET /api/sessions/{session_id}/change-review`](../backend/contracts/openapi.json#L55878) · `reviewTrainerSessionChange` | path: `session_id`*, query: `kind`* | — | 200: [SessionChangeReview](../backend/contracts/openapi.json#L9196) | StaffSession |
| [`GET /api/sessions/{session_id}/client`](../backend/contracts/openapi.json#L56316) · `getSessionClient` | path: `session_id`* | — | 200: [SessionClient](../backend/contracts/openapi.json#L9330) | StaffSession |
| [`POST /api/sessions/{session_id}/copy-plan`](../backend/contracts/openapi.json#L56741) · `copy_session_plan_api_sessions__session_id__copy_plan_post` | path: `session_id`*, header: `Idempotency-Key`*, header: `Origin`* | [CopyPlan](../backend/contracts/openapi.json#L2089) | 200: [PlanCopied](../backend/contracts/openapi.json#L6442) | SessionCSRF + StaffSession |
| [`GET /api/sessions/{session_id}/details`](../backend/contracts/openapi.json#L57199) · `readSessionDetails` | path: `session_id`* | — | 200: [SessionDetailRead](../backend/contracts/openapi.json#L9411) | StaffSession |
| [`POST /api/sessions/{session_id}/handoff`](../backend/contracts/openapi.json#L57624) · `mark_session_handoff_api_sessions__session_id__handoff_post` | path: `session_id`*, header: `Idempotency-Key`*, header: `Origin`* | [MarkHandoff](../backend/contracts/openapi.json#L3735) | 200: [HandoffSaved](../backend/contracts/openapi.json#L3491) | SessionCSRF + StaffSession |
| [`GET /api/sessions/{session_id}/handoff-review`](../backend/contracts/openapi.json#L58082) · `review_session_handoff_api_sessions__session_id__handoff_review_get` | path: `session_id`* | — | 200: [HandoffReview](../backend/contracts/openapi.json#L3448) | StaffSession |
| [`POST /api/sessions/{session_id}/outcome`](../backend/contracts/openapi.json#L58507) · `save_session_outcome_api_sessions__session_id__outcome_post` | path: `session_id`*, header: `Idempotency-Key`*, header: `Origin`* | [SaveOutcome](../backend/contracts/openapi.json#L8597) | 200: [OutcomeSaved](../backend/contracts/openapi.json#L4939) | SessionCSRF + StaffSession |
| [`GET /api/sessions/{session_id}/outcome-review`](../backend/contracts/openapi.json#L58965) · `review_session_outcome_api_sessions__session_id__outcome_review_get` | path: `session_id`* | — | 200: [OutcomeReview](../backend/contracts/openapi.json#L4806) | StaffSession |
| [`POST /api/sessions/{session_id}/plan`](../backend/contracts/openapi.json#L59390) · `save_session_plan_api_sessions__session_id__plan_post` | path: `session_id`*, header: `Idempotency-Key`*, header: `Origin`* | [SavePlan](../backend/contracts/openapi.json#L8693) | 200: [PlanSaved](../backend/contracts/openapi.json#L6594) | SessionCSRF + StaffSession |
| [`GET /api/sessions/{session_id}/plan-review`](../backend/contracts/openapi.json#L59848) · `review_session_plan_api_sessions__session_id__plan_review_get` | path: `session_id`* | — | 200: [PlanReview](../backend/contracts/openapi.json#L6561) | StaffSession |
| [`POST /api/sessions/{session_id}/postponement`](../backend/contracts/openapi.json#L60273) · `postponeSession` | path: `session_id`*, header: `Idempotency-Key`*, header: `Origin`* | [PostponeSession](../backend/contracts/openapi.json#L6628) | 200: [PostponementState](../backend/contracts/openapi.json#L6681) | SessionCSRF + StaffSession |
| [`GET /api/sessions/{session_id}/postponement-review`](../backend/contracts/openapi.json#L60731) · `reviewSessionPostponement` | path: `session_id`* | — | 200: [PostponementReview](../backend/contracts/openapi.json#L6643) | StaffSession |
| [`GET /api/sessions/{session_id}/previous-plan`](../backend/contracts/openapi.json#L61156) · `previous_session_plan_api_sessions__session_id__previous_plan_get` | path: `session_id`* | — | 200: [PreviousPlan](../backend/contracts/openapi.json#L6767) | StaffSession |
| [`POST /api/sessions/{session_id}/summary`](../backend/contracts/openapi.json#L61581) · `save_session_summary_api_sessions__session_id__summary_post` | path: `session_id`*, header: `Idempotency-Key`*, header: `Origin`* | [SaveSummary](../backend/contracts/openapi.json#L8866) | 200: [SummarySaved](../backend/contracts/openapi.json#L10034) | SessionCSRF + StaffSession |
| [`GET /api/sessions/{session_id}/summary-review`](../backend/contracts/openapi.json#L62039) · `review_session_summary_api_sessions__session_id__summary_review_get` | path: `session_id`* | — | 200: [SummaryReview](../backend/contracts/openapi.json#L10004) | StaffSession |
| [`POST /api/sessions/{session_id}/time-change`](../backend/contracts/openapi.json#L62464) · `requestSessionTimeChange` | path: `session_id`*, header: `Idempotency-Key`*, header: `Origin`* | [ChangeTime](../backend/contracts/openapi.json#L1319) | 200: [SessionChangeState](../backend/contracts/openapi.json#L9273) | SessionCSRF + StaffSession |
| [`POST /api/sessions/{session_id}/trainer-change`](../backend/contracts/openapi.json#L62922) · `requestSessionTrainerChange` | path: `session_id`*, header: `Idempotency-Key`*, header: `Origin`* | [ChangeTrainer](../backend/contracts/openapi.json#L1352) | 200: [SessionChangeState](../backend/contracts/openapi.json#L9273) | SessionCSRF + StaffSession |
| [`POST /api/staff/admins`](../backend/contracts/openapi.json#L63380) · `createAdmin` | header: `Idempotency-Key`*, header: `Origin`* | [NewAdmin](../backend/contracts/openapi.json#L4274) | 200: [AdminCreated](../backend/contracts/openapi.json#L103) | SessionCSRF + StaffSession |
| [`GET /api/staff/trainer-creations/{request_key}`](../backend/contracts/openapi.json#L63828) · `reconcileTrainerCreation` | path: `request_key`* | — | 200: [TrainerCreated](../backend/contracts/openapi.json#L10096) | StaffSession |
| [`POST /api/staff/trainers`](../backend/contracts/openapi.json#L64253) · `createTrainer` | header: `Idempotency-Key`*, header: `Origin`* | [NewTrainer](../backend/contracts/openapi.json#L4482) | 200: [TrainerCreated](../backend/contracts/openapi.json#L10096) | SessionCSRF + StaffSession |
| [`GET /api/trainer-approval-saves/{request_key}`](../backend/contracts/openapi.json#L64701) · `reconcileTrainerApprovals` | path: `request_key`* | — | 200: [ApprovalState](../backend/contracts/openapi.json#L174) | StaffSession |
| [`GET /api/trainer-availability-saves/{request_key}`](../backend/contracts/openapi.json#L65126) · `reconcileTrainerAvailability` | path: `request_key`* | — | 200: [AvailabilityState](../backend/contracts/openapi.json#L839) | StaffSession |
| [`GET /api/trainer-deactivations/{request_key}`](../backend/contracts/openapi.json#L65551) · `reconcileTrainerDeactivation` | path: `request_key`* | — | 200: [TrainerDeactivationState](../backend/contracts/openapi.json#L10348) | StaffSession |
| [`GET /api/trainer-detail-saves/{request_key}`](../backend/contracts/openapi.json#L65976) · `reconcileTrainerDetails` | path: `request_key`* | — | 200: [RateState](../backend/contracts/openapi.json#L6977) | StaffSession |
| [`GET /api/trainer-email-requests/{key}`](../backend/contracts/openapi.json#L66401) · `reconcileTrainerEmailRequest` | path: `key`* | — | 200: [EmailState](../backend/contracts/openapi.json#L3253) | StaffSession |
| [`GET /api/trainer-rate-saves/{request_key}`](../backend/contracts/openapi.json#L66826) · `reconcileTrainerRates` | path: `request_key`* | — | 200: [RateState](../backend/contracts/openapi.json#L6977) | StaffSession |
| [`GET /api/trainer-reactivations/{request_key}`](../backend/contracts/openapi.json#L67251) · `reconcileTrainerReactivation` | path: `request_key`* | — | 200: [ReactivationState](../backend/contracts/openapi.json#L7137) | StaffSession |
| [`GET /api/trainers`](../backend/contracts/openapi.json#L67676) · `listTrainers` | query: `limit`, query: `offset` | — | 200: [Page_TrainerSummary_](../backend/contracts/openapi.json#L5510) | StaffSession |
| [`GET /api/trainers/{trainer_id}`](../backend/contracts/openapi.json#L68115) · `getTrainer` | path: `trainer_id`* | — | 200: [TrainerSummary](../backend/contracts/openapi.json#L10576) | StaffSession |
| [`POST /api/trainers/{trainer_id}/approvals`](../backend/contracts/openapi.json#L68540) · `saveTrainerApprovals` | path: `trainer_id`*, header: `Idempotency-Key`*, header: `Origin`* | [SaveApprovals](../backend/contracts/openapi.json#L8227) | 200: [ApprovalState](../backend/contracts/openapi.json#L174) | SessionCSRF + StaffSession |
| [`POST /api/trainers/{trainer_id}/availability`](../backend/contracts/openapi.json#L68998) · `saveTrainerAvailability` | path: `trainer_id`*, header: `Idempotency-Key`*, header: `Origin`* | [SaveAvailability](../backend/contracts/openapi.json#L8348) | 200: [AvailabilityState](../backend/contracts/openapi.json#L839) | SessionCSRF + StaffSession |
| [`POST /api/trainers/{trainer_id}/deactivation`](../backend/contracts/openapi.json#L69456) · `saveTrainerDeactivation` | path: `trainer_id`*, header: `Idempotency-Key`*, header: `Origin`* | [TrainerDeactivationSelection](../backend/contracts/openapi.json#L10223) | 200: [TrainerDeactivationState](../backend/contracts/openapi.json#L10348) | SessionCSRF + StaffSession |
| [`GET /api/trainers/{trainer_id}/deactivation-review`](../backend/contracts/openapi.json#L69914) · `reviewTrainerDeactivation` | path: `trainer_id`* | — | 200: [TrainerDeactivationReview](../backend/contracts/openapi.json#L10159) | StaffSession |
| [`POST /api/trainers/{trainer_id}/deactivation-review`](../backend/contracts/openapi.json#L69914) · `previewTrainerDeactivation` | path: `trainer_id`*, header: `Idempotency-Key`*, header: `Origin`* | [TrainerDeactivationSelection](../backend/contracts/openapi.json#L10223) | 200: [TrainerDeactivationReview](../backend/contracts/openapi.json#L10159) | SessionCSRF + StaffSession |
| [`GET /api/trainers/{trainer_id}/email-change`](../backend/contracts/openapi.json#L70795) · `pendingTrainerEmailChange` | path: `trainer_id`* | — | 200: [PendingEmail](../backend/contracts/openapi.json#L5941) | StaffSession |
| [`POST /api/trainers/{trainer_id}/email-change`](../backend/contracts/openapi.json#L70795) · `requestTrainerEmailChange` | path: `trainer_id`*, header: `Idempotency-Key`*, header: `Origin`* | [EmailRequest](../backend/contracts/openapi.json#L3219) | 200: [EmailState](../backend/contracts/openapi.json#L3253) | SessionCSRF + StaffSession |
| [`POST /api/trainers/{trainer_id}/personal-details`](../backend/contracts/openapi.json#L71676) · `saveTrainerDetails` | path: `trainer_id`*, header: `Idempotency-Key`*, header: `Origin`* | [SaveTrainerDetails](../backend/contracts/openapi.json#L8888) | 200: [RateState](../backend/contracts/openapi.json#L6977) | SessionCSRF + StaffSession |
| [`POST /api/trainers/{trainer_id}/rates`](../backend/contracts/openapi.json#L72134) · `saveTrainerRates` | path: `trainer_id`*, header: `Idempotency-Key`*, header: `Origin`* | [SaveRates](../backend/contracts/openapi.json#L8718) | 200: [RateState](../backend/contracts/openapi.json#L6977) | SessionCSRF + StaffSession |
| [`GET /api/trainers/{trainer_id}/reactivation`](../backend/contracts/openapi.json#L72592) · `reviewTrainerReactivation` | path: `trainer_id`* | — | 200: [ReactivationReview](../backend/contracts/openapi.json#L7090) | StaffSession |
| [`POST /api/trainers/{trainer_id}/reactivation`](../backend/contracts/openapi.json#L72592) · `reactivateTrainer` | path: `trainer_id`*, header: `Idempotency-Key`*, header: `Origin`* | [ReactivateTrainer](../backend/contracts/openapi.json#L7021) | 200: [ReactivationState](../backend/contracts/openapi.json#L7137) | SessionCSRF + StaffSession |
| [`POST /auth/challenge`](../backend/contracts/openapi.json#L73473) · `staffChallenge` | header: `Origin`* | [Challenge](../backend/contracts/openapi.json#L1257) | 200: [AuthChallenge](../backend/contracts/openapi.json#L780) or [SignedIn](../backend/contracts/openapi.json#L9917) | StaffFlow |
| [`POST /auth/change-password`](../backend/contracts/openapi.json#L73916) · `staffChangePassword` | header: `Origin`* | [ChangePassword](../backend/contracts/openapi.json#L1292) | 200: [PasswordChanged](../backend/contracts/openapi.json#L5542) | SessionCSRF + StaffSession |
| [`GET /auth/email-change`](../backend/contracts/openapi.json#L74352) · `pendingStaffEmailChange` | — | — | 200: [PendingEmail](../backend/contracts/openapi.json#L5941) | StaffSession |
| [`POST /auth/email-change/{change_id}/reconcile`](../backend/contracts/openapi.json#L74765) · `reconcileStaffEmailChange` | path: `change_id`*, header: `Origin`* | — | 200: [EmailState](../backend/contracts/openapi.json#L3253) | SessionCSRF + StaffSession |
| [`POST /auth/email-change/{change_id}/send`](../backend/contracts/openapi.json#L75201) · `sendStaffEmailCode` | path: `change_id`*, header: `Origin`* | — | 200: [EmailState](../backend/contracts/openapi.json#L3253) | SessionCSRF + StaffSession |
| [`POST /auth/email-change/{change_id}/verify`](../backend/contracts/openapi.json#L75637) · `verifyStaffEmailChange` | path: `change_id`*, header: `Origin`* | [EmailCode](../backend/contracts/openapi.json#L3201) | 200: [EmailState](../backend/contracts/openapi.json#L3253) | SessionCSRF + StaffSession |
| [`POST /auth/forgot-password`](../backend/contracts/openapi.json#L76083) · `staffForgotPassword` | header: `Origin`* | [ForgotPassword](../backend/contracts/openapi.json#L3382) | 200: [RecoveryStarted](../backend/contracts/openapi.json#L7421) | No declared staff security |
| [`GET /auth/policy`](../backend/contracts/openapi.json#L76513) · `staffAuthPolicy` | — | — | 200: [AuthPolicy](../backend/contracts/openapi.json#L816) | No declared staff security |
| [`POST /auth/refresh`](../backend/contracts/openapi.json#L76921) · `staffRefresh` | header: `Origin`* | [Input](../backend/contracts/openapi.json#L3554) | 200: [Refreshed](../backend/contracts/openapi.json#L7435) | SessionCSRF + StaffSession |
| [`POST /auth/reset-password`](../backend/contracts/openapi.json#L77357) · `staffResetPassword` | header: `Origin`* | [ResetPassword](../backend/contracts/openapi.json#L7969) | 200: [PasswordReset](../backend/contracts/openapi.json#L5602) | StaffFlow |
| [`GET /auth/session`](../backend/contracts/openapi.json#L77792) · `staffSessionBootstrap` | — | — | 200: [SessionBootstrap](../backend/contracts/openapi.json#L9129) | StaffSession |
| [`POST /auth/sign-in`](../backend/contracts/openapi.json#L78205) · `staffSignIn` | header: `Origin`* | [SignIn](../backend/contracts/openapi.json#L9880) | 200: [AuthChallenge](../backend/contracts/openapi.json#L780) | No declared staff security |
| [`POST /auth/sign-out`](../backend/contracts/openapi.json#L78635) · `staffSignOut` | header: `Origin`* | [SignOut](../backend/contracts/openapi.json#L9905) | 200: [SignedOut](../backend/contracts/openapi.json#L9941) | SessionCSRF + StaffSession |
| [`GET /health/live`](../backend/contracts/openapi.json#L79071) · `healthLive` | — | — | 200: [Live](../backend/contracts/openapi.json#L3699) | No declared staff security |
| [`GET /health/ready`](../backend/contracts/openapi.json#L79479) · `healthReady` | — | — | 200: [Ready](../backend/contracts/openapi.json#L7198) | No declared staff security |
| [`GET /me`](../backend/contracts/openapi.json#L79887) · `staffMe` | — | — | 200: [SessionInfo](../backend/contracts/openapi.json#L9497) | StaffSession |

### Request and response schema index

This index locates **all246 schemas** and lists required fields for navigation. Follow each link for every optional field, nested definition, enum, nullability, default, length/range/pattern and additional-property constraint. The JSON remains the field-level authority; required-field lists alone are insufficient to construct a valid request. Historical DTO explanations are preserved in [Journey](journey.md#service-contract-decision-history), labelled by their original dates rather than presented as current.

| Schema | Required fields / shape |
| --- | --- |
| [AcknowledgementReview](../backend/contracts/openapi.json#L4) | `sessionId`, `version`, `expected`, `previousMethod`, `used`, `total` |
| [AcknowledgementSaved](../backend/contracts/openapi.json#L52) | `sessionId`, `version`, `acknowledgementId`, `method`, `sequence`, `used`, `savedAt` |
| [AdminCreated](../backend/contracts/openapi.json#L103) | `id`, `name`, `email`, `role`, `invitation` |
| [ApprovalControls](../backend/contracts/openapi.json#L145) | `availability`, `sessionTime`, `trainerReassignment`, `fixedWeeklySchedule` |
| [ApprovalState](../backend/contracts/openapi.json#L174) | `id`, `version`, `approvalNeeded` |
| [ApprovePay](../backend/contracts/openapi.json#L199) | `revision` |
| [AssessmentRevision](../backend/contracts/openapi.json#L214) | `id`, `assessment_id`, `revision`, `previous_revision`, `form_id`, `form_version`, `status`, `event`, `assessment_date`, `assessor_id`, `assessor_name`, `client_name`, `client_birthday`, `answers`, `actor_id`, `actor_name`, `reason`, `created_at` |
| [AssignmentChoice](../backend/contracts/openapi.json#L358) | `id`, `name`, `version`, `error` |
| [AssignmentHistory](../backend/contracts/openapi.json#L395) | `id`, `at`, `actor`, `previous`, `replacement` |
| [AssignmentPurchase](../backend/contracts/openapi.json#L428) | `id`, `version`, `trainerId`, `name` |
| [AssignmentRead](../backend/contracts/openapi.json#L459) | `id`, `oldTrainerId`, `newTrainerId`, `recordedBy`, `recordedAt`, `reason`, `requestId`, `requestedBy` |
| [AssignmentReview](../backend/contracts/openapi.json#L525) | `id`, `version`, `name`, `expected`, `current`, `purchases`, `sessions`, `choices`, `history` |
| [AssignmentSession](../backend/contracts/openapi.json#L592) | `id`, `version`, `trainerId`, `purchaseId`, `scheduleState`, `date`, `startsAt`, `endsAt` |
| [AssignmentState](../backend/contracts/openapi.json#L670) | `id`, `version`, `trainerId`, `eventId` |
| [AssignmentTrainer](../backend/contracts/openapi.json#L702) | `id`, `name` |
| [AttributionRead](../backend/contracts/openapi.json#L722) | `sessionId`, `originalState`, `original`, `assigned`, `performedBy`, `history` |
| [AuthChallenge](../backend/contracts/openapi.json#L780) | `challenge`, `expiresAt` |
| [AuthPolicy](../backend/contracts/openapi.json#L816) | `password`, `mfa`, `recovery` |
| [AvailabilityState](../backend/contracts/openapi.json#L839) | `outcome`, `trainer`, `requestId` |
| [AvailabilityTrainer](../backend/contracts/openapi.json#L874) | `id`, `version` |
| [AvailabilityWindow](../backend/contracts/openapi.json#L895) | `weekday`, `startsAt`, `endsAt` |
| [BookingPosition](../backend/contracts/openapi.json#L923) | `id`, `version`, `sessionNumber`, `scheduleState`, `date`, `startsAt`, `endsAt`, `trainerId`, `slotId` |
| [BookingSavedVersion](../backend/contracts/openapi.json#L1019) | `id`, `version` |
| [BookingTrainer](../backend/contracts/openapi.json#L1039) | `id`, `version`, `name` |
| [CalendarSession](../backend/contracts/openapi.json#L1064) | `readAccess`, `id`, `version`, `clientId`, `purchaseId`, `trainerId`, `scheduleState`, `sessionNumber`, `date`, `startsAt`, `endsAt`, `status` |
| [CancelRequest](../backend/contracts/openapi.json#L1181) | `expectedVersion` |
| [CancellationState](../backend/contracts/openapi.json#L1196) | `id`, `version`, `at`, `by` |
| [Catalogue](../backend/contracts/openapi.json#L1233) | `items` |
| [Challenge](../backend/contracts/openapi.json#L1257) | No required fields; inspect optional fields |
| [ChangePassword](../backend/contracts/openapi.json#L1292) | `currentPassword`, `newPassword` |
| [ChangeTime](../backend/contracts/openapi.json#L1319) | `expected`, `date`, `startsAt`, `endsAt` |
| [ChangeTrainer](../backend/contracts/openapi.json#L1352) | `expected`, `trainerId` |
| [ClientAssessmentRecords](../backend/contracts/openapi.json#L1373) | `id`, `version`, `businessDate`, `people` |
| [ClientDetail](../backend/contracts/openapi.json#L1407) | `id`, `version`, `name`, `kind`, `status`, `trainer_id`, `people` |
| [ClientDetailState](../backend/contracts/openapi.json#L1464) | `id`, `version`, `people` |
| [ClientOnboardingPolicy](../backend/contracts/openapi.json#L1492) | No required fields; inspect optional fields |
| [ClientProgress](../backend/contracts/openapi.json#L1565) | `clientId`, `exercises` |
| [ClientReactivationReview](../backend/contracts/openapi.json#L1588) | `id`, `version`, `name`, `expected`, `purchaseIds`, `rows`, `packageError` |
| [ClientReactivationState](../backend/contracts/openapi.json#L1647) | `id`, `version` |
| [ClientRenewalState](../backend/contracts/openapi.json#L1674) | `id`, `version`, `purchaseId` |
| [ClientSummary](../backend/contracts/openapi.json#L1701) | `id`, `version`, `name`, `kind`, `status`, `trainer_id` |
| [ClientWeeklyPreview](../backend/contracts/openapi.json#L1750) | `expected`, `outcome`, `updatedSessions` |
| [ClientWeeklyReview](../backend/contracts/openapi.json#L1778) | `id`, `version`, `name`, `purchaseId`, `purchaseVersion`, `trainerId`, `trainerVersion`, `outcome`, `expected`, `slots`, `sessions` |
| [ClientWeeklySession](../backend/contracts/openapi.json#L1856) | `id`, `version`, `trainerId`, `date`, `startsAt`, `endsAt`, `slotId` |
| [ClientWeeklySlot](../backend/contracts/openapi.json#L1911) | `id`, `weekday`, `startsAt`, `endsAt` |
| [ClientWeeklyState](../backend/contracts/openapi.json#L1945) | `outcome`, `client`, `requestId`, `updatedSessions` |
| [ContentDraft](../backend/contracts/openapi.json#L1985) | `key`, `title`, `body`, `status` |
| [ContentState](../backend/contracts/openapi.json#L2025) | `key`, `title`, `body`, `status`, `id`, `version`, `created_at`, `updated_at` |
| [CopyPlan](../backend/contracts/openapi.json#L2089) | `expected`, `sourceId`, `sourceExpected` |
| [CreateClient](../backend/contracts/openapi.json#L2116) | `packageId`, `packageVersion`, `startDate`, `sessionsPerWeek`, `genderPreference`, `clientPreferences`, `type`, `people`, `trainerId`, `trainerVersion`, `fixedWeeklySchedule`, `remarks` |
| [CreatedClient](../backend/contracts/openapi.json#L2217) | `id`, `version`, `purchaseId` |
| [DeactivateClient](../backend/contracts/openapi.json#L2243) | `expectedVersion`, `expectedTrainerId`, `purchases` |
| [DeactivationReview](../backend/contracts/openapi.json#L2273) | `id`, `version`, `name`, `trainerId`, `purchases` |
| [DeactivationState](../backend/contracts/openapi.json#L2314) | `id`, `version` |
| [DirectoryClient](../backend/contracts/openapi.json#L2341) | `id`, `version`, `name`, `kind`, `status`, `trainer_id`, `gender_preference`, `remarks`, `people`, `purchases` |
| [DirectoryPackage](../backend/contracts/openapi.json#L2428) | `id`, `version`, `revision`, `status`, `name`, `total_sessions`, `validity_days` |
| [DirectoryPerson](../backend/contracts/openapi.json#L2477) | `id`, `version`, `position`, `name`, `birthday`, `email`, `phone_country_code`, `phone_number`, `gender`, `emergency_name`, `emergency_relationship`, `emergency_country_code`, `emergency_number` |
| [DirectoryPurchase](../backend/contracts/openapi.json#L2560) | `id`, `version`, `template_id`, `template_revision`, `name`, `total_sessions`, `validity_days`, `sessions_per_week`, `free_gym`, `start_date`, `end_date`, `purchased_trainer_id`, `trainer_name`, `trainer_id`, `status`, `stage`, `used`, `schedule` |
| [DirectorySlot](../backend/contracts/openapi.json#L2677) | `id`, `weekday`, `starts_at`, `ends_at` |
| [DirectorySnapshot](../backend/contracts/openapi.json#L2709) | `serverAt`, `businessDate`, `timeZone`, `schemaVersion`, `viewerId`, `clients`, `trainers`, `packages`, `packagePolicy`, `trainerOnboardingPolicy` |
| [DirectoryTrainer](../backend/contracts/openapi.json#L3027) | `id`, `version`, `name`, `status`, `email`, `phone_country_code`, `phone_number`, `birthday`, `gender`, `trainer_type`, `qualifications`, `public_profile`, `approve_availability`, `approve_session_time`, `approve_session_trainer`, `approve_weekly_schedule`, `availability`, `peak_rate_cents`, `off_peak_rate_cents` |
| [DismissRenewal](../backend/contracts/openapi.json#L3147) | `expectedClientVersion` |
| [DismissalActor](../backend/contracts/openapi.json#L3162) | `id`, `name` |
| [DismissalEvidence](../backend/contracts/openapi.json#L3182) | `at`, `by` |
| [EmailCode](../backend/contracts/openapi.json#L3201) | `code` |
| [EmailRequest](../backend/contracts/openapi.json#L3219) | `expectedVersion`, `email` |
| [EmailState](../backend/contracts/openapi.json#L3253) | `id`, `email`, `state` |
| [Emergency](../backend/contracts/openapi.json#L3291) | `countryCode`, `number`, `name`, `relationship` |
| [ErrorDetail](../backend/contracts/openapi.json#L3345) | `code`, `message`, `requestId` |
| [ErrorEnvelope](../backend/contracts/openapi.json#L3369) | `error` |
| [ForgotPassword](../backend/contracts/openapi.json#L3382) | `email` |
| [FormDefinition](../backend/contracts/openapi.json#L3398) | `form_id`, `version`, `title`, `source_filename`, `source_sha256`, `layout_release`, `layout_sha256`, `definition` |
| [HandoffReview](../backend/contracts/openapi.json#L3448) | `sessionId`, `version`, `expected`, `whatsappOpenedAt`, `whatsappOpenCount` |
| [HandoffSaved](../backend/contracts/openapi.json#L3491) | `sessionId`, `version`, `whatsappOpenedAt`, `whatsappOpenCount` |
| [InitialAssessment](../backend/contracts/openapi.json#L3522) | `formId`, `formVersion`, `assessmentDate`, `answers` |
| [Input](../backend/contracts/openapi.json#L3554) | No required fields; inspect optional fields |
| [LibraryExercise](../backend/contracts/openapi.json#L3560) | `id`, `name`, `category`, `description`, `status`, `version`, `createdAt`, `updatedAt`, `media` |
| [LibraryIntentView](../backend/contracts/openapi.json#L3627) | `key`, `state`, `uploadUntil`, `result` |
| [LibraryMedia](../backend/contracts/openapi.json#L3669) | `id`, `name`, `type`, `size` |
| [Live](../backend/contracts/openapi.json#L3699) | `status` |
| [MFAPolicy](../backend/contracts/openapi.json#L3714) | `required`, `method` |
| [MarkHandoff](../backend/contracts/openapi.json#L3735) | `expected` |
| [MatchRequest](../backend/contracts/openapi.json#L3750) | `packageId`, `packageVersion`, `startDate`, `sessionsPerWeek`, `genderPreference`, `clientPreferences` |
| [MatchResult](../backend/contracts/openapi.json#L3804) | `matches` |
| [MatchedSlot](../backend/contracts/openapi.json#L3821) | `day`, `from`, `to` |
| [Measurement](../backend/contracts/openapi.json#L3856) | `id`, `loadKg`, `reps`, `sets` |
| [MediaReadCheck](../backend/contracts/openapi.json#L3900) | `valid` |
| [MessageReadState](../backend/contracts/openapi.json#L3915) | `id`, `version`, `read`, `readAt` |
| [MessageRequest](../backend/contracts/openapi.json#L3954) | `id`, `version`, `kind`, `status`, `trainer_id`, `client_id`, `purchase_id`, `session_id`, `expected_version`, `replacement_trainer_id`, `old_date`, `old_start`, `old_end`, `new_date`, `new_start`, `new_end`, `resolved_at`, `resolution_note`, `slots` |
| [MessageRequestSlot](../backend/contracts/openapi.json#L4175) | `side`, `slot_identity`, `weekday`, `starts_at`, `ends_at` |
| [MessageUndoEvidence](../backend/contracts/openapi.json#L4218) | `id`, `count`, `expiresAt`, `status` |
| [NewAdmin](../backend/contracts/openapi.json#L4274) | `name`, `email`, `phone_country_code`, `phone_number`, `birthday`, `gender` |
| [NewAssessment](../backend/contracts/openapi.json#L4327) | `formId`, `formVersion`, `expectedPersonVersion`, `answers` |
| [NewPerson](../backend/contracts/openapi.json#L4419) | `name`, `email`, `phone`, `birthday`, `gender`, `emergencyContact`, `healthNotes`, `assessments` |
| [NewTrainer](../backend/contracts/openapi.json#L4482) | `name`, `email`, `phone_country_code`, `phone_number`, `birthday`, `gender`, `trainerType`, `qualifications`, `publicProfile`, `slots`, `approvalNeeded` |
| [NotePatch](../backend/contracts/openapi.json#L4581) | No required fields; inspect optional fields |
| [NoteState](../backend/contracts/openapi.json#L4612) | `id`, `version` |
| [NoteView](../backend/contracts/openapi.json#L4632) | `id`, `version`, `remarks`, `healthNotes`, `people` |
| [OnboardingAvailability](../backend/contracts/openapi.json#L4670) | No required fields; inspect optional fields |
| [OperationalTrainer](../backend/contracts/openapi.json#L4689) | `id`, `version`, `name`, `status`, `email`, `phone_country_code`, `phone_number`, `birthday`, `gender`, `trainer_type`, `qualifications`, `public_profile`, `approve_availability`, `approve_session_time`, `approve_session_trainer`, `approve_weekly_schedule`, `availability` |
| [OriginalLibraryAction](../backend/contracts/openapi.json#L4799) | No required fields; inspect optional fields |
| [OutcomeReview](../backend/contracts/openapi.json#L4806) | `sessionId`, `version`, `expected`, `durationMinutes`, `trainerComments`, `rows`, `draftRows` |
| [OutcomeRow](../backend/contracts/openapi.json#L4857) | `id`, `resultId`, `planItemId`, `name`, `loadKg`, `reps`, `sets` |
| [OutcomeSaved](../backend/contracts/openapi.json#L4939) | `sessionId`, `version`, `durationMinutes`, `trainerComments`, `rows`, `savedAt` |
| [OwnerTrainerOnboardingPolicy](../backend/contracts/openapi.json#L4983) | No required fields; inspect optional fields |
| [PackageActionReview](../backend/contracts/openapi.json#L4999) | `clientId`, `clientVersion`, `purchaseId`, `purchaseVersion`, `name`, `status`, `operation`, `expected`, `eligible` |
| [PackageActionState](../backend/contracts/openapi.json#L5066) | `id`, `clientId`, `purchaseId`, `purchaseVersion`, `status`, `deletedSessionIds`, `messageId`, `undoUntil` |
| [PackageDraft](../backend/contracts/openapi.json#L5142) | `name`, `total`, `status` |
| [PackagePolicy](../backend/contracts/openapi.json#L5174) | No required fields; inspect optional fields |
| [PackageReactivationReview](../backend/contracts/openapi.json#L5205) | `id`, `version`, `name`, `expected`, `purchaseIds`, `rows`, `packageError`, `packageId` |
| [PackageReactivationState](../backend/contracts/openapi.json#L5270) | `id`, `version`, `packageId` |
| [PackageUndoReview](../backend/contracts/openapi.json#L5303) | `id`, `messageId`, `clientId`, `purchaseId`, `expected`, `expiresAt`, `sessions` |
| [PackageUndoState](../backend/contracts/openapi.json#L5355) | `id`, `undoneAt` |
| [Page_AssessmentRevision_](../backend/contracts/openapi.json#L5382) | `items`, `limit`, `offset`, `hasMore` |
| [Page_ClientSummary_](../backend/contracts/openapi.json#L5414) | `items`, `limit`, `offset`, `hasMore` |
| [Page_FormDefinition_](../backend/contracts/openapi.json#L5446) | `items`, `limit`, `offset`, `hasMore` |
| [Page_SessionSummary_](../backend/contracts/openapi.json#L5478) | `items`, `limit`, `offset`, `hasMore` |
| [Page_TrainerSummary_](../backend/contracts/openapi.json#L5510) | `items`, `limit`, `offset`, `hasMore` |
| [PasswordChanged](../backend/contracts/openapi.json#L5542) | `passwordChanged`, `signedOut` |
| [PasswordPolicy](../backend/contracts/openapi.json#L5563) | `minimumLength`, `maximumLength`, `spacesAllowed`, `requiresCharacterMix`, `scheduledRotation` |
| [PasswordReset](../backend/contracts/openapi.json#L5602) | `passwordReset`, `signedOut` |
| [PayCycle](../backend/contracts/openapi.json#L5623) | `key`, `start`, `end`, `payout` |
| [PayRecord](../backend/contracts/openapi.json#L5655) | `cycle`, `trainerId`, `trainerName`, `rows`, `sessions`, `totalSessions`, `minutes`, `amountCents`, `reviewCount`, `closed`, `status`, `revision` |
| [PayRow](../backend/contracts/openapi.json#L5773) | `sessionId`, `source`, `clientId`, `clientName`, `clientType`, `date`, `from`, `to`, `durationMinutes`, `status`, `billable`, `band`, `amountCents`, `issues` |
| [PaySaved](../backend/contracts/openapi.json#L5873) | `id`, `trainerId`, `cycle`, `revision`, `approvedAt` |
| [PayView](../backend/contracts/openapi.json#L5910) | `key`, `cycle`, `isCurrent`, `trainers` |
| [PendingEmail](../backend/contracts/openapi.json#L5941) | `change` |
| [PersonAssessmentRecords](../backend/contracts/openapi.json#L5961) | `id`, `version`, `records` |
| [PersonDetails](../backend/contracts/openapi.json#L5989) | `id`, `expectedVersion`, `name`, `email`, `birthday`, `gender`, `phone`, `emergencyContact` |
| [PersonNote](../backend/contracts/openapi.json#L6068) | `id`, `version`, `healthNotes` |
| [PersonSummary](../backend/contracts/openapi.json#L6093) | `id`, `version`, `position`, `name`, `birthday` |
| [PersonVersion](../backend/contracts/openapi.json#L6136) | `id`, `version` |
| [PersonalMessage](../backend/contracts/openapi.json#L6156) | `id`, `version`, `read`, `readAt`, `recipientUserId`, `kind`, `title`, `body`, `createdAt`, `actorId`, `actorName`, `clientId`, `purchaseId`, `sessionId`, `trainerId`, `requestId`, `exerciseId`, `packageId`, `contentId`, `remunerationCycle`, `request`, `renewalStatus`, `renewalDismissal` |
| [Phone](../backend/contracts/openapi.json#L6410) | `countryCode`, `number` |
| [PlanCopied](../backend/contracts/openapi.json#L6442) | `sessionId`, `version`, `items`, `savedAt`, `copiedFromSessionId` |
| [PlanDetail](../backend/contracts/openapi.json#L6482) | `id`, `value` |
| [PlanItem](../backend/contracts/openapi.json#L6505) | `id`, `name`, `weight`, `reps`, `rounds`, `rest`, `customDetails` |
| [PlanReview](../backend/contracts/openapi.json#L6561) | `sessionId`, `version`, `expected`, `items` |
| [PlanSaved](../backend/contracts/openapi.json#L6594) | `sessionId`, `version`, `items`, `savedAt` |
| [PostponeSession](../backend/contracts/openapi.json#L6628) | `expected` |
| [PostponementReview](../backend/contracts/openapi.json#L6643) | `id`, `version`, `expected`, `outcome`, `session` |
| [PostponementState](../backend/contracts/openapi.json#L6681) | `outcome`, `session`, `requestId`, `messageId`, `changedPositions` |
| [Preference](../backend/contracts/openapi.json#L6727) | `days`, `from`, `to` |
| [PreviousPlan](../backend/contracts/openapi.json#L6767) | `target`, `source` |
| [PreviousSource](../backend/contracts/openapi.json#L6791) | `sessionId`, `version`, `expected`, `items`, `date`, `startsAt` |
| [ProgressExercise](../backend/contracts/openapi.json#L6836) | `id`, `name`, `points` |
| [ProgressPoint](../backend/contracts/openapi.json#L6864) | `id`, `sessionId`, `packageId`, `date`, `load`, `reps`, `sets` |
| [PurchaseLabel](../backend/contracts/openapi.json#L6912) | `id`, `version`, `status`, `name` |
| [PurchaseReview](../backend/contracts/openapi.json#L6947) | `id`, `version`, `status` |
| [RateState](../backend/contracts/openapi.json#L6977) | `id`, `version` |
| [RateValues](../backend/contracts/openapi.json#L6998) | `peak`, `offPeak` |
| [ReactivateTrainer](../backend/contracts/openapi.json#L7021) | `expectedVersion`, `expectedAccountId`, `expectedAccountVersion` |
| [ReactivationDates](../backend/contracts/openapi.json#L7062) | `expected`, `dates` |
| [ReactivationReview](../backend/contracts/openapi.json#L7090) | `id`, `version`, `accountId`, `accountVersion` |
| [ReactivationState](../backend/contracts/openapi.json#L7137) | `id`, `version` |
| [ReadLease](../backend/contracts/openapi.json#L7164) | `url`, `sha256`, `size`, `type`, `version` |
| [Ready](../backend/contracts/openapi.json#L7198) | `status` |
| [RecordingIntent](../backend/contracts/openapi.json#L7213) | `key`, `state`, `uploadUntil`, `result` |
| [RecordingMedia](../backend/contracts/openapi.json#L7255) | `id`, `name`, `type`, `size`, `attachedAt`, `expiresAt` |
| [RecordingReview](../backend/contracts/openapi.json#L7297) | `sessionId`, `exerciseId`, `version`, `expected`, `media` |
| [RecordingSaved](../backend/contracts/openapi.json#L7339) | `sessionId`, `exerciseId`, `version`, `savedAt`, `media` |
| [RecordingUpload](../backend/contracts/openapi.json#L7382) | `name`, `type`, `size`, `sha256` |
| [RecoveryStarted](../backend/contracts/openapi.json#L7421) | `message` |
| [Refreshed](../backend/contracts/openapi.json#L7435) | `refreshed`, `accessExpiresAt`, `expiresAt` |
| [RenewPackage](../backend/contracts/openapi.json#L7462) | `packageId`, `packageVersion`, `startDate`, `sessionsPerWeek`, `genderPreference`, `clientPreferences`, `expected`, `trainerId`, `trainerVersion`, `fixedWeeklySchedule` |
| [RenewalMatchRequest](../backend/contracts/openapi.json#L7544) | `packageId`, `packageVersion`, `startDate`, `sessionsPerWeek`, `genderPreference`, `clientPreferences`, `expected` |
| [RenewalPurchase](../backend/contracts/openapi.json#L7632) | `id`, `version`, `templateId`, `total`, `validityDays`, `sessionsPerWeek`, `startDate`, `endDate` |
| [RenewalReview](../backend/contracts/openapi.json#L7685) | `id`, `version`, `name`, `trainerId`, `genderPreference`, `expected`, `minimumStartDate`, `package`, `fixedWeeklySchedule`, `clientPreferences` |
| [RenewalSlot](../backend/contracts/openapi.json#L7753) | `day`, `from`, `to`, `id` |
| [RenewalState](../backend/contracts/openapi.json#L7794) | `id`, `renewalStatus`, `renewalDismissal` |
| [ReportAction](../backend/contracts/openapi.json#L7829) | `purchaseId`, `kind` |
| [ReportActor](../backend/contracts/openapi.json#L7854) | `id`, `name` |
| [ReportEvent](../backend/contracts/openapi.json#L7874) | `id`, `clientId`, `packageId`, `kind`, `at`, `by` |
| [RequestActor](../backend/contracts/openapi.json#L7929) | `id`, `name` |
| [RequestResolutionActor](../backend/contracts/openapi.json#L7949) | `id`, `name` |
| [ResetPassword](../backend/contracts/openapi.json#L7969) | `code`, `newPassword` |
| [ResolutionState](../backend/contracts/openapi.json#L7996) | `id`, `version`, `status`, `at`, `by` |
| [ResolveRequest](../backend/contracts/openapi.json#L8036) | `expectedVersion`, `decision` |
| [RetainedSession](../backend/contracts/openapi.json#L8060) | `id`, `version`, `purchaseId`, `trainerId`, `trainerName`, `scheduleState`, `originalDate`, `date`, `startsAt`, `endsAt`, `locked`, `error` |
| [SaveAcknowledgement](../backend/contracts/openapi.json#L8173) | `expected`, `method` |
| [SaveApprovals](../backend/contracts/openapi.json#L8227) | `expectedVersion`, `approvalNeeded` |
| [SaveAssessment](../backend/contracts/openapi.json#L8246) | `expectedVersion`, `answers`, `event` |
| [SaveAssignment](../backend/contracts/openapi.json#L8327) | `expected`, `trainerId` |
| [SaveAvailability](../backend/contracts/openapi.json#L8348) | `expectedVersion`, `slots` |
| [SaveClientDetails](../backend/contracts/openapi.json#L8372) | `expectedVersion`, `people`, `remarks`, `genderPreference` |
| [SaveClientWeeklySchedule](../backend/contracts/openapi.json#L8413) | `expected`, `slots` |
| [SaveContent](../backend/contracts/openapi.json#L8438) | `draft` |
| [SaveLibrary](../backend/contracts/openapi.json#L8475) | `name`, `category`, `status` |
| [SaveMessageRead](../backend/contracts/openapi.json#L8558) | `expectedVersion`, `read` |
| [SaveNotes](../backend/contracts/openapi.json#L8578) | `expectedVersion`, `patch` |
| [SaveOutcome](../backend/contracts/openapi.json#L8597) | `expected`, `trainerComments`, `measurements` |
| [SavePackage](../backend/contracts/openapi.json#L8627) | `draft` |
| [SavePackageAction](../backend/contracts/openapi.json#L8664) | `expected`, `operation` |
| [SavePlan](../backend/contracts/openapi.json#L8693) | `expected`, `items` |
| [SaveRates](../backend/contracts/openapi.json#L8718) | `expectedVersion`, `rates` |
| [SaveRecording](../backend/contracts/openapi.json#L8737) | `sessionId`, `exerciseId`, `expected`, `remove` |
| [SaveSessionBooking](../backend/contracts/openapi.json#L8827) | `expected`, `date`, `startsAt`, `endsAt`, `trainerId` |
| [SaveSummary](../backend/contracts/openapi.json#L8866) | `expected`, `summary` |
| [SaveTrainerDetails](../backend/contracts/openapi.json#L8888) | `expectedVersion`, `patch` |
| [ServerClock](../backend/contracts/openapi.json#L8907) | `serverAt`, `businessDate`, `timeZone` |
| [SessionAcknowledgementRead](../backend/contracts/openapi.json#L8934) | `id`, `sequence`, `method`, `signerName`, `signature`, `note`, `recordedAt`, `recordedBy` |
| [SessionActorRead](../backend/contracts/openapi.json#L9008) | `id`, `name` |
| [SessionBookingReview](../backend/contracts/openapi.json#L9028) | `id`, `version`, `clientId`, `clientVersion`, `purchaseId`, `purchaseVersion`, `expected`, `session`, `trainers` |
| [SessionBookingState](../backend/contracts/openapi.json#L9087) | `session`, `client`, `purchase`, `positions`, `messageId` |
| [SessionBootstrap](../backend/contracts/openapi.json#L9129) | `csrfToken`, `expiresAt` |
| [SessionCalendar](../backend/contracts/openapi.json#L9149) | `viewerId`, `sessions`, `clients`, `trainers`, `purchases` |
| [SessionChangeReview](../backend/contracts/openapi.json#L9196) | `id`, `version`, `clientId`, `clientVersion`, `purchaseId`, `purchaseVersion`, `expected`, `session`, `trainers`, `kind`, `outcome` |
| [SessionChangeState](../backend/contracts/openapi.json#L9273) | `kind`, `outcome`, `session`, `requestId`, `messageId` |
| [SessionClient](../backend/contracts/openapi.json#L9330) | `session_id`, `client_id`, `name`, `kind`, `person_names` |
| [SessionClientLabel](../backend/contracts/openapi.json#L9373) | `id`, `name`, `kind`, `status` |
| [SessionDetailRead](../backend/contracts/openapi.json#L9411) | `session`, `client`, `trainer`, `purchase`, `exercisePlan`, `retiredPlanItemIds`, `exerciseResults`, `acknowledgementHistory`, `trainerComments`, `clientSummary`, `whatsappOpenedAt`, `whatsappOpenCount` |
| [SessionInfo](../backend/contracts/openapi.json#L9497) | `user`, `csrfToken`, `expiresAt`, `accessExpiresAt` |
| [SessionPlanDetailRead](../backend/contracts/openapi.json#L9527) | `id`, `value` |
| [SessionPlanRead](../backend/contracts/openapi.json#L9546) | `id`, `version`, `name`, `weight`, `reps`, `rounds`, `rest`, `notes`, `customDetails`, `videoAttached` |
| [SessionPurchaseLabel](../backend/contracts/openapi.json#L9609) | `id`, `clientId`, `trainerId`, `name`, `status`, `stage`, `total`, `used`, `validityDays`, `startDate`, `endDate` |
| [SessionResultRead](../backend/contracts/openapi.json#L9687) | `id`, `planItemId`, `name`, `loadKg`, `reps`, `sets` |
| [SessionSignaturePoint](../backend/contracts/openapi.json#L9735) | `x`, `y` |
| [SessionSummary](../backend/contracts/openapi.json#L9754) | `id`, `version`, `client_id`, `purchase_id`, `trainer_id`, `schedule_state`, `training_date`, `starts_at`, `ends_at`, `status` |
| [SessionTrainerLabel](../backend/contracts/openapi.json#L9851) | `id`, `name`, `status` |
| [SignIn](../backend/contracts/openapi.json#L9880) | `email`, `password` |
| [SignOut](../backend/contracts/openapi.json#L9905) | No required fields; inspect optional fields |
| [SignedIn](../backend/contracts/openapi.json#L9917) | `user`, `csrfToken`, `expiresAt` |
| [SignedOut](../backend/contracts/openapi.json#L9941) | `signedOut` |
| [Staff](../backend/contracts/openapi.json#L9956) | `id`, `name`, `email`, `role`, `trainerId` |
| [SummaryReview](../backend/contracts/openapi.json#L10004) | `sessionId`, `version`, `expected`, `summary` |
| [SummarySaved](../backend/contracts/openapi.json#L10034) | `sessionId`, `version`, `summary`, `savedAt` |
| [TrainerApprovalDefaults](../backend/contracts/openapi.json#L10065) | No required fields; inspect optional fields |
| [TrainerCreated](../backend/contracts/openapi.json#L10096) | `id`, `invitation` |
| [TrainerDeactivationChoice](../backend/contracts/openapi.json#L10122) | `id`, `name`, `version`, `error` |
| [TrainerDeactivationReview](../backend/contracts/openapi.json#L10159) | `id`, `version`, `name`, `accountId`, `accountVersion`, `expected`, `sessions` |
| [TrainerDeactivationSelection](../backend/contracts/openapi.json#L10223) | `expected`, `replacements` |
| [TrainerDeactivationSession](../backend/contracts/openapi.json#L10251) | `id`, `version`, `clientId`, `clientName`, `purchaseId`, `trainerId`, `scheduleState`, `date`, `startsAt`, `endsAt`, `choices` |
| [TrainerDeactivationState](../backend/contracts/openapi.json#L10348) | `id`, `version` |
| [TrainerDefaultRates](../backend/contracts/openapi.json#L10374) | No required fields; inspect optional fields |
| [TrainerMatch](../backend/contracts/openapi.json#L10393) | `trainerId`, `trainerVersion`, `matches`, `total`, `schedule` |
| [TrainerOnboardingPolicy](../backend/contracts/openapi.json#L10431) | No required fields; inspect optional fields |
| [TrainerProfilePatch](../backend/contracts/openapi.json#L10444) | No required fields; inspect optional fields |
| [TrainerProfilePolicy](../backend/contracts/openapi.json#L10543) | No required fields; inspect optional fields |
| [TrainerSummary](../backend/contracts/openapi.json#L10576) | `id`, `version`, `name`, `status` |
| [UndoChange](../backend/contracts/openapi.json#L10610) | `expected` |
| [UndoPackageDeletion](../backend/contracts/openapi.json#L10625) | `expected` |
| [UndoReview](../backend/contracts/openapi.json#L10640) | `id`, `messageId`, `expected`, `expiresAt`, `count` |
| [UndoSaved](../backend/contracts/openapi.json#L10677) | `id`, `actionId`, `status`, `undoneAt` |
| [UploadEvidence](../backend/contracts/openapi.json#L10710) | `name`, `type`, `size`, `sha256` |
| [UploadLease](../backend/contracts/openapi.json#L10752) | `url`, `headers` |
| [WeeklySavedClient](../backend/contracts/openapi.json#L10774) | `id`, `version` |

### Updating a contract

Change the owning route/schema/domain and browser service together; preserve [business invariants](business-rules.md) and stable operation names. Update the generated OpenAPI snapshot through its existing verification owner, refresh this index and the affected matrix evidence links, and run meaningful backend plus real-API browser coverage. Keep detailed change decisions and failures in [Journey](journey.md); a schema change alone is not source acceptance or deployment.
