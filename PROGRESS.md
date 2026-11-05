# Fitfinity current progress and handover

This file owns the **current task, exact stopping point, blockers, next actions and remaining work**. The [milestone overview](docs/journey.md#full-milestone-roadmap) and [complete dated history](docs/journey.md#complete-journey) live in Journey. [NORTH_STAR.md](NORTH_STAR.md) owns campaign procedure; the [documentation skill](.agents/skills/fitfinity-documentation/SKILL.md) owns reconciliation. Replace this checkpoint rather than appending execution history.

## Current task — Record backup restriction and defer retention to client AWS

| Field | Current checkpoint |
| --- | --- |
| Outcome / scope | User decision: retain the developer account's observed one-day backup setting; defer14-day retention until account-plan upgrade and migration to client AWS. Documentation only; no further AWS update, account upgrade or migration authorized by this entry. |
| Starting evidence | PR126 merged asc2774c8 after complete exact-head application41993136952, CodeQL41993136771 and release-preparation41993136983 verification. Fresh-main verification is separate. |
| AWS checkpoint | User executed the retention-only CloudFormation change on5 November. AWS rejected14 days because it exceeds the current Free Tier account-plan limit. Subsequent user-supplied RDS output: available, retention1, pending modifications empty. Last supplied stack state: UPDATE_ROLLBACK_IN_PROGRESS; completion is not yet confirmed. |
| Prepared changes | Reconcile BR-058, Runbook, Data Lifecycle and Security with the deferred client-account target; preserve the failed execution and guard correction in Journey. No infrastructure template, applied migration, IAM or runtime change. |
| Acceptance / budget | Changed documentation links/fences, consistency and diff-whitespace checks passed; unchanged executable behavior needs no new test cases or inventory changes. New source head still requires existing CI. |
| Preserved work / next | Existing checkout and8 stashes preserved. Confirm foundation rollback completion read-only before any future foundation write. Continue private schema/grant and developer deployment readiness independently; retention14 is deferred to the client AWS migration work. |

### Resume in this order

1. Publish and verify this documentation change; inspect fresh-main verification after the PR126 runner repair separately.
2. Confirm the developer foundation reaches UPDATE_ROLLBACK_COMPLETE; database availability alone does not establish stack recovery. Do not replay either old change set.
3. Continue the authorized private catalog-query path and compare actual schema/grants with source; corrected AWS metadata observation41990257797 already succeeded.
4. After account-plan upgrade and migration to the identified client AWS account, verify plan eligibility, destination resources, backup-storage pricing and actual settings; prepare a newly reviewed retention14 change and verify the result. Never reuse developer-account plans/ARNs. Retain a separate populated restore drill and measured recovery objectives before client handover.

## Current acceptance boundaries

The [canonical operation matrix](docs/api-contracts.md#domain-operation-inventory) retains the original **55/55 source-accepted operations:54 server-connected operations and one local predicate**. PR116 separately adds three source-accepted Admin-management operations, making58 named operations in current source. Their acceptance comes from PR116’s final-head and fresh-main receipts, not from inheriting the earlier milestone count.

M6 source exit is accepted; live/provider/device evidence remains outstanding. Real-API verification uses actual FastAPI, migrations, PostgreSQL and isolated object storage with synthetic records and a local signed-token Cognito substitute. No production PostgreSQL is used. GitHub Pages staff-demo publishing passed; no current-source Lambda deployment, live-provider acceptance or current physical-device/UAT receipt is recorded.

## Remaining work

Follow the [full roadmap in Journey](docs/journey.md#full-milestone-roadmap). The 55-operation source target is complete; do not repeat accepted integrations or mark later milestones complete from this count.

1. Resolve or explicitly disposition the deferred UI findings below before physical acceptance, then prepare the remaining environment-specific M6 acceptance described below through separately authorized release work. The source-exit implementation is accepted; do not repeat it or infer live acceptance from synthetic-provider tests.
2. Scope M7 durable events, scheduling/notifications and media processing/retention, preserving provider and deployment boundaries.
3. Prepare M8/M9 release, real Cognito, Owner/Trainer UAT, physical-device and populated recovery evidence. Actual AWS changes, provider actions and deployment require their own authorization.
4. Schedule the M10 packages below by dependency and launch criticality; mutation, latency and Grafana remain planned; dependency automation/audit is partially implemented, with remaining supply-chain work under H4.
5. Map business privacy/retention clauses using [Data lifecycle](docs/data-lifecycle.md); approve category-specific periods and exclusions before any general disposal implementation. Verify existing auth/media worker scheduling and backup/object-copy settings through separately authorized environment work.
6. Deliver the separate public website and its content management after staff-portal acceptance. Preserve the canonical document ownership, the user-requested docs/versions.md inventory, docs/code-owners/index.md navigation map and docs/uat/ role worksheets and all eight existing stashes.

7. **Approval vetting UI cleanup — documented, implementation deferred by the user (1 November 2026).** Review all approval screens for a consistent, uncluttered layout rather than polishing only Exercise Library. Depends on stable proposal/decision contracts, protected attachment preview and approved publication behavior. Exercise Library’s Messages → Review panel should show requesting Admin/time and new/edit intent; name/category/description/proposed active status; playable video or image preview with filename/size; current-versus-proposed changes for edits, including attachment replacement/removal; and **Approve & Save**, **Reject**, **Back**. No library-wide Publish button is agreed. Acceptance evidence: desktop/phone/tablet readability and keyboard navigation, complete exact-intent review, foreign-attachment denial, stale-review rejection without overwrite, rejection preserving the existing entry, original-key recovery after lost responses, and fresh-login verification that Trainers see only the approved version. Rollout boundary: no visual redesign now; resume with a reviewable design before implementation, preserve server guards, and obtain complete final-head verification before source acceptance. No AWS/provider actions are authorized by this backlog.

8. **Global typography increase — source accepted in PR122; physical acceptance pending.** All249 existing CSS text sizes increase by2px, body text is18px and shared chart labels increase by2px. Admin group hierarchy, narrow/tablet calendars and saved-video preview layout were repaired with retained regressions. Final-head full CI passed before merge as00bcda0; developer AWS and actual-device readability/zoom acceptance remain separate. Approval-vetting redesign remains deferred.

### Dependency/security maintenance and deferred refactors

PR117's minimatch override is merged; PR120's dependency/inventory guards and consolidated updates are merged in1ba1573 with final-head and fresh-main verification passed. Preserve the patched override until reviewed upstream resolution and complete verification justify removal. [Journey](docs/journey.md#complete-journey) retains advisories, rejected attempts and historical scans; the [runbook](docs/runbook.md#dependency-maintenance) owns update policy.

Remaining: verify alert27 identity/closure and repository settings when access permits (last direct read denied); implement reviewed Python custom-lock/Compose update automation and broader vulnerability coverage; assess SBOM/provenance and runner OS/browser dependencies. An old zero-audit receipt does not establish today's alert count or deployed remediation. The unadopted browser-image trial does not describe the current runner. Backend router extraction and further feature extraction remain deferred, not active open PRs; preserve stashed work and do not repeat accepted PR91/92 changes.

### Developer AWS UAT preparation

Use the blank [Owner](docs/uat/owner.md), [Admin](docs/uat/admin.md) and [Trainer](docs/uat/trainer.md) worksheets with designated developer-AWS identities and actual device/revision evidence. Arrange assisted fault/recovery cases before execution. No worksheet is a completed live test.

### M6 exit evidence — source accepted, external acceptance open

Source exit, attribution, actual HTTP-process restart and synthetic identity/recovery evidence are retained in [Journey](docs/journey.md#complete-journey) and the [operation matrix](docs/api-contracts.md#domain-operation-inventory). Remaining acceptance: current-source Lambda/database rollout, real Cognito enrollment/recovery, desktop/Samsung/iPad role UAT and populated recovery. Legacy attribution without original evidence remains unresolved; no customer backfill is implied. Bind source, artifact, environment and applicable authorization before execution.

### M10 work packages — planned

Dependency automation and npm auditing are partially implemented through PR103/104. The packages below track remaining work; mutation, latency campaigns and OTel/Grafana are not implemented. The heading remains stable for existing links.

M10 depends on stable domain contracts and isolated test evidence; environment-specific rollout also depends on the relevant M8/M9 release preparation. This is the only task ledger. Priorities below follow integrated-operation evidence; introduce tools only in a scoped implementation task. No paid services, AWS changes or deployment are authorized merely by this list.

| ID / priority | Scope | Dependencies | Acceptance evidence | Rollout boundary |
| --- | --- | --- | --- | --- |
| H1 / next | Mutation testing for critical JS/Python authorization, scheduling, credits, idempotency and persistence | Real-DB coverage map; stable focused tests | Baseline mutants by owner, classify surviving/equivalent/uncovered mutations, repair meaningful gaps; justify per-area gates from baseline, retain time/cost report | Start bounded locally/CI; do not substitute mock-only mutations for DB invariants or set arbitrary global score |
| H2 / next | Latency/throughput/errors/resources; p50/p95/p99, concurrency, representative data, cold/warm starts, DB queries and browser performance | Repeatable isolated data, functional correctness, source/environment fingerprints | Bounded baseline/fault/overload cohorts; sample counts, duration, query/connection/memory/CPU data and browser vitals; measured budgets and regression thresholds after baseline | Synthetic isolated targets first; no production load or claimed Lambda cold-start evidence from local containers |
| H3 / next | CodeQL workflow merged in PR122; main scan after PR123 has eight assessed findings; URI validation repair merged and its finding absent from the new SARIF; severity merge enforcement pending. Secret scanning and permission regression; rate limits, dependency failures, interrupted-write recovery | Permission matrix and operation coverage | Negative-role/foreign-record checks, forged actors, stale authority, 429/503/disconnect/restart recovery and no duplicate/partial writes; review false positives | Inspect supported GitHub controls before enabling; provider faults synthetic; no credential disclosure |
| H4 / next | Dependabot for npm/Python/Actions/container images; supply-chain review | Inventory exact pins/lockfiles, supported update ecosystems and CI | Grouped reviewed update PRs, lockfile/hash validation, vulnerability severity/triage deadlines, all final-head CI; assess SBOM and artifact/source provenance with verified digest | No auto-merge or unreviewed runtime updates; account settings remain unverified until read; provenance generation is not deployment |
| H5 / later | OpenTelemetry traces/metrics/structured logs and Grafana dashboards | H2 baseline, threat/data review, stable request correlation | Cross-layer correlation, latency/error/saturation dashboards, proposed SLOs/error budgets and actionable alert/runbook exercises; redact health/PII, tokens/cookies, SQL parameters; test sampling, retention, cardinality, export failures and cost caps | Prepare default-disabled instrumentation first; separately approve stack/credentials/ingestion/production activation; no planned-capability claim |
| H6 / release | AWS release readiness and production operations (runbook merged through PR109): health/readiness, synthetic checks, incidents, rollback, backup/restore, migration recovery, capacity/cost | Tested source/artifact and migration inventory, H2/H5 where relevant; reviewed recovery environment | Client-account14-day retention deferred until account-plan upgrade and migration, with eligibility/cost verification and a new destination-bound plan; reviewed image/provenance/grants/rollout plan; version/digest-bound health and synthetic evidence, incident ownership and drills, measured RPO/RTO, populated restore/forward-recovery and rollback constraints, capacity/cost alerts | Isolated restore drills first; never replay bootstrap, rewrite applied migrations, touch customer data or deploy under source authority |
| H7 / ongoing | Documentation/test impact and obsolete artifact audit | Source reference/loader scan and owners | Updated affected tests/fixtures/inventories, preserved first failures, no stale status, meaningful purpose comments; retain historical evidence by immutable link | No blanket deletion, architecture transplant or comment-only churn; retain the PR59/63 cleanup evidence |

Full dated receipts, first failures and superseded checkpoints live only in [Service Journey](docs/journey.md#complete-journey).
