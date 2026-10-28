# Architecture decision records

Recorded: 28 October 2026. These records explain Fitfinity's stack, tradeoffs and evolution options. **Statuses distinguish implemented source, selected hosting and planned capabilities.** Rationale is reconstructed from current code and retained contracts; it does not claim that every alternative was historically benchmarked or rejected. Alternatives are review candidates, not approved migrations or ready standby systems.

[System topology and test diagrams](diagram.md) show connections; [code owners](../code-owners.md) maps implementation; [runbook](../runbook.md) owns operational procedures. Business rules remain in [Business Rules](../business-rules.md), API definitions in [API Contracts](../api-contracts.md), and full historical evidence in [Journey](../journey.md), versions in [the inventory](../versions.md), and current acceptance/backlog in [Progress](../../PROGRESS.md). Amend a decision explicitly or add a superseding ADR when assumptions change; retain its earlier rationale and evidence.

## Context and decision drivers

Fitfinity serves Owner, Admin and Trainer workflows for clients, purchased packages, schedules, plans, outcomes, assessments, credits, remuneration and protected media. Concurrent editors, lost responses and changing assignments must not corrupt durable evidence or reveal private health information. The initial eleven assessment forms remain Owner/Admin-only; assigned Trainers have separately permitted general health notes. The server owns current authorization and persistence.

The design prioritizes prototype parity, transactional correctness, maintainable domain ownership, isolated reproducible verification and a traceable AWS release path. The 55-operation source acceptance does not establish live deployment, real Cognito, current physical-device acceptance or unlimited capacity. Current platform limits/prices and measured demand must be reviewed before any scaling decision. No numeric latency or recovery guarantee is inferred from the stack.

## Decision summary

| ID | Choice | Status | Main benefit | Main tradeoff |
| --- | --- | --- | --- | --- |
| [ADR-001](#adr-001) | React/Vite and explicit service adapters | Implemented; live acceptance separate | Reusable UI/service boundary | Editor/recovery lifecycle complexity |
| [ADR-002](#adr-002) | Python FastAPI and a modular transactional backend | Implemented | Portable HTTP/domain separation | Two-language contracts and worker/query limits |
| [ADR-003](#adr-003) | PostgreSQL, SQLAlchemy/Alembic and durable command receipts | Implemented storage; managed-host acceptance separate | Atomic relational effects and evidence | Contention, connections and migration risk |
| [ADR-004](#adr-004) | Cognito identity with application-owned authorization | Implemented integration; real-provider acceptance separate | Managed authentication; explicit app authority | Provider and identity migration dependence |
| [ADR-005](#adr-005) | CloudFront, API Gateway and containerized Lambda on AWS | Selected topology; current-source deployment not established | Managed entry and container reuse | Cold starts, regional dependencies and DB limits |
| [ADR-006](#adr-006) | Private S3 media, immutable upload intents and durable cleanup | Source implemented; activation/processing acceptance separate | Private large-object storage | Database/object reconciliation |
| [ADR-007](#adr-007) | Layered verification with real isolated PostgreSQL | Existing suites implemented; mutation/performance expansion planned | Actual persistence and permission evidence | CI cost and external acceptance gaps |
| [ADR-008](#adr-008) | Verified revisions, separate AWS release and reviewed dependencies | Source workflow implemented; deployment evidence separate | Traceable source and controlled release | Gate time and incomplete update coverage |
| [ADR-009](#adr-009) | Allowlisted logs now; OpenTelemetry and Grafana planned | Structured request logs implemented; OTel/Grafana not implemented | Privacy-conscious diagnostic foundation | Planned correlation/alerts and ingestion costs |
| [ADR-010](#adr-010) | Explicit migration, restore and operational recovery boundaries | Selected approach; full operational drills and acceptance pending | Explicit state-preserving recovery | Restore complexity; drills still pending |

<a id="adr-001"></a>

## ADR-001 — React/Vite and explicit service adapters

**Status.** Implemented; live acceptance separate.

**Decision.** React/Vite renders the Owner, Admin and Trainer portal. Feature screens use injected asynchronous services; `PortalDataProvider` owns authorized snapshots and `useAppNavigation` owns account-scoped history. Explicit demo mode uses prototype data and browser storage. API mode uses `apiPortalAdapter` and FastAPI without falling back to mocks. GitHub Pages hosts the separate demo export. A session-scoped recovery panel above the routes exposes uncertain simple-form commands after their editors close; the adapter retains immutable intents and the server owns receipts.

UI drafts, submitted commands and post-save reads have separate lifetimes. The following maps the current implementation; [Business rules](../business-rules.md#current-business-rules) owns the business invariants. `SessionsRoute` selects the session list, permitted detail or pending recovery in the established acknowledgement → summary → outcome → plan → change order. It preserves session-record keys and login-generation recovery keys. `App` retains global navigation, authentication and profile recovery. `apiBackedWorkflows` identifies API orchestration; individual capabilities still gate writes.

| Transition | Implementation owner and retained behavior |
| --- | --- |
| Idle → opening review → editing | Feature control captures an enabled record lifetime through `useReviewLifetime`; a retired response cannot claim a later editor. This helper is shared only by the matching lifecycle controls. |
| Editing → same-scope refresh | `ApiSessionDetailsRoute` retains the reviewed detail while the editor is active. Ordinary version changes do not silently replace the draft; the server checks its reviewed version when saving. |
| Editing → authority/identity retired | Session selection/detail scope checks retire stale private state. A transient read failure can retain authorized detail; an access denial cannot. Scope rules remain feature-specific. |
| Editing → confirmation → continue/cancel | `ActionConfirmationProvider` binds each decision to its caller; replacement, unmount, session end or the caller’s abort retires that decision. `EditGuardProvider` owns navigation confirmation and unsaved-draft discard. |
| Confirmed → submitting → rejected/unknown/committed | Domain service adapters own the command. `reconciledCommand` is the shared owner for matching simple commands, retaining the original body, key and login generation; other domain adapters keep their specialized semantics. Closing UI does not undo a sent command. |
| Unknown → explicit Check / confirmed retry | Recovery reads the original receipt. Check never posts; an explicit retry may reuse the original immutable command only after reconciliation and current authority checks. Background snapshots expose pending work without consuming it. |
| Committed → refreshing → displayed / refresh failure | The feature retains successful-save status. A failed follow-up read offers refresh recovery, not another save. `ApiSessionDetailsRoute` owns this boundary for session details. |
| Session ended → UI retired | Login generation and authority guards remove old private UI/commands from the current session. This neither rolls back server commits nor claims recovery across browser restarts. |

Keep those owners separate when extracting routes. Regression evidence spans the confirmation/edit-guard tests, command/recovery tests, session-detail tests and real-API refresh, lost-response and permission scenarios; full CI remains the acceptance gate. The existing shared review guard does not replace record-specific draft retirement or transaction/receipt logic.

**Why it fits.** The staff portal needs rich forms, schedules and role-specific workflows while preserving the approved prototype. A static React frontend and asynchronous service boundary let the same feature screens use explicit demo or API composition without moving business authority into the browser.

**Pros.** Cacheable static assets, reusable feature components and explicit service contracts. Independent UI/domain tests make incremental API integration possible.

**Cons.** Client-side routing, draft lifetimes and uncertain saves require careful coordination. JavaScript does not provide TypeScript compile-time contract checks; runtime validation and meaningful tests remain necessary. Static assets alone cannot perform authenticated server work.

**Scaling / revisit trigger.** Measure bundle size, rendering and interaction latency before splitting features or changing frameworks. Extract route owners incrementally while preserving the lifecycle table above. Revisit server rendering for concrete public-site requirements, not merely more portal users.

**Alternative / contingency.** Next.js/server rendering could serve future content needs but adds deployment/runtime responsibilities. TypeScript adoption could strengthen static contracts through an incremental migration. Neither replaces API authorization or recovery. The Pages demo is never an operational fallback for persistent API writes.

**Owners/evidence.** [Frontend manifest](../../package.json), [service contracts](../../src/services/portalContracts.js), [portal data](../../src/components/PortalDataProvider.jsx), [session route](../../src/features/sessions/SessionsRoute.jsx), [BR-001](../business-rules.md#br-001), [BR-009–011](../business-rules.md#br-009).

<a id="adr-002"></a>

## ADR-002 — Python FastAPI and a modular transactional backend

**Status.** Implemented.

**Decision.** Use FastAPI with Pydantic request/schema validation, Python domain modules, SQLAlchemy transactions and a Uvicorn HTTP process. Keep authoritative business checks on the server; route registration delegates to domain owners rather than embedding every rule in transport handlers.

**Why it fits.** The system has many related validation, scheduling, credit and approval rules. FastAPI/Pydantic provide HTTP validation and schema generation while Python domain modules and SQLAlchemy services keep transactional behavior separate from the UI and host.

**Pros.** An ordinary HTTP application can run locally, in tests and in a container. Central server validation, OpenAPI contracts and isolated domain tests support a consistent boundary.

**Cons.** Two languages require explicit browser/server contract maintenance. Python dependencies, synchronous database work, worker resources and large route-registration modules remain maintenance and capacity concerns. Async HTTP alone does not remove database contention.

**Scaling / revisit trigger.** Measure handler time, query counts, pool waits, memory and concurrency. Improve queries and domain boundaries before adding services. Move long-running processing to separately designed durable jobs when evidence requires it; do not rely on work continuing after a Lambda request ends.

**Alternative / contingency.** A containerized FastAPI service can retain domain code while changing hosting. Django or a TypeScript backend would require substantial contract, transaction and authorization regression work. Splitting services creates distributed consistency problems and is not an automatic scalability improvement.

**Owners/evidence.** [Application composition](../../backend/app/main.py), [route registration](../../backend/app/api/routes.py), [Python dependencies](../../backend/pyproject.toml), [database transactions](../../backend/app/database.py), [BR-003](../business-rules.md#br-003).

<a id="adr-003"></a>

## ADR-003 — PostgreSQL, SQLAlchemy/Alembic and durable command receipts

**Status.** Implemented storage; managed-host acceptance separate.

**Decision.** PostgreSQL owns relational business records, purchased snapshots, audit/credit evidence and command receipts; SQLAlchemy and Alembic define models and forward schema changes. A command commits its effects and receipt together. A lost response is reconciled using the original actor and key. S3 is the selected durable media boundary; media and report workflows remain subject to the operation matrix. Application memory and local disk are not durable business stores. Package lifecycle storage separates live bookings from stable session identities and typed deletion archives, preserving plans, results and decision history. Stable original/performed Trainer evidence and append-only assignment history are source-accepted; current assignment remains compatible with the outgoing application. Historical session access never grants current write or full client-profile authority. Permitted package deletion Undo restores original identities with increasing versions only after checking unchanged records and original media availability. General Undo uses typed immutable change snapshots, dependency hashes and compensating transactions; acceptance remains governed by the operation matrix.

**Why it fits.** Schedules, purchases, credit accounting, approvals and retained history have relational constraints and must change consistently. PostgreSQL transactions provide one durable authority for effects and their receipts; version checks make competing edits visible instead of silently overwriting them.

**Pros.** Relational constraints, transactional updates and durable evidence support conflicts, reconciliation and permitted compensating Undo. SQLAlchemy isolates persistence details; Alembic records reviewed schema evolution.

**Cons.** Lock contention, connection limits, query growth and migration risk still need measurement. SQLAlchemy does not make schema changes or bulk operations safe automatically. Database transactions cannot atomically include Cognito or object-storage effects. Receipts do not imply recovery of unsent drafts after a browser restart.

**Scaling / revisit trigger.** Measure slow queries, lock/pool waits, index use, storage and retention first. Bound aggregate application connections across instances. Evaluate a pooler/proxy or database sizing only against observed demand and transaction semantics. Replicas may help suitable reads but cannot supply stale authorization or replace the authoritative write path.

**Alternative / contingency.** Another managed PostgreSQL host is the closest migration option, subject to extensions, TLS, roles, backup and networking compatibility. DynamoDB or a document database would require redesigning multi-record constraints and transactions; SQLite is not equivalent acceptance. A tested database restore is a recovery option, not yet a proven standby.

**Owners/evidence.** [Database owner](../../backend/app/database.py), [models](../../backend/app/models), [migrations](../../backend/migrations), [BR-009](../business-rules.md#br-009), [BR-017](../business-rules.md#br-017), [BR-061](../business-rules.md#br-061).

<a id="adr-004"></a>

## ADR-004 — Cognito identity with application-owned authorization

**Status.** Implemented integration; real-provider acceptance separate.

**Decision.** Cognito owns staff identity and authentication challenges. FastAPI verifies signed tokens, cookies/CSRF, active staff identity and current record permissions. Domain services recheck reviewed versions, assignment and conflicts inside the transaction. Browser capabilities describe available features; they do not grant authority.

**Why it fits.** Staff enrollment, MFA, password recovery and verified email changes benefit from a dedicated identity service. Fitfinity must still decide current roles, assignment and record access from its own authoritative state; a valid token is not sufficient permission.

**Pros.** Managed authentication challenges and signed-token verification avoid building a password/MFA service. Server cookies, CSRF and current staff checks keep browser claims out of authorization.

**Cons.** Provider availability, quotas and challenge/recovery semantics affect login. JWT validity and application revocation must stay coordinated. Identity migration is harder than changing an endpoint, especially for provider subjects, MFA and pending email changes.

**Scaling / revisit trigger.** Measure login/challenge failures and provider latency without recording credentials or health data. Review provider limits and active-session behavior before expanding staff/tenant scope. Multi-tenant identity partitioning is not currently established.

**Alternative / contingency.** Another OIDC identity service is a possible redesign after testing account/subject mapping, session revocation, email verification and MFA re-enrollment. Self-hosting identity adds patching and recovery operations. An outage must not bypass MFA or enable demo identities. Lost MFA uses the authorized operator process, not new Owner/Admin app powers.

**Owners/evidence.** [Auth service](../../backend/app/auth/service.py), [Cognito adapter](../../backend/app/auth/cognito.py), [JWT verification](../../backend/app/auth/jwt.py), [authorization](../../backend/app/authorization.py), [BR-006–008](../business-rules.md#br-006), [BR-031](../business-rules.md#br-031).

<a id="adr-005"></a>

## ADR-005 — CloudFront, API Gateway and containerized Lambda on AWS

**Status.** Selected topology; current-source deployment not established.

**Decision.** The selected AWS topology serves static assets through CloudFront and routes API Gateway requests to FastAPI on Lambda through the Lambda Web Adapter. Cognito, private PostgreSQL/RDS and S3 have distinct responsibilities. The application remains ordinary container-compatible HTTP so hosting changes do not require rewriting business logic. Selected topology does not establish that current source is deployed; Progress owns observed deployment status.

**Why it fits.** Static delivery and managed request execution separate frontend traffic from business processing. The Lambda Web Adapter retains ordinary FastAPI HTTP behavior instead of requiring a Lambda-specific rewrite. AWS supplies identity, relational hosting and private object storage within the selected environment.

**Pros.** Managed entry/scaling and a portable application container reduce custom host lifecycle work. Static assets can be cached independently from authenticated API responses.

**Cons.** Cold starts, execution limits, VPC/database connectivity, aggregate connection demand and cloud costs remain constraints. Managed compute does not make RDS free or infinitely scalable. A regional/platform incident can affect several dependencies; a CDN cannot serve fresh protected business state during a backend outage.

**Scaling / revisit trigger.** Measure cold/warm p50/p95/p99, concurrency, errors, resource use and database saturation before adjusting capacity. Evaluate reserved/provisioned capacity, routing or a container service only with measured benefits and cost review. Long media processing belongs in the planned durable-worker design, not an assumed extended request.

**Alternative / contingency.** ECS/Fargate or another managed container host could retain FastAPI while trading cold-start behavior for continuously running capacity and more operational configuration. Another cloud requires identity, storage, network and release adaptation. No alternate region/host is a configured hot standby; DNS switching without state and writer coordination is unsafe.

**Owners/evidence.** [Runtime container](../../backend/Dockerfile), [infrastructure owners](../../backend/infrastructure), [release runbook](../runbook.md#6-deployments-and-rollback), [BR-060–061](../business-rules.md#br-060).

<a id="adr-006"></a>

## ADR-006 — Private S3 media, immutable upload intents and durable cleanup

**Status.** Source implemented; activation/processing acceptance separate.

**Decision.** Library saves reserve a private original intent, upload immutable bytes directly with short-lived signatures, verify stored length/type/checksum and recheck current permissions/version before publishing metadata and receipts atomically. Reads verify bytes and recheck attachment scope before playback. Durable cleanup waits for upload leases and live references, retaining work across failures. Session recordings use the same private storage boundary, with reviewed session/plan ownership, a fixed publication expiry and durable abandoned-upload/replacement cleanup. Production media is disabled by default; source acceptance follows the matrix, while processing/transcoding and worker scheduling remain separate work.

**Why it fits.** Exercise assets and session recordings are binary objects with different storage and transfer needs from relational records. Direct signed uploads avoid routing large media through the API while database-owned intents and scope checks govern publication and access.

**Pros.** Private durable storage, immutable bytes and checksum verification make publication reviewable. Leases and reference checks protect active uploads and retained media during cleanup and Undo.

**Cons.** Object IO and database commits are separate effects, so interrupted uploads and cleanup need reconciliation. Signed URLs remain usable within their permitted lifetime; short expiry and current scope checks matter. S3-compatible local tests do not prove AWS CORS, IAM or lifecycle configuration.

**Scaling / revisit trigger.** Measure object size, transfer/egress, upload failures, cleanup backlog and retention cost. Introduce durable processing/transcoding/caption jobs under M7 with leases, retries and evidence. Do not extend fixed expiry or delete referenced evidence to reduce costs.

**Alternative / contingency.** Another private S3-compatible provider may fit after signature, checksum, conditional-write, CORS and permission acceptance. Migration must preserve object identity, bytes, expiry and pending intents. Application disk is not durable fallback. Object backups and database restore points must be reconciled before reopening media access.

**Owners/evidence.** [Storage adapter](../../backend/app/media_storage.py), [library cleanup](../../backend/app/library_cleanup.py), [recording cleanup](../../backend/app/session_media_cleanup.py), [media configuration](../runbook.md#10-configuration), [operation matrix](../api-contracts.md#domain-operation-inventory).

<a id="adr-007"></a>

## ADR-007 — Layered verification with real isolated PostgreSQL

**Status.** Existing suites implemented; mutation/performance expansion planned.

**Decision.** Playwright's `tests-api/` runs the real frontend, FastAPI routes, migrations, JWT checks, cookies, CSRF and authorization against temporary Docker PostgreSQL with worker-isolated databases. A local signed-token provider substitutes Cognito. The media tests use real object IO against a pinned, disposable RustFS S3-compatible service with private per-worker buckets; this does not establish AWS S3 acceptance. The verifier rejects non-test database/storage targets and removes owned resources. CI distributes the complete real-API inventory across two isolated shards; a required aggregate compares case identities and requires both jobs to pass without retries or omissions. Node-simulator browser tests remain separate frontend evidence. Separate backend drills kill actual HTTP workers before/after a commit, restart against the same isolated database and verify rollback, durable receipts and authentication. The operator recovery drill exercises real identity-revocation triggers with SDK-stubbed Cognito reset responses; the app gains no recovery-admin powers. No Lambda deployment or production database is needed.

Existing checks cover frontend units; simulator browser workflows; backend/PostgreSQL transactions, authorization and migrations; real-API browser persistence/recovery; offline infrastructure guards; assessment paper-form parity; lint/source health and verifier regressions; and builds/PWA behavior. These have different evidence scopes: simulator success does not prove persistence, and synthetic identity does not prove real Cognito. The [suite diagram](diagram.md#full-verification-suite) separates existing checks, planned additions and external acceptance. [Development](../development.md#verification-commands) owns executable commands; Progress owns results and remaining work.

Mutation testing will target critical JavaScript/Python business rules, authorization and persistence, inspect surviving/equivalent mutations and establish justified gates. Performance campaigns will measure p50/p95/p99 latency, throughput, errors, CPU/memory, connection/query behavior and browser vitals with representative data, concurrency and bounded overload/fault cases. Cold/warm measurements need an identified environment; local Docker cannot prove Lambda cold-start behavior. Establish measured budgets after baseline rather than copying arbitrary thresholds. Expanded resilience testing will cover rate limits, dependency failures, broader service failures and interrupted-write recovery alongside existing targeted process-restart cases.

**Why it fits.** Frontend contracts alone cannot establish durable writes, transaction safety or permission scope. Real database/API tests exercise the deployed technology boundary while synthetic provider fixtures keep routine verification independent of customer data and paid AWS resources.

**Pros.** Reproducible isolation, independent foreign-record assertions and restart/fault probes detect failures that mocked endpoints miss. Sharding reduces elapsed time while the aggregate preserves complete case coverage.

**Cons.** Containers and browsers add setup/CI cost and platform sensitivity. Synthetic identity and local object storage leave real-provider and device gaps. Passing finite probes cannot establish an error-free system or a latency guarantee.

**Scaling / revisit trigger.** Expand critical-rule mutation testing after a baseline and survivor review; establish measured performance budgets with representative data and concurrency. Optimize test ownership/caching/shards only while retaining every required case and failure meaning. Use separately authorized deployed measurements for Lambda cold starts.

**Alternative / contingency.** Another test runner or CI host is possible if it preserves actual PostgreSQL, migrations, permission/recovery coverage and case inventory. Simulator-only or SQLite substitution is not equivalent. During infrastructure failures, preserve evidence and repair the harness rather than weaken checks.

**Owners/evidence.** [Backend tests](../../backend/tests), [real-API browser tests](../../tests-api), [browser Compose](../../backend/compose.browser.yaml), [verifier](../../scripts/verify-api-browser.mjs), [test diagram](diagram.md#full-verification-suite), [BR-063–064](../business-rules.md#br-063).

<a id="adr-008"></a>

## ADR-008 — Verified revisions, separate AWS release and reviewed dependencies

**Status.** Source workflow implemented; deployment evidence separate.

**Decision.** The Docker `application` stage is shared; `test` adds test dependencies without downloading the Lambda adapter, while `runtime` adds the pinned adapter. Final-head frontend/backend/API-browser CI precedes source acceptance. Normal main verification/demo publishing is independent of AWS image approval. Image publication is manually initiated with an exact main SHA, reruns all three gates for that SHA, and then requires the protected AWS environment approval; it never deploys Lambda. Image publication, migrations, deployment and live/provider/device acceptance require their own evidence and applicable authorization. Mutation testing, measured performance budgets and OpenTelemetry/Grafana remain planned work in Progress, not existing capabilities. [Business rules](../business-rules.md#deployment-migration-and-acceptance) owns release safeguards.

Dependabot source configuration covers bounded weekly npm, GitHub Actions and Dockerfile-image update PRs; the remaining floating frontend tooling declarations are pinned to their existing lockfile versions. Bot PR execution has been observed; the user reported zero open /26 closed alerts after PR104, but independent alert reads returned403; that report is not current API verification or deployed remediation. Required npm audit includes development tooling, blocks high/critical findings and retains the report; it does not cover Python or container packages. Python custom hashed locks and Compose image pins still require manual maintenance until a compatible updater is tested. [Runbook](../runbook.md#dependency-maintenance) owns review/triage instructions; Progress H4 owns remaining coverage. Assess SBOMs and artifact/source provenance against verified digests. Secret scanning and static security analysis supplement current lint and authorization tests; repository/account-level settings need verification before any claim they are enabled. Automated updates or clean scans do not replace review, full CI or release approval.

**Why it fits.** Changes to business logic and dependency/runtime bytes need a traceable connection to verification. Separating normal source CI from approval-gated image work avoids making routine verification depend on obsolete release approvals.

**Pros.** Exact-head gates, retained evidence, locked dependencies and manual release initiation support review and reproducibility. Shared application/test Docker stages avoid unnecessary Lambda-adapter downloads during tests.

**Cons.** Full CI costs time and tool updates can require compatibility repairs. Lockfiles do not freeze OS repositories or prove deployed remediation. Manual approval, scans and a version inventory still require responsible review; custom Python locks and Compose pins are not fully automated.

**Scaling / revisit trigger.** Measure gate duration and external-download failures before changing partitioning or caching. Extend updater/audit coverage and evaluate SBOM/provenance against verified artifact digests under M10. Keep dependency proposals bounded and complete final-head checks intact.

**Alternative / contingency.** Another CI service or managed runner can replace GitHub execution only after reproducing gate, isolation and artifact controls. Source revert and compatible prior-artifact recovery need explicit verification; neither reverses database/provider effects. CI unavailability does not justify an unverified deployment.

**Owners/evidence.** [Workflows](../../.github/workflows), [Docker stages](../../backend/Dockerfile), [Dependabot](../../.github/dependabot.yml), [versions](../versions.md), [development](../development.md), [release rules](../business-rules.md#deployment-migration-and-acceptance).

<a id="adr-009"></a>

## ADR-009 — Allowlisted logs now; OpenTelemetry and Grafana planned

**Status.** Structured request logs implemented; OTel/Grafana not implemented.

**Decision.** OpenTelemetry will correlate traces, metrics and structured logs across requests, database work and recovery. Grafana dashboards, SLOs and actionable alerts will use those measurements. Redaction of health/identity data, credentials, cookies and SQL parameters, plus sampling, retention, cardinality and cost controls, must precede activation. Validate correlation and exporter failure isolation locally first; instrumentation and export should start disabled. A Grafana stack, ingestion, credentials and production activation remain separately scoped work, not a connected capability today.

**Why it fits.** Cross-request/database/recovery diagnosis needs correlation, but staff identity and health information must not enter telemetry. Current allowlisted structured events provide a small diagnostic foundation; standard telemetry is a proposed way to improve visibility without creating another business ledger.

**Pros.** Current request IDs, route/status/duration and error types provide bounded diagnostic evidence. Proposed standard instrumentation could connect timings and service signals across components and receivers.

**Cons.** Current logs are not distributed traces, SLO dashboards or complete latency campaigns. Future sampling may omit incidents; exporters, high cardinality and ingestion can add cost or affect reliability without isolation. Redaction and access controls need explicit testing.

**Scaling / revisit trigger.** Implement disabled-first correlation/redaction and exporter-failure tests, then baseline volume, sampling, retention and incident utility. Set measured SLOs and actionable alerts before production activation. Track telemetry cost and missing evidence as well as application performance.

**Alternative / contingency.** Available platform logs can support interim investigation within configured retention/access. Another OTLP receiver or self-hosted collector is a candidate, with its own operations and data-governance burden. A receiver change cannot recover events never captured; telemetry must not become write authority or block recovery.

**Owners/evidence.** [Current observability](../../backend/app/observability.py), [runbook monitoring](../runbook.md#4-monitoring-and-observability), [M10 packages](../../PROGRESS.md#m10-work-packages--planned), [BR-007](../business-rules.md#br-007).

<a id="adr-010"></a>

## ADR-010 — Explicit migration, restore and operational recovery boundaries

**Status.** Selected approach; full operational drills and acceptance pending.

**Decision.** Consolidated AWS release preparation will bind source, image/artifact, grants and migrations to a reviewed rollout and populated-data recovery plan. Health/readiness acceptance, synthetic monitoring, incident ownership, alert exercises, rollback, backup/restore and migration-recovery drills will establish measurable recovery limits. Capacity/resource/cost monitoring supports those decisions. Start with isolated drills; actual AWS changes, real providers, paid telemetry and live load require their applicable authorization. These tasks belong to [M10 work packages](../../PROGRESS.md#m10-work-packages--planned) under Progress → Remaining work. M10 does not defer the security, migration and restore evidence required before launch.

**Why it fits.** Persistent credits, approvals, audit history and private media cannot be reconstructed by deploying application code alone. Forward-compatible schema changes and a measured recovery plan must preserve data and external-effect consistency.

**Pros.** Explicit source/schema/resource bindings and rehearsed recovery can reduce ambiguity during incidents. Separating isolated preparation from environment execution protects customer state and preserves operator ownership.

**Cons.** Backups cost storage and restore takes time. A database snapshot alone omits objects, identity state and effects after its restore point. Code rollback cannot undo financial/history changes. Current planning does not establish achieved RPO/RTO or a working failover environment.

**Scaling / revisit trigger.** Use populated isolated migration/restore drills to measure RPO/RTO and validate invariants, media availability and identity reconciliation. Revisit backup frequency, retention, capacity and regional recovery only after business recovery needs and measured costs are agreed. Launch-critical evidence remains required before launch regardless of M10 scheduling.

**Alternative / contingency.** Restore to a separately verified PostgreSQL instance and private object store is a candidate recovery route; a regional standby is a larger separately designed option. Fence old writers, reconcile effects and verify permissions before resuming. There is no authorized automatic promotion, destructive downgrade or resource recreation.

**Owners/evidence.** [Migrations](../../backend/migrations), [restore runbook](../runbook.md#7-data-protection-and-restore), [roadmap](../journey.md#full-milestone-roadmap), [BR-060–064](../business-rules.md#br-060).

## Scaling review and fallback readiness

| Pressure or failure | First evidence to collect | Candidate response | Preserve before changing architecture |
| --- | --- | --- | --- |
| Slow portal interactions | Device/network timings, bundle/render costs and API waterfall | Optimize the measured feature or query | Drafts, accessibility, permissions and uncertain-command recovery |
| API bursts/cold starts | Cold/warm latency, concurrency, pool waits, errors and resource costs | Tune measured bottleneck; assess capacity or container hosting | Transaction authority and bounded database demand |
| Database contention/growth | Locks, query plans, receipt/history size and retention | Index/query review, sizing or reviewed pooling | Audit/credit history, versions and atomic receipts |
| More studios/tenants | Actual independence of identities, records and schedules | Design explicit tenant isolation before partitioning | No cross-tenant reads/writes or duplicate scarce-resource authority |
| Cognito interruption | Challenge/session/provider evidence | Recover or hold affected flows through the authorized operator process | MFA, original identity and uncertain provider outcomes |
| Media growth/failures | Upload/checksum errors, leases, cleanup backlog and storage/egress | Review limits, cleanup and durable processing | Private scope, immutable bytes, expiry and Undo holds |
| AWS/database outage | Impact, latest valid backups and outstanding effects | Approved restore/continuity procedure after validation | One active writer, consistent state and identity/object reconciliation |
| Telemetry outage | Producer/exporter/receiver evidence, where implemented | Restore visibility using available platform diagnostics | Redaction and no fabricated replay |
| CI/dependency disruption | First failure, exact source and verified artifact | Repair runner/source dependencies or reviewed delivery recovery | Complete gates, trusted bytes and no unverified deployment |

No alternate stack above is configured as hot standby. Before calling an option a backup, define ownership, current costs/limits, RPO/RTO, data and object export/restore, identity/session reconciliation, secrets/network/DNS cutover, single-writer fencing, acceptance and rollback. Rehearse with populated isolated data before separately authorized environment execution. A source ZIP, static demo or database snapshot alone is not a complete recoverable system.

Format reference: [SoccerBot ADR at the inspected revision](https://github.com/LimYouSheng/SoccerBotStudioSG/blob/1b25b892165934282479e3676d4456d2a3403045/docs/architecture/adr.md). Its Cloudflare, provider and deployment decisions are not imported into Fitfinity.
