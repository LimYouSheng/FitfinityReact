# Fitfinity current progress and handover

This file owns the **current task, exact stopping point, blockers, next actions and remaining work**. The [milestone overview](docs/journey.md#full-milestone-roadmap) and [complete dated history](docs/journey.md#complete-journey) live in Journey. [NORTH_STAR.md](NORTH_STAR.md) owns campaign procedure; the [documentation skill](.agents/skills/fitfinity-documentation/SKILL.md) owns reconciliation. Replace this checkpoint rather than appending execution history.

## Current task — Current-release upgrade and observation preparation on PR124

| Field | Current checkpoint |
| --- | --- |
| Outcome / scope | Prepare a populated upgrade, non-destructive runtime/frontend template plan and Actions read-only observation before current-source AWS rollout. Preserve PR124's message UI and parallel build preparation. |
| Starting evidence | PR124 head290adfa had complete application CI41969294827, CodeQL41969294919 and preparation41969294884 success. Those receipts do not accept this follow-up head. |
| Prepared changes | Atomic targeted upgrade primitive; template planner retaining resources/versions; manual main-only observation using the protected hosting role with a read-only session policy and redacted metadata. No live executor or AWS mutation is added. |
| Acceptance / budget | Seven new actual isolated PostgreSQL probes, all658 offline infrastructure tests and144 quality/guard cases passed. Backend inventory1429 includes the7 new cases; source lint/health and dependency consistency passed. One focused validation block followed by complete exact-head CI. |
| Preserved work | Existing checkout and8 stashes; historical release contracts untouched. No AWS identity is configured in this workspace; no production database/provider action or live workflow dispatch. |
| Leave-off / blocker | Publish/verify this PR124 follow-up. After merge, dispatch **Observe current developer AWS release** on main and complete its existing GitHub environment approval. Observation is required before specifying live migration executor, exact runtime grants/feature IAM/configuration, backup and change-set execution. The connected tools lack dispatch and local CLI authentication is unavailable. |

### Resume in this order

1. Validate PR124's combined final head and merge only after all required gates/GitHub requirements; inspect fresh main separately.
2. Run the [read-only observation](docs/runbook.md#62-deployment-preparation-and-acceptance), review resource/image/alias/configuration and backup metadata, and obtain the private observed schema/grant evidence. No SQL/schema is inferred from RDS instance metadata.
3. Finish the current-source private migration executor and artifact/scan/change-set/health controls against that observed state. Keep execution blocked until populated-data, grants, backup/recovery, compatibility and explicit rollout authority are satisfied.
4. Complete M6 live Cognito/device/recovery acceptance after rollout; approval-vetting design remains deferred. Then scope M7 and prioritize M10 work below.

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
| H6 / release | AWS release readiness and production operations (runbook merged through PR109): health/readiness, synthetic checks, incidents, rollback, backup/restore, migration recovery, capacity/cost | Tested source/artifact and migration inventory, H2/H5 where relevant; reviewed recovery environment | Reviewed image/provenance/grants/rollout plan; version/digest-bound health and synthetic evidence, incident ownership and drills, measured RPO/RTO, populated restore/forward-recovery and rollback constraints, capacity/cost alerts | Isolated restore drills first; never replay bootstrap, rewrite applied migrations, touch customer data or deploy under source authority |
| H7 / ongoing | Documentation/test impact and obsolete artifact audit | Source reference/loader scan and owners | Updated affected tests/fixtures/inventories, preserved first failures, no stale status, meaningful purpose comments; retain historical evidence by immutable link | No blanket deletion, architecture transplant or comment-only churn; retain the PR59/63 cleanup evidence |

Full dated receipts, first failures and superseded checkpoints live only in [Service Journey](docs/journey.md#complete-journey).
