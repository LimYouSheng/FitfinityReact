# Fitfinity current progress and handover

This file owns the **current task, exact stopping point, blockers, next actions and remaining work**. The [milestone overview](docs/journey.md#full-milestone-roadmap) and [complete dated history](docs/journey.md#complete-journey) live in Journey. Update this checkpoint when work changes; keep detailed historical receipts in Journey instead of accumulating old handovers here.

## Current task — consolidate and accept the documentation refactor

Checkpoint: 28 October 2026, 16:26 Singapore. The requested documentation changes are implemented and published in **[PR109](https://github.com/LimYouSheng/FitfinityReact/pull/109)**. They are not merged or final-head CI-accepted. The active task is to complete verification and resolve the remaining CI failure before an eligible source merge; no new API feature or AWS deployment is in progress.

### Completed in this task

| Deliverable | Current result |
| --- | --- |
| Documentation structure | Lowercase docs; root README removed; AGENTS is the entry directory. No repository skill created, as requested. |
| Rules and API reference | [Business rules](docs/business-rules.md) retains all64 BR groups. [API contracts](docs/api-contracts.md) retains all55 operation rows and indexes159 HTTP operations /246 schemas from checked-in OpenAPI. |
| Milestones and history | [Journey](docs/journey.md) begins with all20 milestone/extension rows (M0–M10), followed by the complete dated history. No duplicate roadmap remains here. |
| Specialist guides | Version inventory, code-owner/BR mapping, developer AWS role UAT, runbook, development guide and ten architecture ADRs are included. |
| PR cleanup | PR110/111 changes are incorporated into PR109; both are closed and their branches/commits preserved. GitHub marked PR110 merged into the task branch by ancestry, not into main. |
| Local validation | Last split validation passed1,558 local links/anchors, all24 current Mermaid diagrams, preservation of rules/matrix/milestones/full history and API-index agreement. No application, dependency or workflow bytes changed. This handover wording update receives its own link/diff checks. |

### Left off — checkout, evidence and unresolved failure

| Item | Exact handover |
| --- | --- |
| Repository / active branch | `/workspace/FitfinityReact` · `docs/dependency-version-inventory` · PR109 targets main. Use the existing checkout. |
| Inspected source | `1b3a5cea89c79cb0ff839757c7c92d800168bc13`, before this handover-only update. Resolve the latest commit from Git/PR109 when resuming; this document cannot embed its own commit SHA. |
| Working tree / preserved work | Clean before this update. Eight existing stashes and superseded PR branches are retained; do not reset, drop or delete them. |
| Main / accepted application | Last verified main `1246fb815b1240a92fd953b85abc05f18f46bc73` (PR104), with successful fresh-main run40614828297. Recheck remote main before continuing. |
| Latest inspected CI | [run40656465566](https://github.com/LimYouSheng/FitfinityReact/actions/runs/40656465566) for `1b3a5ce` was pending. Publishing this handover creates a newer head requiring its own complete checks. Earlier-head results are not final acceptance. |
| Known failed evidence | [run40650892639](https://github.com/LimYouSheng/FitfinityReact/actions/runs/40650892639), head `a5e36f0`: frontend/backend and API shard2 passed; shard1 had187 passed/1 failed. The aggregate correctly rejected the failed shard. |
| Failure location | Phone permanent reassignment in `tests-api/records.spec.js:200`; visible assignment and reload checks passed, then `read()` at line221 failed on `/api/directory` with `socket hang up (ECONNRESET)`. The reset's root cause is still unproven. No code repair, retry, assertion weakening or timeout change has been made. |
| Evidence to reopen | [Original shard1 job](https://github.com/LimYouSheng/FitfinityReact/actions/runs/40650892639/job/122690445978); retained local log `/tmp/fitfinity-run40650892639-shard1.log`; Actions trace artifact `fitfinity-api-traces-40650892639-1-1`. Local temporary files may not survive another workspace. Detailed receipt: [Journey entry](docs/journey.md#28-october-2026--split-canonical-rules-api-contracts-and-journey-consolidate-prs). |
| Access caveat | The GitHub connector retrieved logs when CLI log download was forbidden; CLI API credentials later returned401. Use the available authorized connector if CLI access remains unavailable; do not replace injected credentials or bypass controls. |

### Resume in this order

1. Read AGENTS and this handover; inspect working tree, latest PR109 head, main and the runs attached to that exact head. Preserve original failed evidence and unknown work.
2. Inspect the final-head frontend/backend/API-browser results. Investigate the retained connection reset using the trace and available server evidence; distinguish a transport/environment interruption from application or fixture behavior before choosing a repair. A later green run does not establish the earlier root cause. Do not use blanket retries or longer timeouts.
3. If a repair is justified, reproduce and validate the focused change, record its diagnosis in Journey, update this checkpoint and run the required complete final-head gates. Keep any application/fixture repair identifiable from the documentation work.
4. Once all three exact-head gates and GitHub requirements pass, merge PR109 under existing source-merge authority and verify fresh main. Record the tested/merged SHAs and run links in Journey; replace this active task with the next actual task here.
5. Resume the separately scoped M6 external acceptance and roadmap work below. Source merge does not authorize image publication, AWS changes, real provider actions or physical/live acceptance claims.

## Current acceptance boundaries

The [canonical operation matrix](docs/api-contracts.md#domain-operation-inventory) remains **55/55 source accepted:54 server-connected operations and one local predicate**. M6 source exit is accepted; the remaining live/provider/device evidence is listed below. Real-API verification uses actual FastAPI/migrations/PostgreSQL and isolated object storage with synthetic records and a local signed-token Cognito substitute. It does not use production PostgreSQL and needs no Lambda redeployment.

No current-source Lambda deployment, real Cognito acceptance or current physical-device/UAT receipt is recorded. Historical application receipts and full milestone scope are in [Journey](docs/journey.md); the current documentation PR does not change those acceptance boundaries.

## Remaining work

Follow the [full roadmap in Journey](docs/journey.md#full-milestone-roadmap). The 55-operation source target is complete; do not repeat accepted integrations or mark later milestones complete from this count.

1. Complete the consolidated documentation PR and CI diagnosis above, then the remaining environment-specific M6 acceptance in the table below through the separately authorized release work. The source-exit implementation is accepted; do not repeat it or infer live acceptance from synthetic-provider tests.
2. Scope M7 durable events, scheduling/notifications and media processing/retention, preserving provider and deployment boundaries.
3. Prepare M8/M9 release, real Cognito, Owner/Trainer UAT, physical-device and populated recovery evidence. Actual AWS changes, provider actions and deployment require their own authorization.
4. Schedule the M10 packages below by dependency and launch criticality; mutation, latency and Grafana remain planned; dependency automation/audit is partially implemented, with remaining supply-chain work under H4.
5. Deliver the separate public website and its content management after staff-portal acceptance. Preserve the canonical document ownership, the user-requested docs/versions.md inventory, docs/code-owners.md navigation map and docs/uat/ role worksheets and all eight existing stashes.

### Dependency/security maintenance and deferred refactors

PR103's grouped Dependabot policy and blocking npm high/critical audit are merged. PR104's PyJWT/urllib3 fixes and browser-runner mirror repair are merged and passed exact-head plus fresh-main verification. They are completed source changes, not active dependent branches. Detailed advisories, first failures and receipts remain in [Journey](docs/journey.md#complete-journey).

The latest recorded security-alert state is the user's **0 open /26 closed** report after PR104. Independent alert reads previously returned403; no fresh alert audit or deployed remediation is claimed by this documentation update. Routine proposals105/107/108 were closed unmerged; closing PRs is not a vulnerability fix. Future grouped updates remain configured under the [runbook policy](docs/runbook.md#dependency-maintenance).

Remaining work: independently reconcile alert/settings access when available, extend Python custom-lock and Compose-image update coverage, assess SBOM/provenance and triage runner OS/browser dependencies. The official Playwright container trial was not adopted; its retained scan found7 high package entries, including a GStreamer fix requiring Ubuntu Pro/ESM. The Ubuntu mirror change fixes download availability, not those findings. No paid service or AWS action is authorized by this backlog.

Optional npm/Actions upgrades require separate compatibility review; the previous combined optional trial's failed unit case remains retained in history. Backend router extraction and its acknowledgement-fixture repair remain unmerged, as does any further feature extraction. PR91/92's accepted changes must not be repeated.

### Developer AWS UAT preparation

The [UAT folder](docs/uat/) in the documentation PR stack contains separate Owner, Admin and Trainer worksheets with blank Result/Remarks columns. The original92 case IDs and additional Trainer manager-action restriction check remain; none is marked executed or passed. Worksheets target the deployed developer AWS site with designated test identities, real Cognito/email and developer storage. Assisted fault/recovery checks require an arranged test. Drafting does not deploy source or establish live/device acceptance.

### M6 exit evidence — source accepted, external acceptance open

PR82 closes the authorized M6 source-exit work after complete final-head CI and normal merge. Full milestone/live acceptance remains distinct. Detailed first failures and the measured test-graph cleanup repair are retained once in Journey.

| Area | Accepted evidence | Remaining boundary |
| --- | --- | --- |
| Trainer attribution | Migration 0046, original/assigned/performed identity, immutable assignment/request evidence, conservative legacy backfill, scoped historical reads and deletion/Undo preservation pass PostgreSQL and browser CI. | Legacy originals without evidence remain explicitly unresolved; no customer backfill or deployed migration is claimed. |
| Service restart | Two actual HTTP worker crash/restart cases pass: committed records/receipts/auth survive restart, interrupted writes roll back, and replay has no second effect. | Isolated Docker PostgreSQL evidence; deployed Lambda/database recovery remains release acceptance. |
| Authentication and route parity | Existing session/JWT/CSRF/refresh/expiry evidence plus 12 real-API enrollment/password/navigation cases and two operator-recovery drills pass complete CI. Evidence owners are linked in Contracts. | Cognito responses are synthetic. The operator procedure adds no app recovery-admin powers; real enrollment/recovery and current device behavior need their own receipts. |
| External acceptance | No current-source Lambda, real Cognito or current physical-device/UAT receipt is recorded. | Reviewed source/environment binding, applicable deployment/provider authorization, and actual desktop/Samsung/iPad/Owner/Trainer acceptance. No blanket M6 closure from source CI. |

### M10 work packages — planned

Dependency automation and npm auditing are partially implemented through PR103/104. The packages below track remaining work; mutation, latency campaigns and OTel/Grafana are not implemented. The heading remains stable for existing links.

M10 depends on stable domain contracts and isolated test evidence; environment-specific rollout also depends on the relevant M8/M9 release preparation. This is the only task ledger. Priorities below follow integrated-operation evidence; introduce tools only in a scoped implementation task. No paid services, AWS changes or deployment are authorized merely by this list.

| ID / priority | Scope | Dependencies | Acceptance evidence | Rollout boundary |
| --- | --- | --- | --- | --- |
| H1 / next | Mutation testing for critical JS/Python authorization, scheduling, credits, idempotency and persistence | Real-DB coverage map; stable focused tests | Baseline mutants by owner, classify surviving/equivalent/uncovered mutations, repair meaningful gaps; justify per-area gates from baseline, retain time/cost report | Start bounded locally/CI; do not substitute mock-only mutations for DB invariants or set arbitrary global score |
| H2 / next | Latency/throughput/errors/resources; p50/p95/p99, concurrency, representative data, cold/warm starts, DB queries and browser performance | Repeatable isolated data, functional correctness, source/environment fingerprints | Bounded baseline/fault/overload cohorts; sample counts, duration, query/connection/memory/CPU data and browser vitals; measured budgets and regression thresholds after baseline | Synthetic isolated targets first; no production load or claimed Lambda cold-start evidence from local containers |
| H3 / next | Secret scanning, static analysis and permission regression; rate limits, dependency failures, interrupted-write recovery | Permission matrix and operation coverage | Negative-role/foreign-record checks, forged actors, stale authority, 429/503/disconnect/restart recovery and no duplicate/partial writes; review false positives | Inspect supported GitHub controls before enabling; provider faults synthetic; no credential disclosure |
| H4 / next | Dependabot for npm/Python/Actions/container images; supply-chain review | Inventory exact pins/lockfiles, supported update ecosystems and CI | Grouped reviewed update PRs, lockfile/hash validation, vulnerability severity/triage deadlines, all final-head CI; assess SBOM and artifact/source provenance with verified digest | No auto-merge or unreviewed runtime updates; account settings remain unverified until read; provenance generation is not deployment |
| H5 / later | OpenTelemetry traces/metrics/structured logs and Grafana dashboards | H2 baseline, threat/data review, stable request correlation | Cross-layer correlation, latency/error/saturation dashboards, proposed SLOs/error budgets and actionable alert/runbook exercises; redact health/PII, tokens/cookies, SQL parameters; test sampling, retention, cardinality, export failures and cost caps | Prepare default-disabled instrumentation first; separately approve stack/credentials/ingestion/production activation; no planned-capability claim |
| H6 / release | AWS release readiness and production operations (runbook drafted in PR109): health/readiness, synthetic checks, incidents, rollback, backup/restore, migration recovery, capacity/cost | Tested source/artifact and migration inventory, H2/H5 where relevant; reviewed recovery environment | Reviewed image/provenance/grants/rollout plan; version/digest-bound health and synthetic evidence, incident ownership and drills, measured RPO/RTO, populated restore/forward-recovery and rollback constraints, capacity/cost alerts | Isolated restore drills first; never replay bootstrap, rewrite applied migrations, touch customer data or deploy under source authority |
| H7 / ongoing | Documentation/test impact and obsolete artifact audit | Source reference/loader scan and owners | Updated affected tests/fixtures/inventories, preserved first failures, no stale status, meaningful purpose comments; retain historical evidence by immutable link | No blanket deletion, architecture transplant or comment-only churn; retain the PR59/63 cleanup evidence |

Full dated receipts, first failures and superseded checkpoints live only in [Service Journey](docs/journey.md#complete-journey).
