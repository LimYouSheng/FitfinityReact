# Fitfinity current progress and handover

This file owns the **current task, exact stopping point, blockers, next actions and remaining work**. The [milestone overview](docs/journey.md#full-milestone-roadmap) and [complete dated history](docs/journey.md#complete-journey) live in Journey. [NORTH_STAR.md](NORTH_STAR.md) owns reusable campaign procedure; the [documentation skill](.agents/skills/fitfinity-documentation/SKILL.md) owns every-PR documentation reconciliation.

## Current task — resolve retained M6 reliability findings before AWS deployment

Checkpoint: 31 October 2026. The user requested developer AWS deployment for physical M6 testing, then paused it to resolve the retained PDF/rendering and transport findings first. No AWS action has been executed. PR114 is merged at `849b45442b2afe61ab0e92f5954f58a7884c577e`; fresh-main run41198362253 has now passed. PR115 is the existing draft on `docs/development-handover`; this reliability slice extends that draft rather than creating competing handovers.

### Completed in this task

| Item | Evidence / limitation |
| --- | --- |
| Original evidence recovered | PDF run40709497234/artifact12826900606 and reassignment run40650892639/artifact12800252129 inspected. First failures retained in Journey. |
| Transport mechanism reproduced | A loopback server recorded Playwright `route.fetch()` leaving socket2 idle; the later readback with `Connection: close` reused socket2. Closing intercepted requests changes the readback to socket3. This establishes a pooling hazard, not retrospective proof of the server's exact reset timing. |
| Fixture repair prepared | Shared `fetchRoute` closes all nine intercepted requests across eight specs and asserts the response closes. Original writes, response-loss scenarios, permissions and persistence assertions remain. A real HTTP regression verifies distinct connections. |
| Focused baseline and stress evidence | Unchanged9-case PDF/reassignment pass; subsequent6-case diagnostic pass includes24 PDF preparations and desktop/tablet sidebar bounds. First PDF readiness:268ms desktop,2319ms phone,797ms tablet; repeats21–337ms. Linux synthetic-provider evidence, not physical-device acceptance. |
| Rendering diagnosis and mitigation | Retained DOM contains the Export Summary dialog and Preparing PDF, while the last image still shows damaged pre-dialog content; page teardown also timed out. No independent navbar layout defect or definitive renderer cause established. Added explicit modal/file readiness assertions, timing annotation and browser-process logging. A controlled80-export comparison found software-backed canvas readback faster (69ms mean versus143ms), and the renderer now requests it on both threads; exact original root cause remains unproven. |

### Campaign contract and leave-off

| Field | Current checkpoint |
| --- | --- |
| Outcome / scope | Resolve the three retained symptoms before developer AWS physical M6 acceptance; BR029/035/047/064. Isolated synthetic storage only during this campaign. |
| Repository / branch | Existing `/workspace/FitfinityReact`, `docs/development-handover`, based on main849b454; preserve all8 stashes. PR115 previously had head29f4a92. |
| Acceptance | Causal repair evidence, relevant persistence/authority regressions, complete369-case real-API suite and all three exact-head CI gates. A passing rerun alone cannot close the rendering finding. |
| Verification in progress | Transport candidate ca17e20 passed all369 local real-API cases in21.1minutes and both CI API shards/aggregate in run41199629750. PDF-context mitigation passed all1472 units/150 files and27 focused real-API export/recovery cases across3 projects; lint and code health passed again. Final-head CI/merge pending;98 quality guards passed on the unchanged fixture/tooling inputs. |
| Unresolved | PDF/browser stall and damaged capture remain unproven despite bounded successful probes. Obtain browser-process evidence if it recurs; do not alter timeouts, renderer selection, worker counts or assertions to hide it. |
| Budget | First bounded90-minute block; transport repair, renderer lifetime/full-suite probes and controlled canvas comparison completed. Full-suite evidence next; reassess after6 substantive iterations or90 active minutes. |
| External boundary | AWS deployment remains user-paused until reliability disposition. Real Cognito, populated recovery and physical desktop/Samsung/iPad UAT remain subsequent acceptance, not locally fixable evidence. |

### Resume in this order

1. Inspect the newest PR115 head and all3 required CI gates. Local1472-unit and27-case PDF checks pass; the preceding369-case transport pass is recorded separately and does not replace complete new-head CI.
2. Use final-head browser-process evidence to assess the renderer mitigation. Current evidence narrows the damaged navbar image to the same stalled rendering episode; it does not prove a fix. No arbitrary CSS or encoder replacement.
3. Update PR115's final scope and evidence, then require all final-head frontend/backend/API-browser gates and normal GitHub requirements. Record fresh-main separately; preserve original failures even if CI passes.
4. Return to the authorized developer AWS preparation only after the user's paused reliability objective is resolved or they explicitly accept a remaining blocker. Bind current source/artifacts, migrations, backup/recovery and rollback before deployment; no bootstrap replay.
5. Complete designated real-Cognito and physical M6 worksheets before M7. Keep planned mutation/latency/Grafana and operational work in the backlog below.

## Current acceptance boundaries

The [canonical operation matrix](docs/api-contracts.md#domain-operation-inventory) remains **55/55 source accepted:54 server-connected operations and one local predicate**. M6 source exit is accepted; the remaining live/provider/device evidence is listed below. Real-API verification uses actual FastAPI/migrations/PostgreSQL and isolated object storage with synthetic records and a local signed-token Cognito substitute. It does not use production PostgreSQL and needs no Lambda redeployment.

No current-source Lambda deployment, real Cognito acceptance or current physical-device/UAT receipt is recorded. Historical application receipts and full milestone scope are in [Journey](docs/journey.md); documentation reconciliation does not change those acceptance boundaries.

## Remaining work

Follow the [full roadmap in Journey](docs/journey.md#full-milestone-roadmap). The 55-operation source target is complete; do not repeat accepted integrations or mark later milestones complete from this count.

1. Resolve or explicitly disposition the retained UI/transport findings below before physical acceptance, then prepare the remaining environment-specific M6 acceptance in the table below through separately authorized release work. The source-exit implementation is accepted; do not repeat it or infer live acceptance from synthetic-provider tests.
2. Scope M7 durable events, scheduling/notifications and media processing/retention, preserving provider and deployment boundaries.
3. Prepare M8/M9 release, real Cognito, Owner/Trainer UAT, physical-device and populated recovery evidence. Actual AWS changes, provider actions and deployment require their own authorization.
4. Schedule the M10 packages below by dependency and launch criticality; mutation, latency and Grafana remain planned; dependency automation/audit is partially implemented, with remaining supply-chain work under H4.
5. Map business privacy/retention clauses using [Data lifecycle](docs/data-lifecycle.md); approve category-specific periods and exclusions before any general disposal implementation. Verify existing auth/media worker scheduling and backup/object-copy settings through separately authorized environment work.
6. Deliver the separate public website and its content management after staff-portal acceptance. Preserve the canonical document ownership, the user-requested docs/versions.md inventory, docs/code-owners/index.md navigation map and docs/uat/ role worksheets and all eight existing stashes.

### Dependency/security maintenance and deferred refactors

PR103's grouped Dependabot policy and blocking npm high/critical audit are merged. PR104's PyJWT/urllib3 fixes and browser-runner mirror repair are merged and passed exact-head plus fresh-main verification. They are completed source changes, not active dependent branches. Detailed advisories, first failures and receipts remain in [Journey](docs/journey.md#complete-journey).

The latest recorded security-alert state is the user's **0 open /26 closed** report after PR104. Independent alert reads previously returned403; no fresh alert audit or deployed remediation is claimed by this documentation update. Routine proposals105/107/108 were closed unmerged; closing PRs is not a vulnerability fix. Future grouped updates remain configured under the [runbook policy](docs/runbook.md#dependency-maintenance).

Remaining work: independently reconcile alert/settings access when available, extend Python custom-lock and Compose-image update coverage, assess SBOM/provenance and triage runner OS/browser dependencies. The official Playwright container trial was not adopted; its retained scan found7 high package entries, including a GStreamer fix requiring Ubuntu Pro/ESM. The Ubuntu mirror change fixes download availability, not those findings. No paid service or AWS action is authorized by this backlog.

Optional npm/Actions upgrades require separate compatibility review; the previous combined optional trial's failed unit case remains retained in history. Backend router extraction and its acknowledgement-fixture repair remain unmerged, as does any further feature extraction. PR91/92's accepted changes must not be repeated.

### Developer AWS UAT preparation

The [UAT folder](docs/uat/) merged through PR109 contains separate Owner, Admin and Trainer worksheets with blank Result/Remarks columns. The original92 case IDs and additional Trainer manager-action restriction check remain; none is marked executed or passed. Worksheets target the deployed developer AWS site with designated test identities, real Cognito/email and developer storage. Assisted fault/recovery checks require an arranged test. Drafting does not deploy source or establish live/device acceptance.

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
| H6 / release | AWS release readiness and production operations (runbook merged through PR109): health/readiness, synthetic checks, incidents, rollback, backup/restore, migration recovery, capacity/cost | Tested source/artifact and migration inventory, H2/H5 where relevant; reviewed recovery environment | Reviewed image/provenance/grants/rollout plan; version/digest-bound health and synthetic evidence, incident ownership and drills, measured RPO/RTO, populated restore/forward-recovery and rollback constraints, capacity/cost alerts | Isolated restore drills first; never replay bootstrap, rewrite applied migrations, touch customer data or deploy under source authority |
| H7 / ongoing | Documentation/test impact and obsolete artifact audit | Source reference/loader scan and owners | Updated affected tests/fixtures/inventories, preserved first failures, no stale status, meaningful purpose comments; retain historical evidence by immutable link | No blanket deletion, architecture transplant or comment-only churn; retain the PR59/63 cleanup evidence |

Full dated receipts, first failures and superseded checkpoints live only in [Service Journey](docs/journey.md#complete-journey).
