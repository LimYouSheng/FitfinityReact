# Fitfinity current progress

## Current checkpoint — 28 October 2026, 16:19 Singapore

Accepted **application source** is [PR104](https://github.com/LimYouSheng/FitfinityReact/pull/104), merge `1246fb815b1240a92fd953b85abc05f18f46bc73`. Exact head `c8f0634820758b5d5de229cfab501d7ef6726189` passed all required gates in run40530155757, including both API shards within20 minutes. PyJWT/urllib3 fixes, offline-editor fixture readiness and the Ubuntu mirror selector are merged. Fresh main run40614828297 passed. No current-source Lambda deployment is claimed. Full receipts and original failures remain in Journey.

[The canonical operation matrix](docs/api-contracts.md#domain-operation-inventory) records **55/55 source accepted**: 54 server-connected operations plus one local predicate. All 18 operations remaining at the 37/55 checkpoint are complete in merged source. This does not establish deployment or blanket milestone acceptance.

| Acceptance | Evidence and limit |
| --- | --- |
| Staff-portal source | All named operations and the additional M6 source-exit implementation are source-accepted; live/provider/device acceptance below remains separate. Detailed operation receipts live in Journey. |
| Real API isolation | Actual FastAPI/migrations/PostgreSQL with synthetic records in disposable Docker databases; local signed-token Cognito substitute and actual isolated S3-compatible media storage. No production PostgreSQL or Lambda redeployment needed. |
| Deployment | The merged release workflow requires manual image initiation, exact main SHA, full verification and existing AWS approval. Current-source Lambda deployment, real Cognito and current device acceptance remain unrecorded. Source merge and Pages demo publishing do not establish these outcomes. |

### Checkout and consolidated documentation PR

Active checkout: `docs/dependency-version-inventory`, incorporating PR110/111 through `4c7495312a6903b6087681efdb755ae4e0356658` before this split. All eight existing stashes remain preserved. GitHub main remains `1246fb815b1240a92fd953b85abc05f18f46bc73`; documentation changes are not accepted main.

[PR109](https://github.com/LimYouSheng/FitfinityReact/pull/109) is the single documentation review. It includes the version inventory, BR/code-owner map, role UAT, runbook, development guide, ten architecture ADRs and the requested three-file contract split. PR110/111 are superseded by this consolidated branch; original branches/commits are preserved. No repository skill was created, as requested; AGENTS remains the entry point.

| Canonical document | Current purpose |
| --- | --- |
| [Business rules](docs/business-rules.md) | All64 current BR groups and acceptance constraints, with stable IDs |
| [API contracts](docs/api-contracts.md) | Unchanged55-operation matrix,159 HTTP method/path entries and246 schema references |
| [Journey](docs/journey.md) | Complete retained dated history, first failures, decisions and acceptance evidence |

The combined Service Contracts file is removed, with links redirected to the specific owners. The full milestone roadmap is retained at the top of Journey; the H1–H7 backlog below remains intact. This split passed1,558 local link/anchor checks, all24 current Mermaid diagrams and preservation checks for all64 BR groups,55 matrix rows, all20 milestone/extension rows and the full original history. The159-endpoint/246-schema index matches the checked-in OpenAPI snapshot. PR109 still requires full final-head CI.

**CI finding:** preceding-head [run40650892639](https://github.com/LimYouSheng/FitfinityReact/actions/runs/40650892639) completed with frontend/backend and API shard2 passed. Shard1 had187 passed and1 failed: phone permanent reassignment passed its visible assignment/reload checks, then `/api/directory` verification failed with `ECONNRESET` at `tests-api/records.spec.js:221`. The aggregate correctly rejected a failed shard. This is neither an inventory mismatch nor a deployment-approval wait. Original logs were obtained through the connector and retained; the reset's root cause remains unproven. No assertion, retry or timeout was changed.

**Next action:** verify PR109's consolidated final head and investigate any recurring connection failure using the retained trace/server evidence before a targeted repair. Previous-head run40651160398 was in progress at inspection and cannot accept the consolidated head. Merge only after all three exact-head gates and GitHub requirements pass. No documentation change authorizes image publication, AWS deployment or provider/device acceptance.

## Milestone roadmap

The [full M0–M10 overview in Journey](docs/journey.md#full-milestone-roadmap) owns milestone scope and exit criteria. Progress retains the current acceptance, remaining work and H1–H7 backlog below.

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
