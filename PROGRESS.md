# Fitfinity current progress and handover

This file owns the **current task, exact stopping point, blockers, next actions and remaining work**. The [milestone overview](docs/journey.md#full-milestone-roadmap) and [complete dated history](docs/journey.md#complete-journey) live in Journey. [NORTH_STAR.md](NORTH_STAR.md) owns campaign procedure; the [documentation skill](.agents/skills/fitfinity-documentation/SKILL.md) owns reconciliation. Replace this checkpoint rather than appending execution history.

## Current task — Admin controls, larger UI text and CodeQL

Checkpoint: **4 November 2026 (Singapore)**. Accepted main is `1ecee1c1f8e2bb63bf6c248f4c845d180b9c4248` (PR121); final-head and fresh-main verification passed. Current branch: `feat/admin-approval-groups-codeql`.

### Campaign contract and leave-off

| Field | Current checkpoint |
| --- | --- |
| Outcome / scope | Remove the Admin approval explanatory paragraph; group the17 unchanged controls; standardize deactivation tab/button/confirmation danger styling; configure parallel CodeQL JS/TS and Python scans; apply the now-authorized global2px typography increase. |
| Starting evidence | PR121 accepted with all16 verification jobs; fresh-main run41602089280 succeeded. Public repository confirmed, CodeQL v4 official source/runtime and immutable pin reviewed. |
| Prepared changes | Six approval groups share one canonical field list; default policy/recovery remains unchanged. CodeQL runs independently on PR/main/week/manual events, with scoped SARIF permission and60-minute job budget. |
| Acceptance / budget | PR122 heada7cc191 passed all16 verification jobs in run41817500225 and both CodeQL jobs in run41817500233. The requested second audit found oversized new Admin group headings; the candidate fixes their hierarchy and strengthens the existing API case for edit/cancel/containment. Local6 component,3 real-API and27 editor/dialog cases passed; 40 independent editable-screen checks also passed; final-head CI remains pending. One bounded six-iteration/90-minute audit block; no inventory, timeout or retry relaxation. |
| Preserved work | Existing checkout and8 stashes; no AWS/provider or production PostgreSQL actions. |
| Leave-off / blocker | Second audit follow-up on PR122: local visual/documentation review complete; publish the heading refinement, then inspect new-head gates. Earlier green CI does not accept this new change. CodeQL alert baseline remains unverified because code-scanning API access returned403; no severity-based merge gate is claimed. |

### Resume in this order

1. Publish the locally verified PR122 heading refinement with the second audit evidence recorded in Journey.
2. Inspect exact-head application gates and both CodeQL language scans; triage actual findings before eligible source merge. If default setup conflicts with the workflow, resolve the observed configuration issue without weakening checks.
3. Verify fresh-main results separately; continue remaining M6 external acceptance under the existing deployment boundaries.

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

8. **Global typography increase — authorized4 November2026; current candidate, acceptance pending.** Increase every application UI text size by2px from its existing baseline, including headings, navigation, labels, inputs/selects, buttons, tables, calendars, dialogs, approval panels, helper/error/status text and empty states. This is app-wide, not limited to approval screens. Dependencies: inventory the shared typography tokens and component-specific font sizes, including responsive rules, before editing their canonical style owners. Acceptance evidence: verify the2px increase across representative computed styles and all roles; inspect desktop/phone/tablet layouts, keyboard focus and browser zoom for clipped/truncated labels, unintended overflow, inaccessible controls and broken wrapping; retain readable hierarchy and complete existing frontend/browser gates. Rollout boundary: current candidate increases249 explicit CSS font sizes by2px, default body text to18px and on-screen chart labels by2px; reports share the larger canonical chart labels; other export typography retains its fixed-page layout. Complete responsive verification before source acceptance. Approval-vetting redesign remains deferred.

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
| H3 / next | CodeQL workflow configured in current candidate; initial baseline and severity merge enforcement pending. Secret scanning and permission regression; rate limits, dependency failures, interrupted-write recovery | Permission matrix and operation coverage | Negative-role/foreign-record checks, forged actors, stale authority, 429/503/disconnect/restart recovery and no duplicate/partial writes; review false positives | Inspect supported GitHub controls before enabling; provider faults synthetic; no credential disclosure |
| H4 / next | Dependabot for npm/Python/Actions/container images; supply-chain review | Inventory exact pins/lockfiles, supported update ecosystems and CI | Grouped reviewed update PRs, lockfile/hash validation, vulnerability severity/triage deadlines, all final-head CI; assess SBOM and artifact/source provenance with verified digest | No auto-merge or unreviewed runtime updates; account settings remain unverified until read; provenance generation is not deployment |
| H5 / later | OpenTelemetry traces/metrics/structured logs and Grafana dashboards | H2 baseline, threat/data review, stable request correlation | Cross-layer correlation, latency/error/saturation dashboards, proposed SLOs/error budgets and actionable alert/runbook exercises; redact health/PII, tokens/cookies, SQL parameters; test sampling, retention, cardinality, export failures and cost caps | Prepare default-disabled instrumentation first; separately approve stack/credentials/ingestion/production activation; no planned-capability claim |
| H6 / release | AWS release readiness and production operations (runbook merged through PR109): health/readiness, synthetic checks, incidents, rollback, backup/restore, migration recovery, capacity/cost | Tested source/artifact and migration inventory, H2/H5 where relevant; reviewed recovery environment | Reviewed image/provenance/grants/rollout plan; version/digest-bound health and synthetic evidence, incident ownership and drills, measured RPO/RTO, populated restore/forward-recovery and rollback constraints, capacity/cost alerts | Isolated restore drills first; never replay bootstrap, rewrite applied migrations, touch customer data or deploy under source authority |
| H7 / ongoing | Documentation/test impact and obsolete artifact audit | Source reference/loader scan and owners | Updated affected tests/fixtures/inventories, preserved first failures, no stale status, meaningful purpose comments; retain historical evidence by immutable link | No blanket deletion, architecture transplant or comment-only churn; retain the PR59/63 cleanup evidence |

Full dated receipts, first failures and superseded checkpoints live only in [Service Journey](docs/journey.md#complete-journey).
