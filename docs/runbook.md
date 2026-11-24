# Fitfinity operations runbook

Operational proposals remain draft; source review **3 November 2026**, PR120 candidate `7f36ae8`. For authorised operators of the developer AWS environment and future production releases. [Security infrastructure](security/security-infrastructure.md) maps controls and remaining layers. This document owns operating procedures; it does not claim that current source is deployed or planned monitoring is active. Confirm the target account, environment and deployed revision before acting. [Progress](../PROGRESS.md) owns current evidence and pending work, [Business rules](business-rules.md) owns rules, and [Development](development.md) owns local setup and verification commands.

Navigation: [Access](#1-ownership-and-access) · [Routine checks](#2-routine-checks) · [Dependencies](#3-dependency-maintenance-and-dependabot) · [Monitoring](#4-monitoring-and-observability) · [Incidents](#5-incident-response-and-recovery) · [Releases](#6-deployments-and-rollback) · [Restore](#7-data-protection-and-restore) · [DNS](#8-domain-dns-and-https) · [Handover](#9-operational-records-and-handover).

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

[versions.md](versions.md) is the dependency inventory of locked application/transitive dependencies, images, browser engines and CI pins, with manual patch guidance and explicit gaps for deployed/OS versions. Update it alongside dependency changes using `npm ci` → `npm run versions:refresh` → review the diff → `npm run verify:dependencies`. The blocking consistency gate validates inputs before regenerating tables; manually review prose, security-override removal criteria and deployment boundaries.

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
3. After a locked install, run `npm run versions:refresh`, review `docs/versions.md` and run `npm run verify:dependencies`. PR120 implements generated tables/fingerprints and a blocking freshness/consistency gate; explanatory prose and deployed state remain reviewed manually. No automatic artifact SBOM is claimed. Preserve unrelated pins and verify hashes; do not use forced blanket upgrades.
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

OpenTelemetry, Grafana, measured latency budgets, SLOs, alert receivers and backup/restore monitoring remain [M10 work](../PROGRESS.md#m10-work-packages--planned). No telemetry exporter or dashboard installation is claimed.

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

The Actions sidebar uses Title Case with CI, AWS and Legacy AWS prefixes. Open Actions → select a workflow → select a run → Summary to read What It Does, When To Use It and What To Expect. The guide appears after its publishing step runs; queued, rejected-before-guide or approval-waiting jobs may not show it yet. Shared application verification also explains the parent staff-demo behavior for PR runs that skip publishing. The sidebar itself has no custom description field. Workflow filenames and job/check names remain stable: merge protection and release receipts depend on those identities. There is no automatic AWS deployment after CI. Legacy means a developer-specific earlier procedure retained for explicit diagnosis/recovery, not a step to run during every release.

| Workflow | Trigger and purpose | Needed when |
| --- | --- | --- |
| [CI - Verify And Publish Staff Demo](../.github/workflows/pages.yml) | PR/main/manual; runs application verification, then publishes the demo on main | Routine source validation and demo publishing; not the AWS site |
| [CI - Application Verification](../.github/workflows/verify.yml) | Called by other workflows; unit, lint, backend, browser and real-API groups | Shared required verification; not a separate manual deployment |
| [CI - Infrastructure Verification](../.github/workflows/infrastructure.yml) | Called by AWS workflows or manually; offline operator regressions | Infrastructure safety checks without AWS changes |
| [CI - CodeQL Security Analysis](../.github/workflows/codeql.yml) | PR/main, weekly Monday09:00 Singapore or manual; JavaScript/Python analysis | Continuous code security scanning |
| [AWS - Prepare Release Evidence](../.github/workflows/aws-release-prepare.yml) | PR/main/manual; builds frontend/runtime evidence and reviewed packages | Release preparation; builds do not publish or deploy to AWS |
| [AWS - Observe Current Release](../.github/workflows/aws-release-observe.yml) | Manual; reads current Lambda/hosting/RDS metadata | Readiness and diagnosis; does not query private SQL schema |
| [AWS - Build Scan And Publish Image](../.github/workflows/aws-image.yml) | Manual; verifies source, builds/scans and publishes image candidate | A new approved image; publication alone does not switch Lambda |
| [AWS - Release Maintenance](../.github/workflows/aws-maintenance.yml) | Manual; pause/drain evidence, maintenance state and RDS snapshot/check | Controlled release maintenance and recovery; mutation depends on mode |
| [AWS - Inspect Private Database Schema](../.github/workflows/aws-schema-probe.yml) | Manual; creates a temporary private worker, collects schema/grant metadata and cleans up | Fresh private database evidence; SQL observation is read-only but worker creation/deletion changes AWS |
| [AWS - Upgrade Private Database Schema](../.github/workflows/aws-schema-upgrade.yml) | Manual; creates/invokes a private migration worker and cleans up | A required reviewed forward migration, with backup and maintenance evidence |
| [AWS - Roll Out And Resume Application](../.github/workflows/aws-rollout.yml) | Manual; upload, reviewed changeset, execute/verify, resume, health and finalize | Release application artifacts and restore service; phases retain separate review/evidence |
| [Legacy AWS - Verify Developer Infrastructure](../.github/workflows/aws-verify.yml) | Manual; read-only audit of the original developer foundation | Existing developer infrastructure diagnosis; target-bound observation is the normal current release path |
| [Legacy AWS - Evaluate Existing Test Image](../.github/workflows/aws-image-accept.yml) | Manual; evaluates an already published developer test image | Earlier image acceptance/provenance investigation; no image publication |
| [Legacy AWS - Prove Private Test Runtime](../.github/workflows/aws-private-runtime.yml) | Manual; plan/collect/run/cleanup a private developer runtime proof | Earlier isolated runtime acceptance or retained-operation cleanup; not routine rollout |
| [Legacy AWS - Manage Test Hosting](../.github/workflows/aws-test-hosting.yml) | Manual; original persistent developer hosting setup/rollback/recovery | Original hosting operations or their recovery; current releases use the target-bound rollout workflow |

Keep the current verification and release stages: they separate read-only evidence, credentials, database writes, application rollout and uncertain-operation recovery. Not every workflow is used in each release. The four legacy wrappers still bind the original developer repository/account; they are not the portable client deployment interface. Retire them only after checking retained operation receipts and documenting replacement/recovery paths. Naming them Legacy neither disables them nor authorizes their execution. Existing environment approvals, enablement flags and main/source restrictions still apply.

### 6.1 Verified image publication

Normal main verification and Pages demo publication do not queue an AWS image. For an authorized release, open **AWS - Build Scan And Publish Image** in Actions. Select `main`, the intended `target` and its exact 40-character commit as `source_sha`. Set the repository enablement flag for this operation. Enter the successful exact-source main verification run as `verification_run`. The workflow authenticates that existing evidence before requesting the target's protected environment approval; it does not rerun the application suites. Check the SHA and run results before approving. [Image workflow](../.github/workflows/aws-image.yml)

The image retains its commit/run/attempt binding, exact AWS account/role checks, scan and receipt evidence. Historical candidates retain their original provenance rules; new manual candidates require all three verification gates. Image publication does not deploy Lambda, run migrations or authorize customer/provider actions. AWS release workflows remain serialized separately from ordinary verification/demo publishing.

Image publication accepts `verification_run`: select the successful `pages.yml` main push/manual run for the exact `source_sha`. The credential-free verification job checks the run/attempt, complete16-job inventory and same-source CodeQL using `release_verification.py --purpose image`; the protected image job rechecks before acquiring AWS credentials. Both retain `image-verification.json`. Changed sources require new CI; failed, missing, skipped, foreign or incomplete evidence is rejected. Build, publication and scan still execute for the candidate; source verification reuse does not reuse a prior scan or extend approvals.

Deployment verification audit: the portable image workflow now consumes existing full CI, and rollout already did. Observe, schema probe, schema upgrade and maintenance call only offline infrastructure verification. Preparation builds source artifacts but does not run the full application suite. Legacy image acceptance, private-runtime and test-hosting utilities still call full CI; they are outside the portable sequence and retain their existing recovery contracts until separately retired or adapted. Ordinary PR/main verification remains unchanged.

Public ECR incident45354391498 stopped in Docker metadata download before publication. Upstream adapter1.0.1's [release workflow](https://github.com/aws/aws-lambda-web-adapter/blob/v1.0.1/.github/workflows/release.yaml) publishes to Public ECR; its GitHub release has no binary assets and no official alternative registry was verified. The proposed authenticated-pull repair needs `ecr-public:GetAuthorizationToken` and `sts:GetServiceBearerToken`, authenticating Public ECR in us-east-1 while retaining the target's Singapore private ECR publication. Review installed role and boundary ownership before policy changes; keep tokens in a temporary private Docker configuration outside the build context and never log them. Authentication offers higher limits, not immunity to throttling. Source implements authentication and portable role/boundary token permissions. The developer role is CloudFormation-owned with no boundary. Its first policy update completed, but image45431483046 exposed an incompatible bearer-token condition; live authentication remains unaccepted; do not blindly rerun failed publication or grant public repository push/admin rights. [AWS Public ECR authentication](https://docs.aws.amazon.com/AmazonECR/latest/public/public-registry-auth.html).

ECR Public bearer-token compatibility: do not require `sts:AWSServiceName` on `sts:GetServiceBearerToken`. The [upstream report](https://github.com/aws/containers-roadmap/issues/2896) identifies missing context, matching the developer CloudTrail AccessDenied on24 November. [AWS's managed read policy](https://docs.aws.amazon.com/aws-managed-policy/latest/reference/AmazonElasticContainerRegistryPublicReadOnly.html) also grants that token action without a condition. Permit only that exact STS action on `*`; retain the Public ECR us-east-1 restriction and private ECR target/repository restrictions. This removes the service-specific restriction on token issuance; it does not add other services' API permissions, public push/admin, role assumption, deployment or secret access. Fresh portable roles and their matching boundaries must use the same corrected statement. Existing roles must be updated through their owning stack; successful template tests are not live authentication evidence.

Image identity verification uses [Buildx metadata](https://docs.docker.com/reference/cli/docker/buildx/build/#write-build-result-metadata-to-a-file---metadata-file): containerimage.config.digest binds the published manifest's config, while containerimage.digest identifies the build output and may differ across image-store/exporter implementations. Do not assume Docker image inspect Id is always the config digest. Verify the local ID against metadata, retain source labels/user/architecture checks and require matching registry/repository/tag plus recomputed manifest/config identity. An upload followed by a failed identity check is an unaccepted remote candidate, even if image_published remains false in the receipt; preserve its original run/tag and cloud_write_attempts. Do not treat it as deployed or blindly repeat/delete it.

### 6.2 Deployment preparation and acceptance

Use **AWS - Observe Current Release** on reviewed main for the selected target. After offline infrastructure checks, its protected job associates the hosting role with a read-only session policy. It reports the hosting stack ID/template digest, Lambda latest and serving alias versions/images/configuration, concurrency and RDS metadata. The 14-day report excludes runtime values, stack parameters and download URLs. The private catalog probe provides the database evidence. [Observation workflow](../.github/workflows/aws-release-observe.yml)

For database-state evidence, [read-schema.sql](../backend/infrastructure/read-schema.sql) uses a repeatable-read, read-only transaction with bounded lock/statement waits and ends with ROLLBACK. It reports the actual `public.alembic_version`, public table/column catalog, constraints/triggers/indexes, effective `fitfinity_app` table privileges and restricted-role attributes. It does not select customer records or passwords. Missing `alembic_version`, denied access or unavailable grants is evidence to investigate, not permission to bootstrap. This is a catalog receipt, not a complete schema-drift or runtime-permission acceptance proof.

Run only from an already authorized private connection to the verified target, using existing secure PostgreSQL connection configuration: `psql -X -qAt -v ON_ERROR_STOP=1 -f backend/infrastructure/read-schema.sql > schema-observation.json`. Do not put passwords/URLs in chat or shell history, and keep the resulting infrastructure metadata in the reviewed evidence location. An ordinary CloudShell terminal does not establish private RDS connectivity. The historical access operators created temporary private Lambdas and cleaned them up; no standing VPN/bastion is recorded. If no approved connection exists, prepare and authorize a narrowly scoped private probe instead of replaying historical bootstrap or exposing RDS publicly. Neither the current metadata-only workflow nor a ready role-ARN variable supplies a SQL connection.

The first read-only AWS observation ([run41981485762](https://github.com/LimYouSheng/FitfinityReact/actions/runs/41981485762),5 November2026,06:39:52UTC) found private/encrypted RDS PostgreSQL17.11 available with **one-day retention**, and a latest restorable point at06:36:16UTC. Lambda retained historical image86183723… on alias`first-test` version2 and reported`Inactive`; no invocation tested health. These are time-bound observations, not current-source deployment or restore acceptance. One-day retention matches the historical foundation template;14 days remains the proposed requirement.

For the next private SQL step, prefer an existing authorized VPC-connected operator terminal if one is identified. Otherwise prepare a dedicated temporary catalog probe in the verified database VPC/private subnets using an existing permitted database-access security group, with no public URL or ingress change. Bind the reviewed SQL and executable artifact to a digest; reject arbitrary SQL/event-supplied code; connect with verified RDS TLS; retrieve only the exact approved database secret inside the probe; execute only the read-only catalog transaction; return projected metadata and sanitized failure codes, never credentials/customer rows. Use a dedicated least-privilege role, one bounded invocation, explicit cleanup of function/role/log resources and a retained cleanup receipt. Verify current subnet/group/secret identities before generating the final resource/IAM change set. Historical names are discovery hints, not approved current bindings. The probe source and offline planner are implemented, but the probe is **not deployed**; the checked-in hosting policy permits observation but does not grant this new probe or database modification. Do not silently broaden that role.

For retention, the user has deferred14 days until **account-plan upgrade and migration to client AWS**. Keep the observed developer setting at1 day; do not retry the old change sets or upgrade the developer account just to obtain14 days. The5 November operator-executed change was rejected by RDS because the requested retention exceeds the Free Tier account-plan maximum. Subsequent supplied RDS output showed available, retention1 and no pending modifications; the user subsequently confirmed UPDATE_ROLLBACK_COMPLETE. Recheck the current stack before any future foundation update; do not replay the rejected change sets. See Journey for the original execution evidence.

After the upgrade and client-account migration, first verify the destination account/region/resource identity, account-plan eligibility, backup-storage allowance/pricing, actual deployed foundation template/parameters and pending changes. Prepare a new destination-bound change set affecting only BackupRetentionPeriod to14; preserve encryption/private access and historical developer fingerprints. Review any Conditional recreation classification against the exact property/value transition and current AWS documentation; never permit definite replacement or unrelated changes. The earlier script wrongly rejected the retention-only Conditional classification, then omitted account-plan eligibility; both lessons must inform the next operator. Do not reuse the developer plan or its ARNs, use an ad-hoc ModifyDBInstance command that leaves CloudFormation drift, or apply unrelated pending modifications. After separately authorized execution, verify actual14-day retention and recoverable points, then perform a populated isolated restore drill. Retention accumulates prospectively and does not prove restore success, agreed RPO/RTO or immediate14-day historical coverage.

The Lambda metadata receipt now has separate `latest_configuration` and `serving_configuration` entries, each with environment key names and allowlisted boolean feature flags. The serving summary comes from the alias-qualified version, not `$LATEST`; differing versions are covered by an explicit redaction regression. The first live observation41981485762 ran the older main observer, so its `feature_flags` describe latest only; run the corrected observer after merge before claiming serving flags.

`app/release_upgrade.py::upgrade_existing` prepares the populated-upgrade primitive: an exact forward source/target, database/user identity check, transaction-scoped advisory lock, bounded SQL/lock waits, one transactional Alembic chain, and explicit already-at-target recovery. It refuses bootstrap, guessed resume, stale starting versions and downgrade. It is not exposed by the staff API. The separate `app/release_upgrade_service.py` factory accepts only one exact operation identity through a private temporary worker; it rechecks a one-hour expiry before credentials and immediately before migration, sanitizes errors and reports uncertain failure without retry. Its planner renders a private worker with a distinct migration boundary. `schema_probe_setup.prepare(..., purpose="upgrade")` prepares a separate upgrade operator and runtime ceiling; the probe installer refuses that template. The manual `aws-schema-upgrade.yml` workflow and executor are prepared, disabled by default and not live-accepted. No installed upgrade role is established yet; callers still need maintenance/write exclusion, verified source/artifact binding, migration-role grants and backup authority. Actual isolated PostgreSQL probes cover the original schema with a synthetic Owner and a later client/package/session graph, competing connections, late failure rollback and lost-receipt recovery. They do not prove runtime-role permissions, every possible populated dataset, RDS restore or outgoing-code compatibility.

`schema_upgrade_plan.py` binds the known populated starting revision and current head to the complete migration-file hashes, image digest, profile and expiring intent. Its image validator recomputes the review, requires every migration hash in the publication receipt and reads a fresh complete ECR scan through `release_image_validation.py`; foreign targets, changed/missing SQL, stale source and edited reviews are refused. This is preparation/read-only evidence validation, not permission to invoke a worker. The read-only probe retains its SQL-specific image guard and cannot select the upgrade handler.28 focused migration/service cases passed locally, including real rollback and lost-response recovery; these do not establish RDS grants, maintenance, backup restoration or deployment.

The release planner binds the observed saved template and its hash to the source, image and frontend manifest. It preserves retained versions and forces zero concurrency in the forward and rollback proposals. Save the pause in CloudFormation before migration or rollout so provider rollback also keeps traffic paused. The protected release checks the actual pause, immutable artifact upload, effective provider access, template delta and separate resumption review. [Release planner](../backend/infrastructure/release_plan.py) · [Protected operations](#protected-release-operations)

[Prepare developer AWS release evidence](../.github/workflows/aws-release-prepare.yml) runs on PRs targeting main, main pushes and manual dispatch. Two independent jobs prepare the exact checkout: an API-mode same-origin frontend/PWA bundle with per-file hashes and a source migration inventory, and the production Docker `runtime` target for `linux/amd64` (including the Lambda adapter). Artifacts retain source SHA, run/attempt, logs and image inspection for14 days. No AWS credentials, ECR push, database connection or hosting change occurs. These jobs have20/35-minute limits and a separate cancellable concurrency group; they do not wait for `aws-test` approval or replace the three application gates/CodeQL. A PR receipt identifies GitHub's tested merge SHA; obtain new main evidence after merge.

Read `release-readiness.json` before planning rollout. It carries a preparation-only HOLD, the current source migration chain and its hashes. Historical bootstrap and private-runtime fingerprints identify older artifacts. The protected rollout consumes the exact frontend bytes and manifest from a successful selected main run, together with the published image and fresh catalog. The preparation runtime job retains build identity. The separate image workflow builds and scans the published ECR artifact.

After source acceptance, run the selected target's observation, private catalog and access checks. Verify a recoverable backup before a populated migration. Continue through the reviewed runtime/frontend release, resumption and health receipts. Real login, role workflows and physical-device results belong to the target's acceptance session. [Protected operations](#protected-release-operations)

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

The separate private catalog probe is now prepared in [schema_probe.py](../backend/app/schema_probe.py), with an offline [template planner](../backend/infrastructure/schema_probe_plan.py). It is not deployed or connected to the staff API. The planner takes reviewed account/region, source SHA, immutable image digest, SQL SHA256, database host/name, migration-secret ARN, two private subnet IDs, security group and an expiry within one hour; it emits a **HOLD** plan. It does not discover resources or execute AWS actions. The probe accepts only the exact compact invocation body `{"operation":"observe-schema"}` and runs the fixed catalog script through a read-only PostgreSQL session, checking database/user identity and returning sanitized failures. Its health route retrieves no credentials. The existing managed-secret loader retains pinned CA/TLS verification and the restricted migration identity. No customer rows, arbitrary SQL, bootstrap or migrations are accepted.

The release-preparation workflow accepts optional manual `probe_bindings` JSON containing only the exact metadata keys above. It produces `schema-probe-review/review.json`, `template.json` and `invoke.json` inside the existing preparation artifact. Source SHA must equal the dispatched checkout SHA and SQL SHA256 must match `backend/infrastructure/read-schema.sql`; the review records the exact compact template SHA256. No secret value belongs in this input. Image/source attestation and live network/secret discovery are still unverified by this offline package. An expired package must be regenerated and reviewed; never alter its expiry after approval.

For local preparation after obtaining reviewed metadata: `python3 backend/infrastructure/schema_probe_plan.py /path/to/bindings.json /path/to/new-review-directory --source-sha "$(git rev-parse HEAD)"`. This creates a new review directory and refuses to overwrite an existing one. It makes no AWS calls and grants no execution authority. Review the template, actual image/scan receipt and current resource identities before separately authorizing probe creation, one invocation and cleanup. The optional packaging step does not supply the missing live executor.

Before activation, verify current resource/network/secret identities, account-plan eligibility/cost, scanned image-to-source/SQL bindings and separately authorized create/invoke/delete permissions. Review any customer-managed KMS key requirement explicitly; do not broaden the hosting role. Inspect the created function's configuration, absence of Function URLs, public triggers and resource policies before invoking. The source SHA in the response is a configured label, not independent artifact attestation. Keep the sanitized catalog receipt in restricted operational evidence. Delete only the owned temporary probe stack and verify cleanup; logical expiry stops new observations but does not delete Lambda, IAM or logs. The local manual probe workflow/operator now prepares creation, collection and cleanup, but has not been activated or exercised against AWS; no current private-schema receipt exists yet. Existing one-day log retention is not immediate deletion.

The draft [manual probe workflow](../.github/workflows/aws-schema-probe.yml) defaults off unless `AWS_SCHEMA_PROBE_ENABLED=true`. It requires the `aws-test` environment and exact `AWS_SCHEMA_PROBE_ROLE_ARN=arn:aws:iam::418638389566:role/fitfinity-test-github-schema-probe`; existing hosting/image roles are not reused or broadened. GitHub variable-name inspection returned403 on15 November. A later environment read confirmed required reviewer LimYouSheng and the sole deployment-branch rule main. Variable presence remains unverified. On 15 November the operator supplied CREATE_COMPLETE and verified the original role trust, inline policy and both boundaries. The installed policy predates the VPC creator reads. Complete the reviewed in-place access update before using this role to create a private worker. Review account-plan eligibility/cost and the following grants before authorizing configuration. The create preflight refuses insufficient Lambda unreserved concurrency for the template's single reservation; it never raises the quota or silently removes that limit.

| Dedicated operator permission scope to review | Required operations / boundary |
| --- | --- |
| OIDC trust | GitHub issuer in account418638389566, audience `sts.amazonaws.com`, subject `repo:LimYouSheng/FitfinityReact:environment:aws-test`; protect that environment for approved main deployments. No new trust is installed by the source workflow. |
| Probe stack | CloudFormation CreateStack, DescribeStacks, DescribeStackResource, GetTemplate and DeleteStack for `fitfinity-test-schema-observe` only; no update of existing staff/foundation stacks. |
| Probe resources through CloudFormation | Lambda creation/configuration/tag/concurrency/read/delete for `fitfinity-test-schema-observe`; IAM create/read/inline-policy/delete/pass-role scoped to `fitfinity-test-schema-observe-runtime`, with CreateRole requiring the exact preinstalled runtime permissions boundary, with PassRole restricted to Lambda; log-group create/read/retention/delete for `/aws/lambda/fitfinity-test-schema-observe`. Review these transitive grants against the exact template; do not grant account-wide IAM administration. |
| Direct observations | STS identity; Lambda GetAccountSettings, GetFunction, GetFunctionConcurrency, GetPolicy, ListFunctionUrlConfigs, ListEventSourceMappings and InvokeFunction for the probe; ECR DescribeImageScanFindings for `fitfinity-test-api`; RDS DescribeDBInstances for `fitfinity-test-db`; regional EC2 DescribeVpcs, DescribeSubnets and DescribeSecurityGroups, plus GetSecurityGroupsForVpc on the reviewed database VPC ARN; DescribeSecret for the exact reviewed migration secret. The operator does not retrieve secret values. |
| Runtime role | Exact template policy only: current migration-secret read, probe log writes and Lambda-managed ENI permissions with the function-code denial. Customer-managed KMS needs a separate exact-key review; the current operator rejects it. Existing ECR Lambda access and actual private Secrets Manager/RDS routing remain prerequisites, not inferred from a same-VPC check. |

The offline planner renders the dedicated probe role, its operator boundary and the worker runtime boundary for the selected profile. The developer role is `fitfinity-test-github-schema-probe` and its worker boundary is `fitfinity-test-schema-observe-runtime-boundary`. The operator cannot alter either boundary, read secret values, change existing staff code or update existing CloudFormation stacks. Its runtime-role creation and PassRole are limited to `fitfinity-test-schema-observe-runtime`, with the exact runtime boundary and Lambda service condition. Both the runtime inline policy and boundary use the shared [IAM owner](../backend/infrastructure/schema_probe_iam.py); collection checks the actual runtime trust and boundary before invoking. The probe stack uses CAPABILITY_NAMED_IAM. Review setup separately; no IAM resource or GitHub activation is installed by running the planner. Setup depends on an existing GitHub OIDC provider and protected main-only `aws-test` environment. Regenerate any earlier local probe package because the named role/boundary changes its template digest. [IAM setup planner](../backend/infrastructure/schema_probe_setup.py)

Retain the developer installation and its original receipt. Use the existing-stack UPDATE procedure for its creator permissions. A fresh target can use the standalone CREATE installer after the role and policies are confirmed absent. The routine probe assumes its installed role through Actions. [Installed access update](#updating-installed-private-worker-access) · [Fresh-account setup](#first-setup-in-a-fresh-aws-account)

The standalone [network follow-up](../backend/infrastructure/schema_probe_network_check.py) reads only the previously observed egress instance health/forwarding metadata, database inbound rules, Lambda inactive reason and GitHub OIDC metadata after verifying account418638389566. It does not invoke Lambda, start the egress instance, fetch secret values or install roles. Its instance/group IDs are discovery bindings from the15 November supplied receipt, not permanent topology assumptions; re-observe if the environment changes.

After source acceptance and separately authorized configuration, use one durable32-hex operation ID throughout:

1. Publish/scan the exact accepted main image through the existing image workflow. Run release preparation manually with matching reviewed bindings and a fresh expiry; inspect its template/hash. Both producer runs must succeed on main at the same source. The workflow retrieves named artifacts from those exact run/attempts before authenticating to AWS.
2. Dispatch `aws-schema-probe.yml` with `create`, review run, image run, approved template SHA256 and operation ID. Creation only submits the owned stack. Preserve its returned stack ARN; no staff API, migration or frontend deployment occurs.
3. Once CloudFormation has completed creation, dispatch `collect` with the same inputs. It rechecks ownership/template, live digest/configuration/role/concurrency, fresh image scan and absence of public URLs/resource policies/event sources before one synchronous compact request. A failed/uncertain create is inspected, not automatically retried. No invocation retry is automatic.
4. Dispatch `cleanup` with the same reviewed operation, then `cleanup-check` with its retained stack ARN. A cleanup submission is not cleanup success; require DELETE_COMPLETE. Expiry does not block cleanup, and the workflow can validate an archived main ancestor's SQL for cleanup after main advances. An unexpected or foreign stack is never deleted. Retain the review package and operation/stack identity outside expiring Actions artifacts for operator recovery.

The receipt is metadata-only operational evidence with7-day Actions retention. Access follows repository Actions permissions; it is not a secret store or private customer-data archive. Never upload credential values or customer rows. The account's RDS schema, actual grants, populated upgrade, complete staff API/hosting rollout and physical UAT remain separate work. The probe workflow being green is not deployment acceptance.
 Actual migration/rollout and populated restore acceptance remain separate.

### 6.3 Rollback

Identify the failing artifact/configuration and the last verified compatible candidate. Compare current schema, new records, outstanding commands and external identity/media effects before selecting rollback. Stop incompatible new writes only through a reviewed change. Restore the approved application/configuration target, verify actual deployment/readiness and reconcile outstanding receipts.

Code rollback does not reverse credits, approvals, sent emails or committed database changes. After email corrections exist, rollback must use correction-aware code; disabling new corrections does not remove pending history. Do not downgrade a populated schema that would discard attribution, receipts or action evidence. If no safe backward path exists, prepare a reviewed forward fix or restore plan instead.

For an executable code rollback, review a new main revision that reverts the affected application or frontend code and preserves the deployed migration head, current grants and required data behavior. Build and scan its fresh image and frontend, authenticate its normal source verification and collect a current catalog. Use the ordinary paused release with the unchanged-schema producer set, then resume and verify health. A retained old template alone provides comparison evidence. If compatibility or schema validation fails, keep the existing release paused for a forward repair. [Release lifecycle regressions](../backend/infrastructure/verify-release-lifecycle.py)

## 7. Data protection and restore

The retained14-day backup/PITR target applies to the deferred client AWS work after account-plan upgrade and migration; it is not achieved in the developer account, whose observed retention remains1 day. Capacity assumptions remain planning requirements. Before handover, verify actual RDS retention/latest restorable time, encryption, access, snapshot ownership, media protection/retention and tested restore permissions. Define measured recovery-point/recovery-time objectives with the Owner; record costs and who receives failed-backup alerts.

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

Before handover, name primary/backup responders; confirm access/MFA/billing; reconcile current artifacts and dependency findings; exercise role UAT, alert delivery, rollback and restore; document residual risks and obtain Owner acceptance. [Code owners](code-owners/index.md) locates implementation modules, not on-call people. M7 processing, public/member delivery and M10 monitoring remain governed by [Progress](../PROGRESS.md), not completed by this document.

## 10. Configuration

Local prototype development uses `VITE_PORTAL_MODE=demo` and an empty `VITE_API_BASE_URL`. API builds explicitly select API mode and the reviewed API origin. Unsupported API operations do not fall back to demo storage. Public frontend configuration is separate from server secrets; never put credentials in a Vite bundle.

Real-API tests create temporary Docker PostgreSQL databases, private buckets in the pinned Docker S3-compatible service and synthetic accounts. They require no production database, AWS credentials or Lambda redeployment. The local signed-token provider substitutes Cognito; FastAPI, PostgreSQL and object IO are real. Local storage compatibility does not prove AWS S3 deployment acceptance. The verifier owns isolation checks and cleanup; browser storage uses loopback port4181 or the internal Compose hostname.

Pending Trainer email correction is disabled by default (`FITFINITY_STAFF_EMAIL_CORRECTIONS_ENABLED=false`). Enable it only after all serving application instances understand superseded requests and the forward migration is verified. Once corrections exist, rollback requires a correction-aware application; old pending-request readers are incompatible, and populated schema downgrade refuses evidence loss. Disabling creation does not prevent account holders from finishing existing verification.

Protected media is disabled by default. An authorized deployment must explicitly set `FITFINITY_MEDIA_ENABLED=true` and `FITFINITY_MEDIA_BUCKET` for an existing private bucket; source code does not create AWS resources. The runtime uses its workload identity and configured-region S3 endpoint. Reviewed bucket CORS must permit only the staff origin, GET/PUT/HEAD and the required content-type/checksum/conditional-write headers. Test endpoints and synthetic credentials exist only in test fixtures. `python -m app.library_cleanup` performs a bounded cleanup sweep after configuration; scheduling, grants and production activation remain release tasks in Progress. It retains durable work after failure and never deletes a library object while it is attached or its upload lease remains valid. `python -m app.session_media_cleanup` similarly performs a bounded session-media sweep, respecting package-deletion Undo holds, original fixed expiry and worker leases. Both commands require separate release activation; source integration does not schedule them. The selected routine session-recording cleanup cadence is monthly on the first day in Asia/Singapore; exact execution time is to be bound in the release plan. Seven-day playback expiry remains unchanged. The session CLI processes at most 100 items per invocation: deployment must provide bounded continuation until eligible monthly work is drained, failure retries and an observable overdue/failed-work signal. A one-minute retry eligibility timestamp does not execute a retry itself. Verify private bucket versioning/noncurrent-version retention and backup/replica coverage before claiming permanent erasure; deleting a key alone can create a delete marker. Library retention is separate and must not inherit the recording expiry. No cloud scheduler is activated by this policy update.

Prepared environments may reuse `FITFINITY_BROWSER_BACKEND_IMAGE`, `FITFINITY_BROWSER_RUNNER_IMAGE` and `PLAYWRIGHT_BROWSERS_PATH` with matching source/engine inputs. Keep public CA/proxy settings and TLS verification intact; cloud-specific trust setup stays outside tracked source. If Docker or trust is unavailable, record the blocker rather than substitute SQLite or a simulator.

For release/configuration readiness reviews, apply the [deployment readiness skill](../.agents/skills/fitfinity-deployment/SKILL.md); this runbook remains the operational command/recovery owner. A go/hold assessment grants no new AWS/provider authority.

Deployment default interpretation: the image workflow requires `AWS_IMAGE_RELEASE_ENABLED == 'true'`, manual dispatch and its source/account gates. An absent/false activation flag can be an intentional closed state, not a failure to fix automatically. Inspect actual settings separately from defaults; test activation and its reversion require a concrete scoped plan and applicable authorization. This statement does not claim the current live variable value or activate any workflow.

For source-security triage, inspect the independent CodeQL workflow and Security → Code scanning results for the exact revision. Assign each finding an owning module, exposure assessment and fix or justified disposition; preserve evidence. CodeQL scan completion alone does not block vulnerable code by severity. Baseline review and separately configured code-scanning merge rules are required before claiming that enforcement; the [security control map](security/security-infrastructure.md) records the current boundary.


### GitHub configuration for a deployment target

A target is one commercial AWS account and region, one repository and one protected GitHub environment. Use the same release source for each target. The source developer profile binds only the existing installation. For a new client, save a private `target-profile.json` with the eight required identity fields and the paired immutable GitHub IDs shown below. All example values in this section are synthetic. [Profile resolver](../backend/infrastructure/deployment_profile.py)

```json
{
  "schema_version": 1,
  "account": "123456789012",
  "region": "eu-west-1",
  "github_repository": "client-example/training-portal",
  "github_owner_id": "900123",
  "github_repository_id": "8104567",
  "github_environment": "production",
  "resource_prefix": "customer-prod",
  "secret_prefix": "customer/production",
  "runtime_alias": "live"
}
```

In **Settings → Secrets and variables → Actions → Variables**, set `FITFINITY_DEPLOYMENT_TARGETS_JSON` to an object mapping each target key to its complete profile, e.g. `{"client": <the profile object>}`. Preserve other targets when updating this map. Set `DEPLOYMENT_TARGET=client` for credential-free preparation on pull requests and main pushes in the client repository. Manual workflows accept the same key in their `target` input. Most manual forms default to `developer`, so select the intended key explicitly. The resolver checks repository identity, all profile fields and duplicate keys before selecting the environment. An absent map permits the checked-in developer profile only in the matching repository. An empty map selects no targets.

Create the exact named environment in **Settings → Environments**. Configure its deployment branches for `main` and its intended reviewers. Register the GitHub OIDC identity provider `token.actions.githubusercontent.com` with audience `sts.amazonaws.com` in the destination account. On GitHub.com, repositories created, renamed or transferred after July 15, 2026 use immutable IDs by default. In a signed-in client-owned session, obtain the IDs with `gh api "repos/$TARGET_REPOSITORY" --jq '{github_owner_id:(.owner.id|tostring),github_repository_id:(.id|tostring)}'`. Compare the subject format in repository OIDC settings. Supplying both decimal strings makes every generated role trust exactly `repo:OWNER@OWNER_ID/REPOSITORY@REPO_ID:environment:ENVIRONMENT`. Actions also checks those IDs against its server-supplied repository identity. Colons in the environment name become `%3A`. Older targets that still emit the name-only subject omit both fields. Retain the verified developer profile and check actual emitted trust before any activation. [GitHub OIDC subject formats](https://docs.github.com/en/actions/reference/security/oidc#immutable-subject-claims)

| Action on the selected target | Repository variable used in the job condition | Variable in the protected environment | IAM role name under the target account |
| --- | --- | --- | --- |
| Build and scan the image | `AWS_IMAGE_RELEASE_ENABLED` | `AWS_IMAGE_ROLE_ARN` | `<resource_prefix>-github-image` |
| Collect the private catalog | `AWS_SCHEMA_PROBE_ENABLED` | `AWS_SCHEMA_PROBE_ROLE_ARN` | `<resource_prefix>-github-schema-probe` |
| Upgrade a populated schema | `AWS_SCHEMA_UPGRADE_ENABLED` | `AWS_SCHEMA_UPGRADE_ROLE_ARN` | `<resource_prefix>-github-schema-upgrade` |
| Pause and snapshot | `AWS_MAINTENANCE_ENABLED` | `AWS_MAINTENANCE_ROLE_ARN` | `<resource_prefix>-github-maintenance` |
| Roll out and resume | `AWS_ROLLOUT_ENABLED` | `AWS_HOSTING_ROLE_ARN` | `<resource_prefix>-github-hosting` |
| Observe the existing release | Manual main dispatch | `AWS_HOSTING_ROLE_ARN` | Same hosting role with a read-only session policy |

Each role variable contains its full ARN, `arn:aws:iam::<account>:role/<role-name>`. Put the enablement flags at repository scope because GitHub evaluates each job condition before loading its protected environment. The flags apply across that repository's targets. Leave them unset or `false` until the corresponding operation is authorized, then set the relevant value to the literal `true`. Per-target role checks and environment protection still apply. GitHub supplies the short-lived OIDC credentials and workflow token. [GitHub variables context](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts#vars-context)

### First setup in a fresh AWS account

Set `REVIEW_DIR` to an existing private directory outside the checkout and save the inputs there. Start from the intended source revision. The exporter has two phases because AWS and the publisher assign identifiers that initial configuration cannot supply. Each new ZIP contains CloudFormation JSON files and a `receipt.json` with the target fingerprint, the two input file hashes and each template's byte hash. Exporting has no cloud side effects. [Onboarding command](../backend/infrastructure/portable_onboarding.py)

1. **Prepare the foundation.** Review a nonoverlapping private /16, two regional availability zones, available PostgreSQL 17 minor and instance class, storage limits, Multi-AZ, backup entitlement and egress. `nat-per-az` creates two chargeable NAT gateways. `none` provisions no external route. A private path to Secrets Manager, Cognito and other enabled services must exist for the workload. The image workflow also requires ECR basic scanning. Keep `session_hours` at 8 to match the staff runtime and Cognito refresh lifetime. Save the selected values as `foundation-inputs.json`. The example below is for offline rendering. The eventual deployed staff origin must match the media CORS rule and Cognito invitation link before enabling those features.

```json
{
  "foundation": {
    "vpc_cidr": "10.95.0.0/16",
    "engine_version": "17.11",
    "database_class": "db.t4g.micro",
    "storage_gib": 20,
    "max_storage_gib": 30,
    "multi_az": false,
    "backup_days": 7,
    "egress": "none"
  },
  "session_hours": 8,
  "staff_portal_url": "",
  "browser_origin": "https://staff.example.invalid"
}
```

```bash
python3 backend/infrastructure/portable_onboarding.py foundation \
  --profile "$REVIEW_DIR/target-profile.json" --inputs "$REVIEW_DIR/foundation-inputs.json" \
  --output "$REVIEW_DIR/foundation-review.zip"
python3 -m zipfile -e "$REVIEW_DIR/foundation-review.zip" "$REVIEW_DIR/foundation-review"
```

2. **Create the reviewed first-install stacks under client ownership.** In the destination account, use CloudFormation CREATE change sets for the unused names and inspect the resource additions, permissions and account/region guards. The application-region templates are `foundation.json`, `identity.json`, `storage.json`, `image-access.json` and `maintenance-access.json`. Use `<resource_prefix>-foundation` for the foundation. `edge.json` belongs in `us-east-1` for CloudFront WAF. Record the creating stacks and output identifiers. An existing database, pool, bucket or IAM identity enters the adoption procedure below.
3. **Initialize private credentials and the empty database once.** An authorized account administrator initializes the following fields through the client's private AWS access. Keep values inside Secrets Manager or the authorized in-account process. Record only full secret ARNs including AWS-assigned suffixes, names and version-stage metadata outside it. [Managed secret schemas](../backend/app/managed_secrets.py)

| Secret name | Initial value and owner | Consumer |
| --- | --- | --- |
| Generated by RDS | `ManageMasterUserPassword` is enabled. Read the RDS-generated `AdminSecretArn` output for the private DBA bootstrap. | Initial database administrator |
| `<secret_prefix>/database/app` | Exactly `username` set to `fitfinity_app` and a fresh independent `password` of 32–128 printable characters that matches the new PostgreSQL login | Staff runtime |
| `<secret_prefix>/database/migration` | Exactly `username` set to `fitfinity_migrator` and its own fresh matching password with the same length constraint. The private workers currently check for the default Secrets Manager key. | Catalog and migration workers |
| `<secret_prefix>/auth` | Exactly `cognito_pool_id`, `cognito_client_id`, `cognito_client_secret` from this confidential client, and `auth_encryption_keys` containing a fresh URL-safe base64 encoding of 32 random bytes as its first array element | Staff runtime |

Use `AWSCURRENT` for the initialized values. For each database secret, use the Secrets Manager console's **Other type of secret** and its two key/value fields. Generate independent random passwords in the client's approved credential manager. For the auth object, use JSON mode so `auth_encryption_keys` is an array. Obtain the confidential client secret directly from the target Cognito app client. Generate the first encryption key inside the authorized client session with 32 bytes of cryptographic randomness and URL-safe base64 encoding. Keep the session private and retain the resulting key across releases. Only the names and ARNs go into review inputs.

Open `psql -X -v ON_ERROR_STOP=1` on a private operator host with an existing `PGSERVICE` entry bound to the target RDS endpoint, database `fitfinity`, administrator `fitfinity_admin`, port 5432 and `sslmode=verify-full` with the reviewed RDS CA. Inspect `\conninfo`, current database and role. Establish that there are no existing application tables or logins to adopt. For a new database only, use the following transaction. The two `\password` prompts take the respective newly generated values without placing them in SQL, shell arguments or history.

```sql
BEGIN;
SET LOCAL password_encryption = 'scram-sha-256';
CREATE ROLE fitfinity_app LOGIN NOINHERIT NOSUPERUSER NOCREATEDB
  NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 10;
CREATE ROLE fitfinity_migrator LOGIN NOINHERIT NOSUPERUSER NOCREATEDB
  NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 3;
REVOKE ALL ON DATABASE fitfinity FROM PUBLIC;
GRANT CONNECT ON DATABASE fitfinity TO fitfinity_app, fitfinity_migrator;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO fitfinity_app, fitfinity_migrator;
GRANT CREATE ON SCHEMA public TO fitfinity_migrator;
CREATE EXTENSION btree_gist WITH SCHEMA public;
\password fitfinity_app
\password fitfinity_migrator
COMMIT;
```

In the reviewed backend's `backend/` directory on that private host, set the migration process's metadata-only environment as shown below. The private process identity reads only its target migration secret. Supply the reviewed RDS endpoint, full migration ARN, actual account, region and source migration head. Use the appropriate explicit `staging` or `production` runtime environment. First connect as `fitfinity_migrator` through its verified private `psql` session and run `ALTER DEFAULT PRIVILEGES REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC`. Complete the following operations before runtime access. The first command runs Alembic as the migrator. The second verifies the migrated head and database identity, applies any missing current-table privileges and checks the result within one transaction. A process interruption after migration can be resolved by observing that head and reconciling the grants independently. [Migration entry point](../backend/migrations/env.py) · [Runtime grant contract](../backend/app/runtime-grants.json) · [Grant reconciliation](../backend/app/runtime_grants.py)

```bash
export FITFINITY_CONFIG_SOURCE=aws-secrets-manager FITFINITY_ENVIRONMENT=production
export FITFINITY_AWS_ACCOUNT_ID="$TARGET_ACCOUNT" FITFINITY_AWS_REGION="$TARGET_REGION"
export FITFINITY_DATABASE_SECRET_ARN="$MIGRATION_SECRET_ARN" FITFINITY_DB_HOST="$DB_ENDPOINT"
export FITFINITY_DB_NAME=fitfinity FITFINITY_ALLOWED_HOSTS='["127.0.0.1"]'
export REVIEWED_SCHEMA_HEAD
alembic -c alembic.ini upgrade "$REVIEWED_SCHEMA_HEAD"
python3 - <<'PY'
import os

from sqlalchemy import text
from app.config import load_settings
from app.database import Database
from app.runtime_grants import reconcile

database = Database(load_settings(purpose="migration"))
try:
    with database.engine.begin() as connection:
        head = os.environ["REVIEWED_SCHEMA_HEAD"]
        identity = connection.execute(text("SELECT current_database(), current_user")).one()
        revisions = connection.scalars(text("SELECT version_num FROM public.alembic_version")).all()
        if tuple(identity) != ("fitfinity", "fitfinity_migrator") or revisions != [head]:
            raise SystemExit("Check the database, migration role and reviewed schema head")
        reconcile(connection, expected_migrator="fitfinity_migrator", target_revision=head, apply=True)
finally:
    database.close()
PY
```

The protected upgrade workflow starts at a known populated revision. Initial database and secret initialization are once-per-account administrator operations.

4. **Collect the hosting bindings.** Read stack outputs and resource metadata in the selected account. Foundation supplies `DatabaseEndpoint`, `DatabaseIdentifier`, `Vpc`, `AppSubnetA`, `AppSubnetB`, `ApplicationSecurityGroup`, `MigrationSecurityGroup` and `AdminSecretArn`. Cognito supplies `PoolId` and `ClientId`. Storage supplies `MediaBucket`, `ImageRepository` and `ImageRepositoryUri`. The edge stack supplies `WebAclArn`. Copy server-assigned identifiers from those owners. Code derives the runtime function, alias, database, repository and role names from the profile. Verify subnet VPC/account membership, routes, private database access and group permissions. Observe full secret ARNs via Secrets Manager metadata. The following metadata reads return the target's real outputs and full migration ARN. Use the reviewed CLI profile and application region.

```bash
aws cloudformation describe-stacks --profile "$AWS_PROFILE" --region "$TARGET_REGION" \
  --stack-name "$FOUNDATION_STACK" --query 'Stacks[0].Outputs' --output table
aws secretsmanager describe-secret --profile "$AWS_PROFILE" --region "$TARGET_REGION" \
  --secret-id "$SECRET_PREFIX/database/migration" --query ARN --output text
```
5. **Bind the first artifacts and render hosting.** Use `aws-release-prepare.yml` and `aws-image.yml` for the selected target and exact accepted main SHA. Record the frontend's `frontend_build.manifest_sha256` and the published scanned image digest. Compose `hosting-inputs.json` with the following keys. Replace the illustrated values with the discovered target metadata. `environment` accepts `staging` or `production`, and `stage` names the API stage. Keep optional features disabled until the target's grants and public origin are verified.

```json
{
  "hosting": {
    "database_secret": "arn:aws:secretsmanager:eu-west-1:123456789012:secret:customer/production/database/app-aB1cD2",
    "auth_secret": "arn:aws:secretsmanager:eu-west-1:123456789012:secret:customer/production/auth-aB3cD4",
    "db_host": "customer-prod-db.abc123.eu-west-1.rds.amazonaws.com",
    "pool": "eu-west-1_Example123",
    "client": "exampleclient123",
    "subnets": ["subnet-11111111111111111", "subnet-22222222222222222"],
    "security_groups": ["sg-33333333333333333"],
    "image": "123456789012.dkr.ecr.eu-west-1.amazonaws.com/customer-prod-api@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "environment": "production",
    "stage": "staff",
    "features": {"media": false, "invitations": false, "email_changes": false}
  },
  "frontend_prefix": "releases/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb/cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
  "edge_arn": "arn:aws:wafv2:us-east-1:123456789012:global/webacl/customer-prod-login-cloudfront/11111111-2222-3333-4444-555555555555"
}
```

```bash
python3 backend/infrastructure/portable_onboarding.py hosting \
  --profile "$REVIEW_DIR/target-profile.json" --inputs "$REVIEW_DIR/hosting-inputs.json" \
  --output "$REVIEW_DIR/hosting-review.zip"
python3 -m zipfile -e "$REVIEW_DIR/hosting-review.zip" "$REVIEW_DIR/hosting-review"
```

6. **Establish the hosting and access owners.** The authorized client administrator reviews and creates the initial `<resource_prefix>-login` stack from `hosting.json` with the dedicated `<resource_prefix>-hosting-cloudformation` service role and the profile's hosting OIDC role. First-install authority and an appropriately scoped initial service role must already be available in the account. The routine release policy is prepared from the resulting stack's physical resources. Its update path requires that existing stack and attached role. Retain the stack ID, complete resource inventory, original template and access-owner template privately. Verify the distribution's `FrontendDomain` and set the Cognito `StaffPortalUrl` and storage CORS origin through their owning stacks before switching on invitations or media. The source hosting template serves the CloudFront domain. Use the saved release prefix for the exact frontend artifact, then complete the protected release, health and verification steps below before handover.
7. **Install missing scoped access once.** For a new target with no probe or upgrade roles, prepare their two independent bundles using the verified full migration secret ARN and the VPC ID from the database subnet group. Review each generated `template.json`. On authorized execution the corresponding `fitfinity-install-probe-iam.py` or `fitfinity-install-upgrade-iam.py` checks the AWS caller, OIDC provider and a three-addition CREATE change set, then verifies the resulting role and both boundaries. Set the protected environment role ARNs from actual installed identities. Review hosting/release access from the observed stack as described below. The existing developer probe installation already has its successful verification receipt.

```bash
python3 backend/infrastructure/schema_probe_setup.py --purpose probe \
  --profile "$REVIEW_DIR/target-profile.json" --migration-secret-arn "$MIGRATION_SECRET_ARN" \
  --vpc-id "$DATABASE_VPC_ID" --output "$REVIEW_DIR/new-probe-access"
python3 backend/infrastructure/schema_probe_setup.py --purpose upgrade \
  --profile "$REVIEW_DIR/target-profile.json" --migration-secret-arn "$MIGRATION_SECRET_ARN" \
  --vpc-id "$DATABASE_VPC_ID" --output "$REVIEW_DIR/new-upgrade-access"
```

For an authorized first Owner in a fresh target, use the designated verified identity in that client pool. Inside its private operator runtime with the target's authentication and database configuration, `python -m app.auth.admin check-config` validates the client settings and `python -m app.auth.admin bootstrap-owner --subject "$OWNER_SUBJECT" --owner-name "$OWNER_NAME"` links the first Owner. An existing Owner uses the existing identity. Keep the subject, name and any provider effects in the client's operational process. [Authentication administration](../backend/app/auth/admin.py)

### Adopting an existing installation

Start the existing developer release at the observed resources using a reviewed copy of the checked-in developer profile, reconciled with current GitHub OIDC metadata. Retain its database, Cognito pool and Owner, media/frontend buckets, edge ACL, deployed alias, secrets and their existing versions. Match the actual caller, account, region, stack ID and current template against the selected profile. If an existing client's names or ownership diverge, resolve that adoption with its owner before consuming the resources. The first-install templates describe new resources.

Run the protected `aws-release-observe.yml` on main. Use its stack/template digest, current Lambda revision, serving alias/version/image, prior concurrency, RDS identifier and physical resource ID. Obtain the catalog from the private probe. Resolve any remaining subnets, groups, exact secret ARNs, Cognito IDs and IAM owner stack/resource IDs from their actual owners. Do not repeat the completed developer probe IAM installer or run the empty-database/Owner bootstrap on this installation. Reconcile missing permissions against the original IAM owners. Reuse the observed resource identities for maintenance, schema change, rollout and recovery.

The developer-only `aws-verify.yml` audit, `aws-image-accept.yml`, `aws-private-runtime.yml`, `aws-test-hosting.yml`, and the historical `test-*` database/auth/foundation/egress bootstrap and recovery contracts bind original developer resources or artifacts. Their retained receipts remain historical evidence. The portable image entry point is `aws-image.yml`, followed by the target-aware observation, maintenance, schema and rollout workflows. Routine deployment proceeds through reviewed Actions dispatches. A normal main push produces verification and preparation evidence.

Observation reports distinguish `true`, `false`, `unset` (variable absent) and `invalid` (present but not a recognized report boolean); invalid values are never echoed. These labels describe configuration, not provider acceptance. Current application settings default media and pending-email corrections off. The email-correction flag controls superseding a pending address-change request, not all email-change endpoints. Enable media only with the reviewed private bucket and runtime role/boundary access; apply intended feature configuration with the reviewed release. A successful observation deliberately remains HOLD until the other release evidence is established.

AWS credential steps compare the Action's supported `aws-account-id` output to the reviewed target before subsequent operations. Missing or wrong accounts stop the job. The pinned Action does not support `allowed-account-ids`; do not reintroduce that ignored input. Operators retain their own account/role checks. No credential Action version or runtime requirement changes in this repair.

#### Updating installed private-worker access

Before generating an update, read `gh api "repos/$TARGET_REPOSITORY/actions/oidc/customization/sub"` and compare its subject prefix with the exact installed role trust. On24 November2026, developer repository metadata reported `use_immutable_subject: true` and prefix `repo:LimYouSheng@141623519/FitfinityReact@1353173586`; its original verified probe template retained name-only trust. For the next reviewed developer configuration, add `github_owner_id: "141623519"` and `github_repository_id: "1353173586"` to the private target-profile copy and the matching `developer` entry in `FITFINITY_DEPLOYMENT_TARGETS_JSON`. Recheck those IDs before use. Keep the original checked-in profile and installation receipt as historical evidence; the revised profile has a new fingerprint, so obtain fresh receipts. Do not disable immutable subjects or add wildcard trust.

For an installed probe or upgrade role, use its original IAM stack and the existing authorized IAM-owner session. Retain the exact stack ARN, its Original template body as JSON, and the observed RDS subnet group's VPC ID. Cross-check the account, region, database and VPC against the selected target. The developer probe's verified original template has SHA256 `e8a2e59127edea9506ba27be52761106fe032ed3cf2de2257da6650b906a2ca8`. The original installation receipt remains evidence for that version.

For the developer probe, prepare the reviewed update locally using the existing IAM stack's ARN. For an existing upgrade stack, select `--purpose upgrade` with that stack's own ARN, template and output directory.

```bash
python3 backend/infrastructure/schema_probe_setup.py --purpose probe \
  --profile "$REVIEW_DIR/target-profile.json" --migration-secret-arn "$MIGRATION_SECRET_ARN" \
  --vpc-id "$DATABASE_VPC_ID" --installed-stack-arn "$PROBE_ACCESS_STACK_ARN" \
  --installed-template "$REVIEW_DIR/probe-access-original.json" \
  --output "$REVIEW_DIR/probe-access-update"
```

Review `review.json` and the proposed `template.json`. Both the operator inline policy and its boundary must grant regional `ec2:DescribeVpcs` and `ec2:GetSecurityGroupsForVpc` on that single VPC ARN. The existing subnet and security-group reads are scoped to the same region. Where the selected profile supplies immutable IDs, the reviewed update may also replace the exact name-only subject with the exact ID-bearing subject for the same repository and environment; audience, provider and all other trust conditions must remain identical. The upgrade operator additionally needs `lambda:ListTags` on the exact staff function to observe its pause and snapshot markers. The worker runtime boundary owns Lambda's runtime networking permissions. [Lambda VPC permissions](https://docs.aws.amazon.com/lambda/latest/dg/configuration-vpc.html) · [EC2 permission scopes](https://docs.aws.amazon.com/service-authorization/latest/reference/list_ec2.html) · [Lambda tag visibility](https://docs.aws.amazon.com/lambda/latest/dg/configuration-tags.html)

After separate IAM-owner authorization, execute the generated `fitfinity-update-probe-iam.py` or `fitfinity-update-upgrade-iam.py` once. It matches the original stack ARN and template hash, the physical role and policies, and their effective IAM documents. Its CloudFormation UPDATE permits only in-place modifications to `OperatorRole` and `OperatorBoundary`. It compares the AWS change-set template to the reviewed candidate, checks the change set completed on the original stack, and reads the trust, inline policy and both policy versions back from IAM. Retain the journal with its operation and change-set IDs. If interrupted, inspect that change set, stack events and IAM readback before any further write. The developer's updated grants still need live verification. [IAM setup operator](../backend/infrastructure/schema_probe_setup_operator.py)

### Protected release operations


For a routine release, use the selected target's verified main build, image, live observation and private catalog. Keep the original evidence and operation identity throughout each stage. The protected phases consume their corresponding enablement flags and installed role ARNs from the configuration table above.

For upgrade preparation, the credential-free release workflow accepts optional `upgrade_bindings`, using the exact account/region/source/image/database/secret/network/expiry fields plus `operation_id`, `from_revision` and `to_revision`. It retains `schema-upgrade-review/review.json`. The protected upgrade workflow selects that successful manual preparation run and matching image run. Modes are explicit: `create`, `inspect`, `invoke`, `cleanup`, `cleanup-check`. Supply the retained stack ARN and previous upgrade run for inspection/invocation; invocation also takes `catalog_run`, `maintenance_run` and the reviewed `snapshot_arn`. Supply a fresh private probe receipt from this source and target using the currently packaged `read-schema.sql`. Earlier SQL digests fail the artifact check. Select the successful same-source maintenance `snapshot-check` run in state `snapshot_ready`. The executor verifies its operation, source, profile, deterministic snapshot ARN, live ownership tags, current physical database and the two staff-function markers. The available encrypted manual PostgreSQL snapshot must have been created after the catalog observation and at or after the recorded drain deadline. The hosting template and staff function must both still record zero concurrency. After an upgrade, collect a fresh private catalog at the destination head for rollout.

Before a cloud mutation, the operator flushes an exclusive local receipt and atomically replaces it on each transition. Before invocation it additionally marks the owned worker with the operation ID. Lost responses, failures or a stale earlier receipt cannot trigger an automatic repeat; inspect the actual schema through the read-only probe. Metadata inspection explicitly reports that it has not observed the database outcome. Cleanup is a separate owned-resource action and remains possible after expiry; archived migration bytes are read from an approved ancestor without executing old Python. Receipt upload runs even after failure. These guards are locally tested with simulated AWS, not live acceptance. New staff table grants and runtime/provider permissions must still be reconciled before switching the application onto an upgraded schema.

Portable hosting bindings may include `features` with exactly three boolean keys: `media`, `invitations` and `email_changes`. Omitting the object leaves all three disabled. Media enablement binds the target storage bucket and grants object get/put/delete only under `library/` and `recordings/`; invitation enablement grants only DescribeUserPool, AdminGetUser and AdminCreateUser on the selected pool. The role and permissions boundary match. Before activation, verify the actual bucket, CORS origin and Cognito invitation link against the deployed staff origin. Rendering this configuration does not activate features or send invitations. Current runtime table permissions are owned by `backend/app/runtime-grants.json` and verified/applied by the private upgrade service, not by replaying the historical bootstrap.

The prepared `release_maintenance.py` state machine retains original intent before provider writes, verifies the function revision and physical database ID, and uses cloud markers to prevent replay. Prepare `maintenance_bindings` with the existing profile/source/operation/expiry, function revision, database resource ID and previous concurrency, plus `hosting_stack_arn` and `hosting_template_sha256` from the exact hosting observation. Review its generated digest and separate IAM template. After protected `pause` → `inspect`, run `record-pause-create` → `record-pause-inspect` to review the concurrency-only change set, then `record-pause-execute` → `record-pause-verify`. Each subsequent step uses the original review and the preceding receipt run. On an uncertain response, use inspection of the original operation; never rerun creation/execution blindly. The receipt retains metadata and nested operation identity, not raw templates. Only after the saved hosting template has concurrency0 and the observed Lambda timeout has drained can `snapshot` → `snapshot-check` proceed. A failed pause that rolls back to the old concurrency is inspectable, but is not verified or eligible for migration. Read-only recovery remains available after review expiry; new writes require an unexpired review. Snapshot creation does not change automated backup retention. The disabled manual `aws-maintenance.yml` workflow uses `AWS_MAINTENANCE_ROLE_ARN`, `AWS_MAINTENANCE_ENABLED`, the selected protected environment and shared environment concurrency group. Its role now includes exact hosting-stack/change-set access for this pause, without image-update, database-credential or migration authority. Review/install that role separately before activation. Upgrade IAM additionally needs read-only access to the hosting template to confirm the saved pause. Post-rollout resumption and finalization use the separate reviewed steps below; no activation or live execution is claimed.

The manual main-only `aws-rollout.yml` inputs are `target`, `mode`, `verification_run`, `review_json`, `review_sha256`, `producer_runs_json` and optional `prior_run`. Use the successful exact-current-main `pages.yml` push/manual run ID for `verification_run`. Each dispatch authenticates that run's full 16-job verification inventory, its exact attempt and the current-source CodeQL run before obtaining AWS credentials. The resulting `rollout-verification.json` accompanies the operation receipt. Reuse completed verification for each step on the same main SHA. This preserves existing source gates and the one-hour write-review expiry. [Verification consumer](../backend/infrastructure/release_verification.py)

For `producer_runs_json`, use string run IDs under `frontend`, `image` and `catalog`. For a populated upgrade add the confirmed `upgrade` producer and the post-upgrade catalog. Omit `upgrade` for an observed unchanged schema. In the private review directory save the exact producer files `release-readiness.json` and `fitfinity-image-candidate.json`, and the current, already paused hosting `TemplateBody` as `paused-hosting.json`. Create `rollout-fields.json` with `operation_id` (32 lowercase hex characters), `expires_at` (Unix seconds within one hour), observed `stack_arn`, and the original `maintenance_marker`. For feature changes, add `feature_values` containing the reviewed hosting bindings including the three explicit booleans. With an external boundary also include `external_boundary` with the owning `stack_arn` and `logical_id`, and save its original TemplateBody as `boundary-owner.json`. Keep these files outside Git and the workflow inputs.

Compute the template and review hashes locally using the same planner as Actions. Inspect the candidate template and the public configuration in the resulting `rollout-review.json`. Supply only that review JSON and its printed digest to the workflow. The protected executor independently authenticates producer runs, source and target. [Template planner](../backend/infrastructure/release_plan.py)

```bash
PYTHONPATH=backend/infrastructure python3 - "$REVIEW_DIR" <<'PY'
import json
import sys
from pathlib import Path
from deployment_profile import fingerprint, load
from release_observation import digest
from release_plan import prepare

directory = Path(sys.argv[1])
def read(name):
    return json.loads((directory / name).read_text())

profile = load(directory / "target-profile.json")
frontend, image = read("release-readiness.json"), read("fitfinity-image-candidate.json")
fields, hosting = read("rollout-fields.json"), read("paused-hosting.json")
source = frontend["source_sha"]
if image["revision"] != source or not image["candidate_ready"]:
    raise SystemExit("Select matching successful release producers")
if frontend["profile_sha256"] != fingerprint(profile) or image["profile_sha256"] != fingerprint(profile):
    raise SystemExit("Select producers for the reviewed target")
owner = read("boundary-owner.json") if "external_boundary" in fields else None
plan = prepare(hosting, observed_template_sha256=digest(hosting), source_sha=source,
               image_digest=image["image_digest"], frontend_sha256=frontend["frontend_build"]["manifest_sha256"],
               profile=profile, feature_values=fields.get("feature_values"),
               boundary_template=owner, boundary_template_sha256=digest(owner) if owner else None)
if owner:
    fields["external_boundary"]["template_sha256"] = digest(plan["feature_review"]["boundary_candidate_template"])
review = dict(fields, source_sha=source, profile_sha256=fingerprint(profile),
              original_template_sha256=digest(hosting), candidate_template_sha256=digest(plan["candidate_template"]))
for name, value in (("candidate-template.json", plan["candidate_template"]), ("rollout-review.json", review)):
    with (directory / name).open("x") as output:
        json.dump(value, output, indent=2)
print(digest(review))
PY
```

The paused steps are `upload`, `upload-inspect`, `create`, `inspect`, `execute` and `verify`. Upload the immutable frontend once and inspect its original receipt. Create the change set without a prior receipt, then inspect, execute and verify using the preceding original rollout receipt. The fetch phase authenticates exact producer runs before AWS credentials. Each write requires a current-source review. Read-only recovery can inspect an ancestor release with original operation and evidence hashes. Keep the verified template paused until the separately reviewed resumption succeeds.

Review both the operator policy and the CloudFormation service-role policy. The latter covers the underlying Lambda, IAM and distribution handlers for the reviewed change. The public feature configuration and effective boundary/role must agree before reopening traffic. A boundary held in another stack remains under that stack's existing authority. The routine operator reads its exact owner stack and verifies the currently installed policy version and sole runtime-role consumer. [CloudFormation permissions](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/control-access-with-iam.html) · [Release access planner](../backend/infrastructure/release_access.py)

`release_access.py` prepares replacement operator/service policies and matching permission ceilings from the reviewed profile and complete owned stack/resource metadata. It does not install them. The executor preserves the exact profile-derived CloudFormation service role and rejects drift in both stack and change set. Maintenance pause reuses the attached role implicitly; ordinary release explicitly passes it. AWS documents that [stack operators can use an attached service role without PassRole](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-iam-servicerole.html), so source change-set checks remain essential: IAM does not constrain the numeric Lambda concurrency value. Review both existing IAM owners and actual handler requirements before activation.

The prepared operator policy permits listing only the frontend bucket because [HeadObject returns403 instead of404 for a missing object without ListBucket](https://docs.aws.amazon.com/AmazonS3/latest/API/API_HeadObject.html). Object reads/writes remain restricted to its releases prefix; writes require AES256 encryption and an [If-None-Match condition](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes-enforce.html). These are source-prepared permissions, not evidence of installed policies or successful provider execution.

Prepare the review package locally from the target profile, a single saved stack object (not the DescribeStacks envelope), and the complete ListStackResources response:

```bash
python3 backend/infrastructure/release_access.py \
  --profile target-profile.json \
  --stack hosting-stack.json \
  --resources hosting-resources.json \
  --output release-access-review.json
```

This command makes no provider calls, refuses an existing output file and records hashes of the review and supplied observations. Saved JSON is not proof of freshness or authenticity: obtain and verify current observations before installation. The historical hosting IAM template owns `CloudFormationRole` and `HostingRole`; preserve those existing identities and reconcile their owner template rather than recreating them. The package is a proposal, not an installation change set or proof of effective permissions. Keep private source observations outside the repository.

To include an existing IAM owner-template proposal, add `--owner-template hosting-iam-owner.json --owner-sha256 <reviewed-canonical-template-digest>` to the command above. The digest uses `release_observation.digest` (canonical JSON), not a raw file-byte hash. The plan preserves HostingRole, CloudFormationRole, inline policy names and unrelated resources, adding two dedicated release permission ceilings. It rejects unknown attachments, boundary ownership and trust. Existing numeric-ID GitHub OIDC subjects are retained without conversion to name-only trust; verify the retained IDs and actual emitted subject against current GitHub configuration before installation. Both standard and retained numeric formats are tested. This does not configure GitHub OIDC claims, authenticate saved observations, create a change set or update IAM. Keep the candidate template private and review its exact delta and current provider-handler requirements before any execution.

The prepared hosting service policy scopes function configuration/code changes and PassRole to the selected runtime. Feature changes grant `iam:PutRolePolicy` only on that runtime role. A hosting-owned boundary additionally permits managed policy version operations on the exact boundary. For an external owner, add `--boundary-stack` and `--boundary-resources` to the access command above with that owner's saved single stack object and complete resource inventory. This keeps boundary updates with its owner and emits a separate `external_owner_handler_policy` for the exact managed policy. Retain current effective policy evidence and verify actual handler behavior in the destination before deployment. [Release access planner](../backend/infrastructure/release_access.py)

For a changed external boundary, run the separate owner operation during the recorded maintenance pause, before the hosting rollout change set. Use the already authorized owner session in a clean checkout of the reviewed source. It needs `iam:GetRole` on its own exact role to verify the IAM path as well as the original stack's authority and target policy reads. Prepare `owner-review.json` with the same `profile_sha256`, `source_sha`, `maintenance_marker` and `feature_values`, a distinct `operation_id` and expiry, `hosting_stack_arn` and `hosting_template_sha256` for the saved paused hosting template, and the rollout's `external_boundary` including its destination template digest. Set `owner_original_sha256` to the canonical digest of the saved original owner template. Set `operator_role_arn` to the existing independent owner's role and `service_role_arn` to the owner's actual attached CloudFormation role or JSON `null` if it has none. Use the same private files and journal directory through `create`, `inspect`, `execute` and `verify`. After a lost response, inspect the original operation. When the desired policy is already installed, supply the verified owner identity and digest directly to rollout. [Boundary owner command](../backend/infrastructure/release_boundary_owner.py)

```bash
python3 backend/infrastructure/release_boundary_owner.py "$OWNER_STEP" \
  --profile "$REVIEW_DIR/target-profile.json" --review "$REVIEW_DIR/owner-review.json" \
  --review-sha256 "$OWNER_REVIEW_SHA256" --hosting-template "$REVIEW_DIR/paused-hosting.json" \
  --owner-template "$REVIEW_DIR/boundary-owner.json" --journal "$REVIEW_DIR/owner-journal"
```

`release_rollout.resumption_plan` prepares a separate, expiring concurrency-only review from the exact template-verified paused rollout receipt and its collected artifact evidence. It rejects incomplete receipts, substituted source/evidence, reused operation IDs and invalid concurrency. A prepared plan is not permission or evidence that traffic reopened.

The same disabled `aws-rollout.yml` entry point now accepts `resume-create` → `resume-inspect` → `resume-execute` → `resume-verify` → `resume-health` → `resume-finalize` → `resume-finalize-inspect`. Keep the original paused-rollout metadata and add `resumption` with a distinct32-character lowercase hexadecimal `operation_id`, integer `expires_at` within the next hour for writes, positive integer `concurrency`, and string `verified_run` identifying the completed paused `verify` receipt. Recalculate the canonical review digest. Creation takes no prior resumption receipt; subsequent steps take the preceding resumption receipt's run. Use the same artifact producers. The fetch phase authenticates the completed paused receipt before AWS credentials; every step binds its review/evidence hashes. New creation/execution rechecks image scans, uploaded frontend bytes and catalog freshness. Expired reviews permit inspection/verification, never renewed writes.

`resume-health` checks the completed saved template, deployed CloudFront distribution and release prefix, Lambda alias/version/image and reviewed positive concurrency. It compares public frontend index bytes with the authenticated artifact and requires exact `/health/live` and `/health/ready` responses. Readiness includes database connectivity and migration heads; this does not establish login, provider delivery or physical acceptance. HTTPS requests reject redirects, arbitrary hosts and oversized responses. Failed health leaves maintenance ownership intact; retain the receipt and investigate the original operation.

`resume-finalize` repeats the release health checks, records durable intent and removes only the operation's maintenance/snapshot tags. Use `resume-finalize-inspect` with that original receipt after submission or a lost response. It checks current tag state and retains the original health observation and timestamp. Confirm the `maintenance_finalized` state before closing the operation. An uncertain outcome keeps the original journal for inspection. [Finalization](../backend/infrastructure/release_finalize.py)


### AWS resource and retention policy

Approved on24 November2026 for **developer AWS**. The user prioritises the first automated developer deployment, then implementation and verification of the remaining controls below. These are agreed policies, not claims of deployed enforcement or permission to delete resources now. Client-production capacity and release-retention policy require separate review; the earlier client14-day backup decision remains conditional on account eligibility/migration.

Routine releases reuse verified existing resources. Fresh-account provisioning is a separate operation. Preserve target/account/profile binding, resource ownership, encryption/private access, exact change-set review and uncertain-operation recovery. Do not recreate the database, network, bucket or identity pool on each release. No automatic paid capacity expansion, replacement or destructive cleanup is implied by deployment authority.

| Area | Approved rule | Implemented / deployed / verified status and owner |
| --- | --- | --- |
| Release artifacts: frontend, ECR images, Lambda versions/configuration | Protect current release plus the two newest successful, schema-compatible rollback releases regardless of age. Other successful releases:30 days. Failed/abandoned candidates:7 days only if never deployed and not linked to unresolved operations. First generate a deletion plan; active references and unresolved operations block deletion. Treat matching frontend/image/configuration as a release set. | Retention-aware cleanup pending. Current templates retain versions, immutable images and frontend prefixes; frontend bucket versioning is enabled. Protect noncurrent versions/referenced images too. No arbitrary delete-oldest lifecycle rule. |
| Session media | Access expires7 days from publication; monthly physical cleanup on the first day in Asia/Singapore. Respect upload leases and Undo holds; bounded batches, failed-deletion retries and missed-run/backlog alerts. Never delete valid media just because a storage threshold is crossed. Original10 MiB, converted5 MiB, known duration60 seconds maximum remain business rules. | Expiry and bounded cleanup workers exist; scheduler/alerts not deployed or verified. Schedule time of day remains to be selected. Per-file limits do not cap aggregate storage. |
| Exercise library | Retain valid published attachments until explicitly removed/replaced; eligible abandoned or detached objects follow protected cleanup. No session7-day bucket-wide expiry. | Existing cleanup logic; deployed schedule/versioning coverage unverified. |
| Developer RDS capacity |20 GiB initially, autoscaling maximum30 GiB; retain existing instance class and Single-AZ. No automatic class upgrade, extra DB or increased ceiling. Further increases require approval. Warn below20% free storage; escalate below10%; investigate growth without automatic business purge. | Historical developer template/receipt matches allocation limits; actual current settings and alerts require verification. Existing runbook proposes15-minute warning/5-minute critical evaluation; these timings/receivers are not newly accepted by approval of percentages. Portable validator still allows broader explicit client values. |
| Automated backups | Developer1 day; do not replay the rejected14-day change. Client14 days remains deferred until eligible account upgrade/migration. | Historical developer observation1 day; current verification and populated restore drill outstanding. |
| Manual/pre-change snapshots | One pre-change snapshot for a release involving DB migrations; reuse the verified original during recovery of the same operation. Protect the newest two verified pre-change snapshots regardless of age. Other managed snapshots become eligible after14 days only after the related release successfully completes. Protect unresolved/failed operations and explicit holds; flag them for review. Never delete outside managed ownership. | Snapshot primitives exist; protected-set retention/cleanup pending. Backup presence is not restore acceptance. |
| Temporary deployment workers | Explicit reviewed operations only; recover the original operation rather than create duplicates. Remove workers after completion and safe evidence retention. Daily orphan check; flag resources still present24 hours after creation. Automatic removal only when proven inactive and linked to a completed operation. Preserve shared IAM/network/database/secrets. | Operation ownership and explicit cleanup primitives exist; daily orphan detection/automated cleanup pending. Expired authorization is not a resource-deletion timer. Never delete a potentially running migration based solely on age. |
| Logs | Application7 days; helper1 day. Every new log group declares finite retention. No credentials, request bodies or health-record contents. Preserve necessary incident evidence deliberately before expiry. | Hosting/private-helper templates specify7/1 days; actual and historical groups require inspection. Retention limits stored age, not ingestion charges. |
| S3 unfinished uploads | Abort incomplete multipart uploads after7 days. Completed abandoned objects use the application cleanup worker, respecting leases/Undo. No blanket expiry of completed library or protected release files. | Multipart lifecycle pending; actual bucket versioning must be checked because ordinary DeleteObject can leave noncurrent copies. |
| Auth / business DB rows | Keep business history after deactivation; no general purge until a category-specific deletion/anonymisation policy is agreed. Preserve financial, signature, audit and uncertain-command evidence. Existing auth maintenance removes flows expired more than1 day and closed sessions older than7 days only after refresh ciphertext is cleared. | Narrow auth/media cleanup exists; scheduled execution unverified. No deletion of staff accounts or Cognito users is implied. General retention remains in [Data lifecycle](data-lifecycle.md). |

CloudFormation owns scheduler, log/RDS retention and S3 lifecycle configuration. EventBridge Scheduler triggers bounded Python workers for application-aware cleanup and orphan checks; workers do not wait in a polling process. Python owns eligibility, protected references, leases, receipts and failure recovery. These schedules are planned rather than deployed.

After first deployment: inventory actual resources/settings; implement the agreed controls with independent negative and interrupted-cleanup tests; review deletion plans; activate only the reviewed target operations; verify receipts and monitor backlog. Rollback incompatibility, missing evidence or unknown ownership must hold deletion. Existing7/14-day GitHub deployment artifacts are not sufficient for every indefinite recovery hold: preserve required evidence before their expiry. CI-artifact retention, network topology changes, aggregate-media thresholds, restore targets and client-production limits remain separate decisions.

The user reports an existingUS$100 budget; do not create a duplicate. Billing alerts are supplementary, not spending caps. Baseline RDS/network/WAF costs, requests, egress and log ingestion remain chargeable even with finite storage retention. No AWS query or mutation was performed for the24 November source audit.
