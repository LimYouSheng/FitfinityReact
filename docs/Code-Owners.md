# Code owners and feature map

Snapshot: **28 October 2026**, based on main `1246fb815b1240a92fd953b85abc05f18f46bc73`. “Owner” means the module responsible for a behavior, not a person or GitHub review assignment. Start with the overview and follow numbered sections into smaller diagrams and linked source files. Arrows show responsibility breakdown unless explicitly labelled as request/data flow; this is not an exhaustive import graph or execution sequence.

This document owns code navigation. [System topology](Architecture/diagram.md) owns infrastructure/test topology, [Architecture](Architecture/README.md) explains runtime relationships, and [Service Contracts](SERVICE_CONTRACTS.md) owns business rules and the 55-operation matrix. [Progress](../PROGRESS.md) owns acceptance and planned work; [Versions](../Versions.md) owns dependency versions. Update this map when responsibilities move. Source ownership does not establish deployed/provider/device acceptance.

Format reference: [SoccerBotStudioSG Code Owners](https://github.com/LimYouSheng/SoccerBotStudioSG/blob/feat/version-inventory/docs/Code-Owners.md). Fitfinity retains its own React/FastAPI/PostgreSQL/Cognito boundaries.

## 1. Overview

```mermaid
flowchart TB
App["Fitfinity staff portal"]
  App --> UI["2 · Staff experience and navigation<br/>src/App.jsx + src/features"]
  App --> Client["3 · Browser services and recovery<br/>src/services + src/app"]
  App --> Server["4 · HTTP entry and authentication<br/>backend/app/main.py + auth + api"]
  Server --> People["5 · Clients, Trainers and packages"]
  Server --> Sessions["6 · Sessions, plans and completion"]
  Server --> Ops["7 · Messages, requests and remuneration"]
  Server --> Media["8 · Assessments, reports and media"]
  Server --> Data["9 · Persistence and diagnostics"]
  App --> Delivery["10 · Verification and delivery<br/>scripts + workflows + infrastructure"]
```

Navigation: [UI](#2-staff-experience-and-navigation) · [Services](#3-browser-contracts-and-recovery) · [Server/auth](#4-server-entry-and-identity) · [People/packages](#5-clients-trainers-and-packages) · [Sessions](#6-session-workflows) · [Operations](#7-messages-requests-and-remuneration) · [Records/media](#8-assessments-reports-and-media) · [Storage](#9-persistence-and-diagnostics) · [Delivery](#10-verification-and-delivery) · [Rule index](#11-business-rule-to-owner-index).

## 2. Staff experience and navigation

```mermaid
flowchart TB
Entry["src/main.jsx · React mount"]
  Entry --> App["App.jsx · page composition and shared recovery surfaces"]
  App --> Shell["components/AppShell.jsx<br/>Shared staff shell"]
  App --> Nav["hooks/useAppNavigation.js<br/>Selected page and record navigation"]
  App --> State["components/PortalDataProvider.jsx<br/>Snapshot, session and creation state"]
  App --> Routes["2.1 · Feature route owners"]
  App --> Guard["ActionConfirmationProvider + EditGuardProvider<br/>Reviewed actions and unsaved navigation"]
  App --> Account["features/account<br/>Sign-in, password and account screens"]
```

Source owners: [mount](../src/main.jsx), [composition](../src/App.jsx), [shell](../src/components/AppShell.jsx), [navigation](../src/hooks/useAppNavigation.js), [portal state](../src/components/PortalDataProvider.jsx), [confirmation](../src/components/ActionConfirmationProvider.jsx), [edit guard](../src/components/EditGuardProvider.jsx).

The provider owns shared snapshots and session lifetime. Feature editors own their drafts. Confirmation ownership is distinct from navigation/discard ownership; closing a dialog cannot undo a command already sent. Notifications and shared form/modal primitives live in `src/components`; visual styles live in [styles.css](../src/styles.css).

### 2.1 Feature route expansion

```mermaid
flowchart TB
Routes["Feature route owners under src/features"]
  Routes --> Client["clients/ClientProfileRoute.jsx<br/>Client detail and API/demo composition"]
  Routes --> Trainer["trainers/TrainerProfileRoute.jsx<br/>Trainer detail and API/demo composition"]
  Routes --> Sessions["sessions/SessionsRoute.jsx<br/>List, permitted detail and pending recovery"]
  Sessions --> Detail["sessions/SessionDetailsRoute.jsx<br/>Demo detail orchestration"]
  Sessions --> API["sessions/ApiSessionDetailsRoute.jsx<br/>Fetch, refresh, selection and draft lifetime"]
  API --> View["sessions/SessionDetailsPage.jsx<br/>Detail panels and editor presentation"]
  Routes --> Pay["remuneration/ApiRemunerationRoute.jsx<br/>Server-backed remuneration"]
  Routes --> Other["DashboardPage / MessagesPage / PackagesPage<br/>ExerciseLibraryPage / ApiContentWorkspace"]
```

Source owners: [client route](../src/features/clients/ClientProfileRoute.jsx), [Trainer route](../src/features/trainers/TrainerProfileRoute.jsx), [sessions route](../src/features/sessions/SessionsRoute.jsx), [demo detail](../src/features/sessions/SessionDetailsRoute.jsx), [API detail lifecycle](../src/features/sessions/ApiSessionDetailsRoute.jsx), [detail UI](../src/features/sessions/SessionDetailsPage.jsx), [remuneration route](../src/features/remuneration/ApiRemunerationRoute.jsx), [content workspace](../src/features/content/ApiContentWorkspace.jsx).

## 3. Browser contracts and recovery

```mermaid
flowchart TB
Config["defaultPortalServices.js<br/>Configured API or demo selection"]
  Config --> Boundary["portalService.js + portalContracts.js<br/>Named operation facade and input contracts"]
  Boundary --> API["apiPortalAdapter.js<br/>Compose domain commands and snapshot reads"]
  Boundary --> Demo["mockPortalAdapter.js + mockPortalOperations.js<br/>Prototype/demo behavior"]
  API --> Domains["apiClient*, apiTrainer*, apiSession* and other api*.js<br/>DTO validation and feature commands"]
  Domains --> Command["3.1 · apiCommand.js<br/>Matching command recovery lifecycle"]
  API --> HTTP["apiClient.js<br/>HTTP, cookies, CSRF and login generation"]
  Boundary --> Report["reportService.js<br/>Browser print and download boundary"]
```

Source owners: [configuration](../src/services/defaultPortalServices.js), [facade](../src/services/portalService.js), [contracts](../src/services/portalContracts.js), [API composition](../src/services/apiPortalAdapter.js), [transport](../src/services/apiClient.js), [shared command](../src/services/apiCommand.js), [demo adapter](../src/services/mockPortalAdapter.js), [browser reports](../src/services/reportService.js).

API domain modules retain specialized review/recovery semantics where needed; they do not all use one identical lifecycle. `src/app` owns pure browser rules/projections (permissions, schedules, packages, progress, remuneration and assessments). These support UI and demo behavior; server checks remain authoritative. The service matrix owns operation coverage, not this diagram.

### 3.1 Command and editor recovery expansion

```mermaid
flowchart TB
Edit["Feature editor · draft and reviewed values"]
  Edit --> Review["useReviewLifetime.js + ActionConfirmationProvider<br/>Keep review bound to its caller"]
  Review --> Command["apiCommand.js / specialized api*.js<br/>Original body, key and login generation"]
  Command --> Unknown["Feature Recovery components<br/>Present pending or uncertain outcome"]
  Unknown --> Check["reconcile / receipt read<br/>Check without creating a new write"]
  Unknown --> Retry["Explicit retry<br/>Reconcile before reusing original command"]
  Command --> Refresh["Feature route + PortalDataProvider<br/>Refresh after a known commit"]
  Refresh --> Failed["Keep committed status on read failure<br/>Do not turn refresh into a new save"]
```

Source owners: [review lifetime](../src/hooks/useReviewLifetime.js), [shared command](../src/services/apiCommand.js), [profile recovery](../src/services/apiProfileRecovery.js), [profile recovery UI](../src/components/ProfileSaveRecovery.jsx), [plan recovery](../src/features/sessions/SessionPlanRecovery.jsx), [media commands](../src/services/apiSessionMedia.js), [snapshot owner](../src/components/PortalDataProvider.jsx).

This is a responsibility map, not a universal state machine. The [architecture lifecycle table](Architecture/README.md) explains retained editor boundaries. Receipt read, retry, refresh and authority retirement are distinct operations.

## 4. Server entry and identity

```mermaid
flowchart TB
Entry["main.py · create_app<br/>Lifespan, middleware, health and router composition"]
  Entry --> Auth["auth/routes.py + auth/service.py<br/>Login, challenges, refresh and logout"]
  Auth --> Provider["auth/cognito.py + auth/jwt.py + auth/security.py<br/>Provider, token verification and session security"]
  Entry --> Staff["api/routes.py<br/>Most staff-domain HTTP registration"]
  Entry --> Extra["Separate staff, email, library, package-action,<br/>session-media and Undo routers"]
  Staff --> Gate["api/dependencies.py + authorization.py<br/>Principal and authorized transaction"]
  Gate --> Domains["Sections 5–8 · domain review / save / receipt logic"]
  Entry --> Health["database.py + migrations.py<br/>Database and expected schema readiness"]
```

Source owners: [app entry](../backend/app/main.py), [staff routes](../backend/app/api/routes.py), [transaction boundary](../backend/app/api/dependencies.py), [authorization](../backend/app/authorization.py), [auth routes](../backend/app/auth/routes.py), [auth service](../backend/app/auth/service.py), [Cognito](../backend/app/auth/cognito.py), [JWT verification](../backend/app/auth/jwt.py), [request auth middleware](../backend/app/auth/middleware.py).

`api/routes.py` still registers many domains; the earlier broad domain-router extraction is not merged and is not shown as implemented. Authenticated API registration is controlled by app configuration. Client capabilities and hidden buttons do not authorize writes.

### 4.1 Staff account expansion

```mermaid
flowchart TB
Account["Staff identity and lifecycle"]
  Account --> UI["features/account + TrainerEmailEditor.jsx<br/>Login, password and verified email UI"]
  Account --> Invite["api/staff.py + staff_provisioning.py<br/>Staff account provisioning"]
  Invite --> Cognito["auth/invitations.py<br/>Cognito invitation boundary"]
  Account --> Email["api/email_changes.py<br/>New-address verification and reconciliation"]
  Account --> Session["auth/service.py + models/authentication.py<br/>Session and challenge evidence"]
  Account --> Recovery["README operator-assisted recovery procedure<br/>Identity checks, audited per-user action and re-enrollment"]
```

Source owners: [staff API](../backend/app/api/staff.py), [provisioning](../backend/app/api/staff_provisioning.py), [invitation adapter](../backend/app/auth/invitations.py), [verified email](../backend/app/api/email_changes.py), [authentication records](../backend/app/models/authentication.py).

The [operator recovery procedure](../README.md#operator-assisted-lost-authenticator-recovery) is an operator-owned process with test drills, not an Owner-facing MFA-reset feature. Real Cognito actions remain separately authorized.

## 5. Clients, Trainers and packages

```mermaid
flowchart TB
People["People and package feature ownership"]
  People --> Clients["features/clients + services/apiClient*.js<br/>Profiles, onboarding, assignments and lifecycle"]
  Clients --> Server["api/client_creation.py, client_details.py, client_notes.py<br/>api/client_assignment* and client_deactivation.py"]
  People --> Trainers["features/trainers + services/apiTrainer*.js<br/>Profiles, availability, approvals and lifecycle"]
  Trainers --> TrainerServer["api/trainer_creation.py, trainer_details.py,<br/>trainer_availability.py, trainer_approvals.py, trainer_rates.py"]
  People --> Packages["5.1 · Purchase and package lifecycle"]
  People --> Data["models/people.py + staff.py + training.py<br/>People, staff and purchased/session records"]
```

Source owners: [client profile](../src/features/clients/ClientProfilePage.jsx), [onboarding](../src/features/clients/ClientOnboardingForm.jsx), [client reassignment](../src/features/clients/ApiClientAssignmentButton.jsx), [Trainer profile](../src/features/trainers/TrainerProfilePage.jsx), [availability editor](../src/features/trainers/TrainerAvailabilityEditor.jsx), [Trainer deactivation](../src/features/trainers/TrainerDeactivationDialog.jsx), [package definitions](../src/features/setup/PackagesPage.jsx).

Source owners: [client create](../backend/app/api/client_creation.py), [client edit](../backend/app/api/client_details.py), [assignment review](../backend/app/api/client_assignment.py), [assignment save](../backend/app/api/client_assignment_save.py), [Trainer creation](../backend/app/api/trainer_creation.py), [Trainer availability](../backend/app/api/trainer_availability.py), [Trainer deactivation review](../backend/app/api/trainer_deactivation.py), [Trainer deactivation save](../backend/app/api/trainer_deactivation_save.py), [Trainer reactivation](../backend/app/api/trainer_reactivation.py).

### 5.1 Purchase and package lifecycle expansion

```mermaid
flowchart TB
Purchase["Client purchase and package lifecycle"]
  Purchase --> Definition["api/packages.py<br/>Package definition save/read"]
  Purchase --> Create["purchase_creation.py + purchase_activation.py<br/>Purchased terms and activation"]
  Purchase --> Renew["client_renewal.py + client_renewal_save.py<br/>Review and apply renewal"]
  Purchase --> Status["client_deactivation.py + client_reactivation*.py<br/>Client lifecycle"]
  Purchase --> Action["package_action_routes.py<br/>Review, save and reconcile package commands"]
  Action --> Apply["package_action_review.py + package_action_save.py<br/>Deactivation / deletion decisions"]
  Action --> Restore["package_reactivation_save.py + package_action_undo.py<br/>Reactivation and eligible restoration"]
  Apply --> Evidence["models/package_actions.py<br/>Retained deletion and action evidence"]
```

Source owners: [definitions](../backend/app/api/packages.py), [purchase create](../backend/app/api/purchase_creation.py), [activation](../backend/app/api/purchase_activation.py), [renewal save](../backend/app/api/client_renewal_save.py), [package routes](../backend/app/api/package_action_routes.py), [package review](../backend/app/api/package_action_review.py), [package save](../backend/app/api/package_action_save.py), [reactivation](../backend/app/api/package_reactivation_save.py), [package Undo](../backend/app/api/package_action_undo.py).

## 6. Session workflows

```mermaid
flowchart TB
Session["Sessions feature"]
  Session --> UI["SessionsPage + SessionDetailsPage<br/>List, calendar context and detail panels"]
  Session --> Read["apiSessionReads.js → api/session_reads.py<br/>Scoped calendar and detail reads"]
  Session --> Schedule["6.1 · Booking and schedule mutations"]
  Session --> Plan["6.2 · Exercise plans and Copy Previous Plan"]
  Session --> Finish["6.3 · Outcomes, summaries, acknowledgement and credits"]
  Session --> Media["8.1 · Protected session recordings"]
  Session --> Attribution["api/session_attribution.py + models/session_attribution.py<br/>Original, assigned and performed Trainer evidence"]
```

Source owners: [session list](../src/features/sessions/SessionsPage.jsx), [session details](../src/features/sessions/SessionDetailsPage.jsx), [schedule interaction](../src/features/sessions/useSessionSchedule.js), [change dialogs](../src/features/sessions/SessionChangeDialogs.jsx).

Source owners: [session reads](../backend/app/api/session_reads.py), [attribution](../backend/app/api/session_attribution.py).

### 6.1 Booking and schedule expansion

```mermaid
flowchart TB
Schedule["Server schedule ownership under backend/app"]
  Schedule --> Booking["api/session_booking_review.py + session_booking_save.py<br/>Inspect and apply fixed/open session changes"]
  Schedule --> Requests["api/session_changes.py<br/>Time and Trainer change requests"]
  Schedule --> Postpone["api/session_postponement.py<br/>Postponement review and mutation"]
  Schedule --> Weekly["api/client_weekly_schedule.py + client_weekly_schedule_save.py<br/>Weekly schedule edits / proposals"]
  Schedule --> Availability["api/trainer_availability.py<br/>Availability validation and writes"]
  Booking --> Order["session_numbering.py + purchase_schedule.py<br/>Stable identities and schedule construction"]
  Requests --> Decision["7.1 · Request application and resolution"]
```

Source owners: [booking review](../backend/app/api/session_booking_review.py), [booking save](../backend/app/api/session_booking_save.py), [change requests](../backend/app/api/session_changes.py), [postponement](../backend/app/api/session_postponement.py), [weekly review](../backend/app/api/client_weekly_schedule.py), [weekly save](../backend/app/api/client_weekly_schedule_save.py), [numbering](../backend/app/session_numbering.py), [purchase schedule](../backend/app/purchase_schedule.py).

### 6.2 Exercise plan expansion

```mermaid
flowchart TB
UI["ExercisePlanEditor.jsx · ordered prescription editing"]
  UI --> Copy["PreviousPlanDialog.jsx<br/>Preview and confirm replacement"]
  UI --> Client["apiSessionPlans.js<br/>Review, save, copy and recovery commands"]
  Client --> Server["api/session_plans.py<br/>review / save / previous / copy_previous"]
  Server --> Apply["apply_plan<br/>Current authority, versions and stable detail identities"]
  Apply --> Store["models/training.py + command receipts<br/>Typed plan rows and retained results/media references"]
```

Source owners: [plan UI](../src/features/sessions/ExercisePlanEditor.jsx), [previous-plan confirmation](../src/features/sessions/PreviousPlanDialog.jsx), [plan commands](../src/services/apiSessionPlans.js).

Source owners: [plan transaction](../backend/app/api/session_plans.py), [training models](../backend/app/models/training.py).

### 6.3 Completion and credit expansion

```mermaid
flowchart TB
Completion["Session completion responsibilities"]
  Completion --> Outcome["api/session_outcomes.py<br/>Results and reviewed corrections"]
  Outcome --> Progress["api/session_progress.py<br/>Persisted progress projection"]
  Completion --> Summary["api/session_summaries.py<br/>Client-facing summary save"]
  Summary --> Handoff["api/session_handoffs.py<br/>Record WhatsApp-open handoff evidence"]
  Completion --> Ack["api/session_acknowledgements.py<br/>Reviewed acknowledgement and credit accounting"]
  Ack --> Journal["models/training.py + evidence.py<br/>Durable session and audit/credit evidence"]
  Completion --> Export["SessionSummaryExport.jsx + sessionExport.jsx<br/>Browser presentation and export"]
```

Source owners: [outcomes](../backend/app/api/session_outcomes.py), [progress](../backend/app/api/session_progress.py), [summaries](../backend/app/api/session_summaries.py), [handoff](../backend/app/api/session_handoffs.py), [acknowledgement](../backend/app/api/session_acknowledgements.py).

Source owners: [summary export](../src/features/sessions/SessionSummaryExport.jsx), [export formatting](../src/features/sessions/sessionExport.jsx).

A recorded WhatsApp-open action is not proof of provider delivery or customer receipt. Completion and credit rules remain in the linked contract section below.

## 7. Messages, requests and remuneration

```mermaid
flowchart TB
Ops["Staff operations"]
  Ops --> Inbox["MessagesPage.jsx + apiMessages.js<br/>Inbox, recipient read/unread state"]
  Inbox --> Server["api/messages.py + renewal_dismissal.py<br/>Scoped messages and personal renewal dismissal"]
  Ops --> Decisions["7.1 · Request decisions and permitted Undo"]
  Ops --> Pay["ApiRemunerationRoute.jsx + apiRemuneration.js<br/>Cycle/detail reads and approval UI"]
  Pay --> Payroll["api/remuneration.py + remuneration_schemas.py<br/>Server calculation and approval snapshot"]
  Ops --> Content["ApiContentWorkspace.jsx + apiContent.js<br/>Content management"]
  Content --> ContentServer["api/content.py<br/>Versioned content save/read"]
```

Source owners: [inbox](../src/features/messages/MessagesPage.jsx), [request review](../src/features/messages/RequestReview.jsx), [Undo UI](../src/features/messages/MessageUndo.jsx), [remuneration commands](../src/services/apiRemuneration.js), [content workspace](../src/features/content/ApiContentWorkspace.jsx).

Source owners: [message state](../backend/app/api/messages.py), [renewal dismissal](../backend/app/api/renewal_dismissal.py), [remuneration](../backend/app/api/remuneration.py), [content](../backend/app/api/content.py).

### 7.1 Decisions and Undo expansion

```mermaid
flowchart TB
Decision["Request / Undo ownership under backend/app/api"]
  Decision --> Resolve["request_resolution.py<br/>Review decision and serialize resolution"]
  Resolve --> Apply["request_application.py<br/>Apply approved domain change"]
  Decision --> Cancel["request_cancellation.py<br/>Original requester cancellation"]
  Decision --> Undo["session_undo_routes.py<br/>Review / save / reconcile Undo"]
  Undo --> Check["session_undo_review.py<br/>Eligibility and unchanged dependency review"]
  Undo --> Save["session_undo_save.py<br/>Compensating transaction"]
  Save --> History["session_mutation_journal.py + models/session_mutations.py<br/>Typed snapshots and durable mutation evidence"]
  Decision --> Package["package_action_undo.py<br/>Package-specific restoration rules"]
```

Source owners: [resolve](../backend/app/api/request_resolution.py), [apply](../backend/app/api/request_application.py), [cancel](../backend/app/api/request_cancellation.py), [Undo routes](../backend/app/api/session_undo_routes.py), [Undo review](../backend/app/api/session_undo_review.py), [Undo save](../backend/app/api/session_undo_save.py), [mutation journal](../backend/app/api/session_mutation_journal.py).

## 8. Assessments, reports and media

```mermaid
flowchart TB
Records["Client records and exercise library"]
  Records --> Assess["ClientAssessmentWorkspace + AssessmentRecordDialog + AssessmentHistoryDialog<br/>Draft, fill and history UI"]
  Assess --> API["apiAssessments.js + apiAssessmentRecords.js<br/>Assessment contracts and transport"]
  API --> Server["api/assessments.py<br/>Assessment route operations"]
  Server --> Rules["assessment_validation.py + assessment_persistence.py<br/>Answer validation and durable revisions"]
  Records --> Notes["useClientNotes.js → apiClientNotes.js → api/client_notes.py<br/>General health notes, separate authority from initial forms"]
  Records --> Reports["apiProgressReports.js → api/session_reports.py<br/>Report-action history"]
  Records --> Render["progressReportPdf.jsx + utils/reportPdf.js<br/>Browser document generation"]
  Records --> Media["8.1 · Protected library and session media"]
```

Source owners: [assessment workspace](../src/features/clients/ClientAssessmentWorkspace.jsx), [assessment form definitions](../src/app/assessmentForms.js), [assessment history](../src/features/clients/AssessmentHistoryDialog.jsx), [general notes](../src/features/clients/useClientNotes.js), [report PDF](../src/features/clients/progressReportPdf.jsx), [report history commands](../src/services/apiProgressReports.js).

Source owners: [assessment operations](../backend/app/api/assessments.py), [answer validation](../backend/app/assessment_validation.py), [revision persistence](../backend/app/assessment_persistence.py), [notes authorization](../backend/app/api/client_notes.py), [report actions](../backend/app/api/session_reports.py).

### 8.1 Media expansion

```mermaid
flowchart TB
Media["Protected original media ownership"]
  Media --> LibraryUI["ExerciseLibraryPage + ExerciseLibraryMedia<br/>Library metadata and media UI"]
  Media --> VideoUI["ExerciseVideoDialog.jsx + apiSessionMedia.js<br/>Session recording interaction"]
  LibraryUI --> Library["api/library_routes.py + exercise_library.py<br/>Reserve, verify and publish library media"]
  VideoUI --> Recording["api/session_media_routes.py + session_media.py<br/>Reserve, commit and authorize session media"]
  Library --> Storage["media_storage.py<br/>Configured object-storage adapter"]
  Recording --> Storage
  Media --> Cleanup["library_cleanup.py + session_media_cleanup.py<br/>Durable cleanup processing"]
  Media --> Evidence["models/media.py + session_media.py<br/>Private media intents, attachments and retention evidence"]
```

Source owners: [library UI](../src/features/exercises/ExerciseLibraryPage.jsx), [library transport](../src/services/apiLibraryMedia.js), [video dialog](../src/features/sessions/ExerciseVideoDialog.jsx), [recording transport](../src/services/apiSessionMedia.js).

Source owners: [library routes](../backend/app/api/library_routes.py), [library operations](../backend/app/api/exercise_library.py), [recording routes](../backend/app/api/session_media_routes.py), [recording operations](../backend/app/api/session_media.py), [storage adapter](../backend/app/media_storage.py), [library cleanup](../backend/app/library_cleanup.py), [recording cleanup](../backend/app/session_media_cleanup.py).

Cleanup code ownership does not mean cloud worker scheduling, transcoding or captions are deployed. M7 processing and rollout remain in Progress. Isolated tests use real RustFS object IO; production object storage is the separately configured S3 boundary.

## 9. Persistence and diagnostics

```mermaid
flowchart TB
Data["backend/app · durable data and runtime support"]
  Data --> Connection["database.py + persistence.py<br/>Database access and persistence helpers"]
  Data --> Models["9.1 · models<br/>Typed relational state and evidence"]
  Data --> Schema["backend/migrations + app/migrations.py<br/>Forward schema changes and expected revisions"]
  Data --> Config["config.py + managed_secrets.py<br/>Validated settings and managed-secret loading"]
  Data --> Logs["observability.py<br/>Request IDs, structured logs, duration and error envelopes"]
  Data --> Future["Planned in Progress M10<br/>OpenTelemetry, Grafana, SLOs and operating drills"]
```

Source owners: [database](../backend/app/database.py), [persistence helpers](../backend/app/persistence.py), [schema readiness](../backend/app/migrations.py), [configuration](../backend/app/config.py), [managed secrets](../backend/app/managed_secrets.py), [request diagnostics](../backend/app/observability.py).

### 9.1 Model expansion

```mermaid
flowchart TB
Models["backend/app/models"]
  Models --> Identity["authentication.py + email_changes.py<br/>Sessions, identity and verification evidence"]
  Models --> People["people.py + staff.py<br/>Client and staff records"]
  Models --> Training["training.py + session_attribution.py<br/>Purchases, sessions, plans and Trainer attribution"]
  Models --> Records["assessments.py + media.py + session_media.py<br/>Assessment revisions and protected media"]
  Models --> Actions["api.py + evidence.py + session_mutations.py + package_actions.py<br/>Receipts, audit and compensating-action history"]
  Models --> Comms["communications.py<br/>Messages, requests and recipient state"]
```

Source owners: [authentication](../backend/app/models/authentication.py), [people](../backend/app/models/people.py), [staff](../backend/app/models/staff.py), [training](../backend/app/models/training.py), [attribution](../backend/app/models/session_attribution.py), [assessments](../backend/app/models/assessments.py), [receipts](../backend/app/models/api.py), [audit evidence](../backend/app/models/evidence.py), [communications](../backend/app/models/communications.py), [mutation history](../backend/app/models/session_mutations.py).

## 10. Verification and delivery

```mermaid
flowchart TB
Delivery["Repository verification and release"]
  Delivery --> Gates["10.1 · Three required CI gates"]
  Delivery --> Demo["pages.yml<br/>Main verification and Pages demo publishing"]
  Delivery --> Image["aws-image.yml + backend/infrastructure<br/>Manual exact-source image publication and scan"]
  Delivery --> Runtime["aws-image-accept.yml + aws-private-runtime.yml<br/>Separately authorized image/runtime acceptance"]
  Delivery --> Hosting["aws-test-hosting.yml<br/>Separately authorized frontend hosting work"]
  Delivery --> Dependencies["dependabot.yml + Versions.md<br/>Dependency proposals and manual lookup"]
  Delivery --> Future["Progress M10 backlog<br/>Mutation, measured latency, SBOM and recovery drills"]
```

Source owners: [verification](../.github/workflows/verify.yml), [demo publication](../.github/workflows/pages.yml), [image publication](../.github/workflows/aws-image.yml), [image acceptance](../.github/workflows/aws-image-accept.yml), [private runtime](../.github/workflows/aws-private-runtime.yml), [frontend hosting](../.github/workflows/aws-test-hosting.yml).

Release scripts and resource reconciliation live in [backend/infrastructure](../backend/infrastructure); [backend/Dockerfile](../backend/Dockerfile) owns separate application/test/runtime stages. Normal source merges do not authorize AWS publication or Lambda deployment. Planned M10 work has no implied implemented module owner.

### 10.1 Verification expansion

```mermaid
flowchart TB
CI["verify.yml · required gates"]
  CI --> Front["frontend · macOS<br/>Lint, audit, units, simulator browser suites and source health"]
  Front --> FOwners["src/**/*.test.* + tests<br/>verify-lint, verify-quality and verify-code-health scripts"]
  CI --> Back["backend · Docker<br/>Actual isolated PostgreSQL and infrastructure verification"]
  Back --> BOwners["verify-backend.mjs + backend/scripts + backend/tests<br/>Transactions, authority, migrations and recovery"]
  CI --> Browser["api-browser · two shards plus required aggregate<br/>Actual UI to FastAPI to PostgreSQL"]
  Browser --> Harness["verify-api-browser.mjs + backend/tests/browser_server.py<br/>Synthetic identity, real database and media isolation"]
  Browser --> Cases["tests-api + playwright.api.config.js<br/>UI persistence, scope, conflicts and interrupted writes"]
  Browser --> Aggregate["verify-api-shards.mjs<br/>Complete discovered inventory, no omitted cases"]
```

Source owners: [backend harness](../scripts/verify-backend.mjs), [browser harness](../scripts/verify-api-browser.mjs), [shard aggregate](../scripts/verify-api-shards.mjs), [quality gates](../scripts/verify-quality.mjs), [result inventory](../scripts/verify-test-results.mjs), [source health](../scripts/verify-code-health.mjs).

[Real-API browser cases](../tests-api), [backend tests](../backend/tests) and [browser server](../backend/tests/browser_server.py) own acceptance probes. Simulator tests are frontend evidence; synthetic Cognito is not live-provider acceptance. Physical-device, deployed-service and operational-drill evidence remain distinct.

## 11. Business rule to owner index

These links navigate to the existing contract sections; they do not duplicate or renumber business rules. Multiple modules can enforce different boundaries of the same rule. Consult the full linked rule before changing an owner.

| Contract topic | Diagram expansion | Main code owners |
| --- | --- | --- |
| [Service boundary](SERVICE_CONTRACTS.md#service-boundary) and [operation matrix](SERVICE_CONTRACTS.md#domain-operation-inventory) | 3 | [portalContracts.js](../src/services/portalContracts.js), [apiPortalAdapter.js](../src/services/apiPortalAdapter.js), [routes.py](../backend/app/api/routes.py) |
| [Authority and privacy](SERVICE_CONTRACTS.md#authority-and-privacy) | 4, 8 | [authorization.py](../backend/app/authorization.py), [dependencies.py](../backend/app/api/dependencies.py), [assessments.py](../backend/app/api/assessments.py), [client_notes.py](../backend/app/api/client_notes.py) |
| [Persistence, conflicts and recovery](SERVICE_CONTRACTS.md#persistence-conflicts-and-recovery) | 3.1, 9 | [apiCommand.js](../src/services/apiCommand.js), [apiClient.js](../src/services/apiClient.js), [dependencies.py](../backend/app/api/dependencies.py), domain-specific review/save owners above |
| [Product invariants](SERVICE_CONTRACTS.md#product-invariants) | 5.1, 6.1 | [purchase_creation.py](../backend/app/api/purchase_creation.py), [session_booking_save.py](../backend/app/api/session_booking_save.py), [session_numbering.py](../backend/app/session_numbering.py) |
| [Permitted Undo](SERVICE_CONTRACTS.md#permitted-undo) | 7.1 | [session_undo_review.py](../backend/app/api/session_undo_review.py), [session_undo_save.py](../backend/app/api/session_undo_save.py), [package_action_undo.py](../backend/app/api/package_action_undo.py) |
| [Acknowledgement and credits](SERVICE_CONTRACTS.md#reviewed-acknowledgement-and-credit-accounting) | 6.3 | [session_acknowledgements.py](../backend/app/api/session_acknowledgements.py), [training.py](../backend/app/models/training.py) |
| [Outcomes and progress](SERVICE_CONTRACTS.md#outcome-corrections-and-persisted-progress) | 6.3 | [session_outcomes.py](../backend/app/api/session_outcomes.py), [session_progress.py](../backend/app/api/session_progress.py) |
| [Summaries](SERVICE_CONTRACTS.md#client-facing-summaries) and [report history](SERVICE_CONTRACTS.md#report-actions-and-retained-history) | 6.3, 8 | [session_summaries.py](../backend/app/api/session_summaries.py), [session_handoffs.py](../backend/app/api/session_handoffs.py), [session_reports.py](../backend/app/api/session_reports.py) |
| [Authentication](SERVICE_CONTRACTS.md#authentication-and-additional-routes) | 4.1 | [auth/service.py](../backend/app/auth/service.py), [email_changes.py](../backend/app/api/email_changes.py); operator recovery remains a documented process |
| [Assessment policy](SERVICE_CONTRACTS.md#assessment-records-business-policy-and-retained-capacity-decisions) | 8 | [assessment_validation.py](../backend/app/assessment_validation.py), [assessment_persistence.py](../backend/app/assessment_persistence.py), [ClientAssessmentWorkspace.jsx](../src/features/clients/ClientAssessmentWorkspace.jsx) |
| [Deployment and acceptance](SERVICE_CONTRACTS.md#deployment-migration-and-acceptance) | 10 | [infrastructure](../backend/infrastructure), [workflows](../.github/workflows); operator authorization and live acceptance are not automated by a diagram |
