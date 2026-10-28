# Fitfinity operations runbook

Draft — **28 October 2026**. For authorised operators of the developer AWS environment and future production releases. [Security infrastructure](security.md) maps controls and remaining layers. This document owns operating procedures; it does not claim that current source is deployed or planned monitoring is active. Confirm the target account, environment and deployed revision before acting. [Progress](../PROGRESS.md) owns current evidence and pending work, [Business rules](business-rules.md) owns rules, and [Development](development.md) owns local setup and verification commands.

Navigation: [Access](#1-ownership-and-access) · [Routine checks](#2-routine-checks) · [Dependencies](#3-dependency-maintenance-and-dependabot) · [Monitoring](#4-monitoring-and-observability) · [Incidents](#5-incident-response-and-recovery) · [Releases](#6-deployments-and-rollback) · [Restore](#7-data-protection-and-restore) · [DNS](#8-domain-dns-and-https) · [Handover](#9-operational-records-and-handover).

Adapted from [SoccerBot's runbook format](https://github.com/LimYouSheng/SoccerBotStudioSG/blob/feat/version-inventory/docs/Runbook.md). Fitfinity uses its own Cognito, FastAPI, PostgreSQL and AWS deployment model; SoccerBot provider permissions and monitoring are not inherited.

## 1. Ownership and access

| Area | Responsible role | Boundary |
| --- | --- | --- |
| Business acceptance, downtime and residual risk | Business Owner | Approves operational impact and designated live test activity |
| Application source, CI and diagnosis | Engineering maintainer | Preserves rules, final-head gates and original failure evidence |
| AWS release, infrastructure and credentials | Authorised AWS operator | Confirms account/region/resource identities; separate approval for mutation/deployment |
| PostgreSQL schema, migration and restore | Authorised database operator | Separate migration/runtime identities; protects populated data and rollback compatibility |
| Staff account recovery | Authorised identity operator | Exact Cognito user plus application identity; no app-admin MFA-reset power |
| Remuneration and credit corrections | Owner with engineering support | Uses reviewed domain actions and audit evidence; approved pay is not a payment transfer |
| DNS and certificates | Authorised DNS/hosting owner | Preserves existing hosting and mail records; verifies actual renewal prerequisites |
| Monitoring and incident coverage | Assigned primary/backup responders | Grafana/alerts remain pending until configured and exercised |

Keep named primary/backup contacts, support channels, MFA and billing ownership in the restricted access inventory. Do not store passwords, recovery codes, signing keys or database credentials in this file.

| Target | Repository reference | Verify before acting |
| --- | --- | --- |
| Developer/test AWS | [deployment-test.json](../backend/infrastructure/deployment-test.json): account418638389566, regionap-southeast-1, GitHub environmentaws-test | Actual caller, target resource identity and current approval; the file contains historical stage receipts |
| AWS application runtime | [private-runtime-contract.json](../backend/infrastructure/private-runtime-contract.json) and release receipts | Current Lambda image digest, API routing, Cognito pool, database and configuration; retained fingerprints are not current-source deployment proof |
| AWS frontend | [hosting-source.json](../backend/infrastructure/hosting-source.json) and hosting receipts | Actual CloudFront/static artifact and API origin; historical source bindings cannot accept arbitrary new bytes |
| Pages demo | [pages.yml](../.github/workflows/pages.yml) | Demo export only; not the developer AWS API site |
| Future production | Separately reviewed environment mapping | Do not infer a production account, domain or resource set from developer configuration |

## 2. Routine checks

Suggested cadence; assign coverage before operational handover.

| When | Check | Record / follow-up |
| --- | --- | --- |
| Each operational day | Website/HTTPS, API readiness, sign-in failures, unresolved saves, AWS incidents and security notifications | Environment, deployed revision, affected operation and request ID; do not create business writes merely to check health |
| Monday after09:00 Singapore | Dependabot jobs, update PRs, alerts and failed verification | Follow section3; scheduled jobs may start later |
| After release/configuration changes | Actual frontend/API artifacts, readiness, permitted sign-in/read and arranged role smoke checks | Match source and artifact receipts; confirm authorization and persistence on designated records |
| Monthly / before handover | Access, MFA, billing, certificates, backup retention, restore readiness, resource/cost trends and alert receivers | Actual observed settings; record missing coverage instead of assuming defaults |
| After an incident | Recover unresolved outcomes, verify permissions/data and review cause | Retain first failure, repair evidence and outstanding actions |

Use [Owner](uat/owner.md), [Admin](uat/admin.md) and [Trainer](uat/trainer.md) worksheets for arranged developer AWS acceptance. They are blank masters, not passed tests. Real invitations, email changes, media writes and disruptive recovery need designated test identities and applicable operator authority.

## 3. Dependency maintenance and Dependabot

### Dependency maintenance

[versions.md](versions.md) is the dependency inventory of locked application/transitive dependencies, images, browser engines and CI pins, with manual patch guidance and explicit gaps for deployed/OS versions. Update it alongside dependency changes.

The design has three layers:

| Layer | Purpose | Behaviour |
| --- | --- | --- |
| Version updates | Keep dependencies current | Weekly Monday, 9 am Singapore. At most one open version-update PR each for npm, Actions and backend Dockerfile images. |
| Security alerts and updates | Identify known vulnerabilities and propose fixes | GitHub alerts and security PRs have been observed. Settings and the complete alert inventory still require verification with appropriate read access; security updates are independent of the weekly schedule and version-PR limits. |
| Blocking audit | Prevent known high/critical npm findings from passing verification | Full verification runs `npm audit --include=dev --audit-level=high --json`, including development tooling, and retains the report even on failure. Registry/access errors fail verification too. This does not audit Python, OS/container packages or the deployed environment. |

Routine minor/patch updates are grouped. Major upgrades and sensitive tooling (TypeScript, ESLint, Playwright, Wrangler and Miniflare, where present) remain separate from routine and security groups. Other minor/patch npm security fixes have their own group. Exclusions from grouping do not ignore updates. Python runtime proposals remain within the supported 3.12 line. The version-PR limit controls the queue, not a guarantee that all updates fit one PR.

Every update follows **PR → compatibility fixes → all three CI gates → review and authorized merge → fresh main CI → separately authorized deployment and verification**. There is no automatic merge. Failed updates leave the deployed version unchanged and require investigation; never weaken tests to accept them. Main verification can publish the Pages demo; AWS image publication and Lambda deployment remain separate manual, authorized actions. A deployed security fix is complete only after the affected deployment is verified.

GitHub alerts/PRs notify according to account notification preferences; they do not automatically message this chat. Recheck security settings for each client repository. Closing update PRs neither fixes vulnerabilities nor disables future proposals. The five formerly floating frontend test/build declarations remain pinned.

Review release notes, compatibility, dependency/lockfile diffs, vulnerability reachability and license changes before accepting an update. Require full final-head frontend/backend/API-browser CI and preserve SHA-pinned Actions and image digest/source evidence. Triage critical or actively exploited findings within24 hours, high severity within3 business days and other alerts within10 business days; record exposure, owner and disposition rather than treating these targets as a waiver or guaranteed remediation date. Release-blocking findings must be resolved or separately reviewed before deployment.

Python version updates remain manually maintained: `pyproject.toml` feeds uv-generated `requirements.lock` and `requirements-test.lock`, which the current Dependabot pip fetcher does not discover as ordinary requirements files. Observed security PR106 updated only the manifest; a bot proposal is incomplete until both hashed locks are regenerated and verified. Review/regenerate both hashed locks together with manifest changes and run the complete isolated backend/API gates. Compose PostgreSQL/RustFS pins also remain manually reviewed; Dockerfile automation is not claimed to cover Compose or every embedded image reference. A tested lock-updater integration, remaining image coverage, security-alert activation, SBOMs and provenance remain in Progress H4.

### Update and remediation procedure

1. Read the advisory/release notes and PR diff. Use [versions.md](versions.md) to identify direct, transitive, development and image exposure. Inspect vulnerable Action internals and OS packages separately from app locks. Confirm repository alert/security-update settings with suitable access; copied YAML does not enable them.
2. Update the owning inputs together: npm manifest/lock, Python manifest and **both hashed locks**, or reviewed full Action SHA/image references. Python and Compose PostgreSQL/RustFS maintenance remain manual. A manifest-only Python security PR is incomplete.
3. Refresh `docs/versions.md`, including nested versions and input fingerprints. This is manually maintained; no generated freshness gate or automatic artifact SBOM is claimed. Preserve unrelated pins and verify hashes; do not use forced blanket upgrades.
4. Run relevant checks, then require exact-head `verify / frontend`, `verify / backend` and `verify / api-browser`. The npm audit includes development tools and blocks high/critical findings and audit-service errors. It does not cover Python, OS packages or the deployed Lambda image. Diagnose failures without weakening tests, adding retries or raising timeouts.
5. Review and merge only the tested head, then inspect fresh **main application CI**, not a Dependabot job named main. PR success, source merge, image publication and deployed remediation are different evidence.
6. Recheck alerts/audits and, after separately authorised deployment, the actual deployed digest. Closed-as-fixed differs from dismissed. The user reported0 open/26 closed alerts after PR104; detailed API access remained403. That observation is not a continuing clean-state guarantee.

Triage critical/actively exploited findings within24 hours, high severity within3 business days and others within10 business days under the retained policy. Record owner, exposure and disposition; these targets do not waive vulnerabilities. If no compatible patch exists, document containment and escalate a concrete mitigation plan. Closing bot PRs does not install a fix or disable future update proposals.

## 4. Monitoring and observability

### Current source capabilities

| Surface | Implemented owner / signal | What it does not prove |
| --- | --- | --- |
| `/health/live` | [main.py](../backend/app/main.py): process responds alive | Database readiness, Cognito delivery or end-to-end workflow success |
| `/health/ready` | Database connectivity and exact expected Alembic heads; auth must be enabled for staging/production | Every route/provider/media capability is working; no revision/digest is exposed here |
| Structured request logs | [observability.py](../backend/app/observability.py): request_id, method, route, status, duration_ms and error_type; standard timestamp/level/event | Complete distributed traces, user-perceived latency or installed SLOs |
| Error response | Stable code/message/requestId | An error or lost response alone does not prove a write failed before commit |
| AWS runtime/service metrics | Inspect only the actual configured account/service/log groups | No particular dashboard, retention, alarm or receiver is claimed configured by this document |

Use the API's deployed base path when checking health; do not assume a frontend-origin path reaches FastAPI. Correlate request IDs with redacted logs. Never export health answers, signatures, cookies/tokens, request bodies, raw SQL parameters or credentials. Logs and browser/device evidence need restricted storage where personal data could appear.

### Planned monitoring — not activated

OpenTelemetry, Grafana, measured latency budgets, SLOs, alert receivers and backup/restore monitoring remain [M10 work](../PROGRESS.md#m10-work-packages--planned). There is no Fitfinity Tail Worker, Tempo exporter, dashboard JSON or exporter command to copy from SoccerBot.

Before activation: define service/environment labels and correlation; review redaction and sampling; cap cardinality, retention and cost; verify export failure isolation; measure representative cold/warm workloads; configure named responders and test actual receiver delivery. Choose thresholds from observed baselines, not invented budgets. Check ingestion with real queryable evidence; an exporter HTTP response or an empty dashboard is not proof of monitoring coverage.

| Proposed alert | Investigate | Responsible operator |
| --- | --- | --- |
| Website/API availability or certificate failure | DNS/HTTPS, routing, recent artifact, health and AWS incidents | Hosting / release |
| Sustained errors or slow saves | Route, request IDs, cold/warm behavior, database connections/queries and provider timing | Engineering / database |
| Unresolved writes, duplicate-looking credits or approvals | Original command receipt, business record and immutable evidence | Engineering + Owner |
| Database/storage saturation or backup failure | Actual metrics, capacity, retention and latest successful recoverable point | Database / AWS |
| Telemetry loss during known traffic | Configuration/export path and receiver, not just an empty chart | Monitoring |
| Advisories, failed update checks or cost spike | Exact dependency/digest or resource usage, account and recent changes | Maintainer / AWS |

**Draft operational detail — 28 October 2026.** The Owner confirmed that targets, thresholds, responders/destinations and a restore-drill receipt are not yet agreed or available, and authorized drafting first. The following values are concrete review proposals, not active alarms, measured budgets, SLAs or accepted recovery commitments. Current alert-rule IDs, receiver/contact-point IDs, primary responder, backup, destination and coverage hours are **unassigned/unverified**. Do not infer24/7 cover or use a repository/GitHub username as a notification address. No alert is provisioned or sent by this documentation.

**Availability and TLS proposal.** Probe approved frontend content and the correctly routed API readiness endpoint once per minute from two independent locations. Critical after both locations fail three consecutive checks; clear after both succeed three times. Use non-mutating requests and verify the expected marker and trusted certificate. A live-only probe cannot establish database readiness; no synthetic booking or provider write is a health check. Propose certificate-expiry warning below21 days and critical below7 days, clearing after a trusted replacement exceeds21 days. Review renewal timing, maintenance and false positives before approval.

**Errors and latency proposal.** With complete unsampled request counters, warn at5%5xx over10 minutes with at least20 requests and escalate at20% over5 minutes with at least20 requests; clear after10 minutes below warning. Sparse traffic still requires investigation for an affected user, but is not a statistically meaningful rate. Route/environment labels must exclude customer identifiers. For latency, establish representative per-route cold/warm p50/p95/p99 and sample counts first; propose a sustained p95 above twice that approved baseline for10 minutes as an investigation trigger, not a fixed response-time SLA. No baseline or latency alert is currently accepted. Failure-biased sampled traces cannot supply true request/error rates.

**Integrity, capacity and recovery proposal.** Any confirmed cross-record disclosure, duplicate credit debit, unauthorized remuneration approval or corrupted durable receipt is critical irrespective of traffic; clear only after recorded containment/reconciliation. An unresolved user command remains bound to its original key; alerting must never retry it. Propose a warning for database free storage below20% for15 minutes, critical below10% for5 minutes, with recovery above25% for15 minutes; use actual provisioned storage and autoscaling limits and validate thresholds against growth. Warn on any failed expected backup job or a latest-restorable-time lag greater than the approved RPO; this requires an inspected backup schedule and RDS recovery metadata. A source template or snapshot filename is insufficient evidence.

**Monitoring/security proposal.** A separately configured heartbeat missing for10 minutes or three exporter failures in5 minutes should warn; clear only after queryable ingestion and heartbeat recovery. No application traffic is not proof that telemetry failed. Triage new high/critical dependency findings on detection; verified remediation and deployment/re-scan, not closing a PR, clears deployed exposure. GitHub notifications and Grafana receivers are independent channels; both need actual account settings and delivery acceptance.

**Routing and acceptance to complete before activation.** Record the named primary/backup, exact destination, coverage timezone/hours, environment/service, signal source, query, evaluation/clear/no-data/error policy, rule/contact-point IDs and linked incident procedure. Proposed critical acknowledgement/escalation is15 minutes during explicitly agreed coverage; warnings go to the next staffed period unless impact warrants escalation. These are unapproved proposals. Group by environment/service/symptom, never raw health/client/session data. Test a synthetic firing through delivery, acknowledgement, escalation, resolution and deduplication; retain redacted timestamps and receiver evidence. Give maintenance silences an owner/reason/expiry and never silence unresolved integrity breaches as routine maintenance.

## 5. Incident response and recovery

1. Record Singapore/UTC times, environment/account, hostname, deployed revision/digest, affected role/operation and safe request IDs. Assign an incident owner and update cadence.
2. Prioritise data exposure, lost/duplicate business effects and account compromise, then availability and performance. Preserve original evidence before changing anything.
3. Inspect recent source/configuration changes, health, AWS incidents and matching logs/receipts. An accepted source PR does not identify the current deployment.
4. Make the smallest reviewed correction with the required authority. Do not replay an uncertain save under a new key, edit approved remuneration to force agreement, erase history, reset the database or weaken MFA/permissions.
5. Verify the affected records and permissions, then run arranged role checks. Reconcile outstanding outcomes; one successful request does not close every affected case.

### 5.1 Symptom guide

| Symptom | First checks | Recovery / stop condition |
| --- | --- | --- |
| Wrong page or site unavailable | Hostname, TLS, CloudFront/static artifact, cache and API routing | Restore only an identified compatible artifact/route; preserve other domains and mail records |
| API not ready | Database connection, actual migration heads, auth setting and release compatibility | Diagnose failure before retrying migration or changing grants; never reset populated data |
| Sign-in/code fails | Correct developer identity/pool, verified email, expiry, provider status and resend limits | Reconcile pending email/provider outcomes; do not repeatedly send codes or disable required MFA |
| Save timed out / connection lost | Original actor/key, receipt and current record; Check UI | Read original outcome first. Explicit retry retains original intent; no replacement creation/debit |
| Conflict after another user saved | Reviewed version versus current authorised record | Refresh/review latest values and deliberately reapply; never silent overwrite |
| Duplicate-looking credit/pay | Session acknowledgement/credit evidence, approval snapshot and original receipt | Engineering/Owner reconcile exactly-once effects. Approval is not a bank transfer; do not make a compensating financial action blindly |
| Old private data appears after identity/assignment change | Current session, role, assignment and request generation | Contain access through authorised controls; retain evidence and fix scope regression before accepting recovery |
| Video missing, expired or access denied | Current attachment/scope, original expiry, object bytes and cleanup leases | Do not restore expired access, extend expiry or publish metadata for missing bytes; follow retained media/Undo rules |
| Slow but eventually successful | First/repeat action, device/network, request duration, cold starts and DB queries | Record usability impact. Do not double-click/replay writes or change timeout limits to hide it |
| CI browser installation stalls | Failed step, runner image, source-selection output and package-download timings | [prepare-browser-apt.py](../scripts/prepare-browser-apt.py) selects the reviewed archive. Preserve budgets and verify actual download cause; this is not an application regression by default |

### 5.2 Operator-assisted lost-authenticator recovery

This is a controlled operator procedure, not an app-admin feature. [The recovery policy](business-rules.md#br-008) governs it. Preparation and synthetic drills do not authorize a live reset; first bind the deployment and obtain the applicable provider/database authorization.

1. Open an access-controlled recovery case. Independently verify the person against trusted records; record the verifier, approving operator, case reference and timestamps. Never collect passwords, codes or TOTP secrets in the case.
2. Verify the AWS account, Singapore region, pool/app client, staff UUID, immutable issuer/subject and provider Username. Use `python -m app.auth.admin check-config` in the reviewed environment. Confirm the same enabled provider identity and verified recovery address. Stop on a mismatch, pending email change or unsupported second factor; pool-wide software-token MFA stays required.
3. In a reviewed database transaction, lock the exact authentication account then mapped identity and set that identity inactive, matching all bound identifiers. The existing identity trigger advances its epoch and closes its sessions; old challenge flows also lose authority. Record the transaction receipt and verify revocation. Do not deactivate the Trainer/client business records or touch another identity.
4. With separately authorized operator IAM, call Cognito `AdminUserGlobalSignOut`, then `AdminDeleteSoftwareToken` for that exact pool/Username. Retain sanitized request IDs and CloudTrail evidence in the case. Never replace the user/subject, disable pool MFA or use MFA preference changes as a factor reset. Runtime IAM receives no administrator recovery permissions.
5. Confirm the same enabled subject has no old software-token registration. A timeout or uncertain response leaves the application identity inactive; reconcile the exact action and provider/audit evidence before proceeding. Do not blindly repeat a reset that could erase a newly enrolled authenticator.
6. After confirmed reset and a coordinated handoff, restore only that mapped identity to active in a reviewed transaction. Its epoch advances again; old sessions/flows stay invalid. The staff member signs in, enrolls their own authenticator and proves fresh sign-out/re-login. Check required MFA and close the recovery case with evidence; suspend access again if verification fails.

The full backend gate includes [the synthetic recovery drill](../backend/tests/test_mfa_recovery_drill.py) and [actual HTTP worker crash/restart tests](../backend/tests/test_process_restart.py), using isolated PostgreSQL. Cognito reset responses are SDK-stubbed; an authorized real-provider recovery and deployment-specific execution receipt remain separate acceptance.

## 6. Deployments and rollback

### 6.1 Verified image publication

Normal main verification and Pages demo publishing do not queue an AWS image. For an independently authorized image candidate, open **Build and scan the verified AWS image candidate** in GitHub Actions, select `main`, and enter its exact 40-character commit SHA as `source_sha`. A mismatch stops before verification; main advancing later does not change the run’s selected commit. `AWS_IMAGE_RELEASE_ENABLED=true` must remain explicitly configured. The workflow reruns the complete frontend, backend and API-browser gates for that SHA before requesting the existing `aws-test` environment approval. Inspect the run SHA and successful gates before approving; cancel an obsolete candidate instead of approving it to clear a queue.

The image retains its commit/run/attempt binding, exact AWS account/role checks, scan and receipt evidence. Historical candidates retain their original provenance rules; new manual candidates require all three verification gates. Image publication does not deploy Lambda, run migrations or authorize customer/provider actions. AWS release workflows remain serialized separately from ordinary verification/demo publishing.

### 6.2 Deployment preparation and acceptance

| Step | Required evidence |
| --- | --- |
| Bind target | Actual AWS account/region and existing Lambda, API, Cognito, database, bucket and frontend identities; stop on mismatch |
| Bind source/artifacts | Exact verified source, release workflow/run/attempt, image digest and separately built frontend artifact |
| Check compatibility | Current/outgoing application, migration heads, populated data, grants, feature flags and tested rollback candidate |
| Check scan and backup | Exact artifact findings and disposition; recoverable populated data and reviewed recovery plan |
| Review action | Concrete operator change plan, intended resources/effects and applicable approval; old bootstrap approvals are not reusable |
| Apply and verify | Only approved actions; record results, actual deployed identity, readiness and arranged role/UAT checks |

[Release image](../backend/infrastructure/release_image.py), [image acceptance](../backend/infrastructure/image_acceptance.py), [private runtime](../backend/infrastructure/private_runtime.py), [database migrations](../backend/infrastructure/database_migrations.py) and [hosting operator](../backend/infrastructure/hosting_operator.py) are source owners, not a sequential script list to execute blindly. Their retained contracts and fingerprints may bind earlier artifacts. Reconcile and review a new release binding; never rewrite history or bypass a source mismatch just to make publication pass.

Frontend and Lambda releases are separate. Preserve reviewed API origin/CORS/cookies and existing resource identities. Email correction and media are default-disabled capabilities: use [Runbook configuration](runbook.md#10-configuration) for compatible activation. Source-present cleanup commands do not establish scheduled cloud cleanup or accepted media processing.

### 6.3 Rollback

Identify the failing artifact/configuration and the last verified compatible candidate. Compare current schema, new records, outstanding commands and external identity/media effects before selecting rollback. Stop incompatible new writes only through a reviewed change. Restore the approved application/configuration target, verify actual deployment/readiness and reconcile outstanding receipts.

Code rollback does not reverse credits, approvals, sent emails or committed database changes. After email corrections exist, rollback must use correction-aware code; disabling new corrections does not remove pending history. Do not downgrade a populated schema that would discard attribution, receipts or action evidence. If no safe backward path exists, prepare a reviewed forward fix or restore plan instead.

## 7. Data protection and restore

The retained14-day backup/PITR target and capacity assumptions are planning requirements, not observed settings. Before handover, verify actual RDS retention/latest restorable time, encryption, access, snapshot ownership, media protection/retention and tested restore permissions. Define measured recovery-point/recovery-time objectives with the Owner; record costs and who receives failed-backup alerts.

1. Authorise the specific drill/incident recovery and identify the cutoff, affected database/media/identity state and target environment. Preserve current evidence.
2. Select a consistent recoverable point and restore **first to a separate isolated environment**, with external messages/provider writes and destructive cleanup disabled through reviewed configuration.
3. Verify schema/grants, people/purchases/session identities, credits/approvals, assessment revisions, command receipts, media references/bytes and original expiries. Reconcile Cognito revocations/email changes and external effects that occurred after the selected recovery point.
4. Prevent restored stale sessions or command history from reviving revoked access or replaying already-completed effects. A database restore is not permission to roll back provider identity or resend messages.
5. Measure actual recovery duration/loss, run arranged read/write/permission checks and record unresolved differences. Obtain approval before any cutover and retain a rollback route for that cutover.

Do not shorten original media expiry, resurrect expired data or delete retained audit evidence as an unreviewed cleanup shortcut. Restore drills, backup/alert activation and migration recovery remain pending until actual environment-specific receipts exist.

**Draft recovery targets and actual capability.** RPO means the maximum agreed data-loss window; RTO means elapsed time from incident declaration to safe restoration, including validation and reconciliation. The Owner has not agreed either. For planning review only, propose a compatible static/application release recovery within60 minutes during agreed coverage, relational data RPO15 minutes and RTO4 hours, and media recovery within8 hours with any allowable media-loss window explicitly decided before approval. These are proposed targets, not measured achievements or purchased-service guarantees. No silent loss or duplicate replay of credits, approved remuneration, receipts or identity changes is acceptable merely because a backup meets its nominal RPO. Reject/revise a target if current backup mechanisms or reconciliation cannot safely meet it.

The retained14-day RDS backup/PITR objective describes retention, not a15-minute loss guarantee. Inspect actual retention, earliest/latest restorable times, encryption/key access, restore grants and media protection in the intended account before committing to targets. The checked-in TEST foundation's one-day baseline and historical changes are not proof of present settings. Cognito state and private object bytes are outside a PostgreSQL backup. Recovery operator, backup operator, escalation destination, coverage, approved targets and provider support arrangements remain unassigned. Actual RPO/RTO are **not measured**.

**Expand the existing five-step procedure as follows before a drill.** For step1, record drill/incident ID, approving Owner, operator, original source/image digest, account/region/resource IDs, PostgreSQL version, Alembic heads, backup point and incident cutoff. Decide whether the fault is code-only or data corruption; a schema-compatible release rollback may avoid data restore. Preserve current read-only evidence and do not overwrite the only surviving copy. Wrong account, unknown artifact/schema or unavailable decryption keys blocks the drill.

For step2, use a separately named isolated database and private media target with reviewed network/credentials. Deny real Cognito/email/provider writes, scheduled processing, destructive cleanup and automatic command replay before restoring data. Verify those denials; a flag label is not isolation evidence. Use synthetic records for local rehearsal. Any customer-data copy or AWS snapshot/PITR action needs its own reviewed authority and restricted evidence storage. Restore using the supported PostgreSQL/RDS mechanism selected for that target; this document supplies no blanket production command. Record backup checksum/identity, tool/server versions, recovery-point timestamp, restore start/end and errors. Never restore over the current database as a first diagnostic attempt.

For step3, inspect schema and migration heads before applying any forward change. Validate foreign keys and unchanged stable people/purchase/session identities, immutable assessment revisions, purchased terms, exactly-once credit debits, approved pay snapshots, typed Undo dependencies and actor-private receipts. Verify original media bytes/checksums, links, expiry and outstanding leases; a database row alone does not prove an object can be restored. Reconcile Cognito subject/email/revocation changes since the restore point. Do not make raw SQL edits, rewrite applied migrations or manufacture missing audit evidence to pass validation.

For step4, retain one authoritative writer. Establish which commands/providers committed after the backup point and which outcomes remain unknown, and prevent restored old state from authorizing duplicate effects. In isolated synthetic fixtures, verify committed receipt replay has no second effect, interrupted transactions remain rolled back, revoked accounts cannot regain access, foreign records stay denied and expired media cannot be resurrected. Authentication-token key compatibility and any required session invalidation need a reviewed plan. A process-restart test against the same database is useful existing evidence, but **is not a backup restore**.

For step5, record actual data-loss interval, elapsed incident-to-safe-service time and all discrepancies against the proposed targets. The drill is blocked if grants/identity/media cannot be reconciled, writes cannot be fenced, data is exposed or validation fails. Keep the isolated target closed, preserve failures and decide recovery/rollback with the Owner rather than reopening writes. A later separately approved cutover must verify artifact/schema binding, readiness, roles, fresh reads, monitoring and operator acceptance; actual AWS/provider/device checks remain separate. No live cutover or restore is authorized by the draft.

**Evidence still to obtain.** Keep a restricted record with drill ID/date, named operator/approver, environment/resource identities, artifact/schema versions, backup mechanism and point, key/grant access checks, proof of isolation, restore timings, measured loss/downtime, integrity/permission/receipt/media results, post-backup identity/effect reconciliation, unresolved discrepancies, cutover/rollback decision and next drill date. For this draft every execution/result field is **not run/not measured**, and approval fields are **unassigned**. Existing [process-restart tests](../backend/tests/test_process_restart.py) prove their stated crash/transaction behavior only. No tested restore procedure, agreed target, active alert or recipient-delivery acceptance is claimed until actual receipts exist.

## 8. Domain, DNS and HTTPS

Confirm registrar, authoritative DNS owner, AWS account, approved hostnames, CloudFront distribution/static origin and API endpoint separately. Do not infer a current hostname or certificate ARN from historical artifacts.

Before a change, retain the exact DNS/TTL/validation baseline, ACM certificate coverage/region, routing and rollback contact. Preserve MX/SPF/DKIM/DMARC records. Keep DNS validation records needed for managed renewal. Verify trusted HTTPS, permitted redirects, frontend-to-API origin, secure cookies, CORS and private-media behavior on each approved hostname.

For certificate/routing incidents, distinguish DNS validation/CAA, certificate coverage/expiry, distribution/API association and stale caches. Correct the identified prerequisite through the authorised operator, then verify actual issuance and availability. Initial issuance is not proof of future renewal; monitoring and renewal evidence must be recorded separately. No DNS migration or production-domain cutover is authorised by this runbook.

## 9. Operational records and handover

For each incident/change retain: named owner, Singapore/UTC timestamps, environment/account/resource identities, source/run/artifact/digest, reason/scope, applicable BR/UAT IDs, redacted evidence, approval, observed before/after behavior and remaining actions. Store completed user worksheets and sensitive incident evidence in restricted records, not in blank worksheet masters or public PRs.

Before handover, name primary/backup responders; confirm access/MFA/billing; reconcile current artifacts and dependency findings; exercise role UAT, alert delivery, rollback and restore; document residual risks and obtain Owner acceptance. [Code owners](code-owners.md) locates implementation modules, not on-call people. M7 processing, public/member delivery and M10 monitoring remain governed by [Progress](../PROGRESS.md), not completed by this document.

## 10. Configuration

Local prototype development uses `VITE_PORTAL_MODE=demo` and an empty `VITE_API_BASE_URL`. API builds explicitly select API mode and the reviewed API origin. Unsupported API operations do not fall back to demo storage. Public frontend configuration is separate from server secrets; never put credentials in a Vite bundle.

Real-API tests create temporary Docker PostgreSQL databases, private buckets in the pinned Docker S3-compatible service and synthetic accounts. They require no production database, AWS credentials or Lambda redeployment. The local signed-token provider substitutes Cognito; FastAPI, PostgreSQL and object IO are real. Local storage compatibility does not prove AWS S3 deployment acceptance. The verifier owns isolation checks and cleanup; browser storage uses loopback port4181 or the internal Compose hostname.

Pending Trainer email correction is disabled by default (`FITFINITY_STAFF_EMAIL_CORRECTIONS_ENABLED=false`). Enable it only after all serving application instances understand superseded requests and the forward migration is verified. Once corrections exist, rollback requires a correction-aware application; old pending-request readers are incompatible, and populated schema downgrade refuses evidence loss. Disabling creation does not prevent account holders from finishing existing verification.

Protected media is disabled by default. An authorized deployment must explicitly set `FITFINITY_MEDIA_ENABLED=true` and `FITFINITY_MEDIA_BUCKET` for an existing private bucket; source code does not create AWS resources. The runtime uses its workload identity and Singapore S3 endpoint. Reviewed bucket CORS must permit only the staff origin, GET/PUT/HEAD and the required content-type/checksum/conditional-write headers. Test endpoints and synthetic credentials exist only in test fixtures. `python -m app.library_cleanup` performs a bounded cleanup sweep after configuration; scheduling, grants and production activation remain release tasks in Progress. It retains durable work after failure and never deletes a library object while it is attached or its upload lease remains valid. `python -m app.session_media_cleanup` similarly performs a bounded session-media sweep, respecting package-deletion Undo holds, original fixed expiry and worker leases. Both commands require separate release activation; source integration does not schedule them.

Prepared environments may reuse `FITFINITY_BROWSER_BACKEND_IMAGE`, `FITFINITY_BROWSER_RUNNER_IMAGE` and `PLAYWRIGHT_BROWSERS_PATH` with matching source/engine inputs. Keep public CA/proxy settings and TLS verification intact; cloud-specific trust setup stays outside tracked source. If Docker or trust is unavailable, record the blocker rather than substitute SQLite or a simulator.
