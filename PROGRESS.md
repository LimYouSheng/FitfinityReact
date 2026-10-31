# Fitfinity current progress and handover

This file owns the **current task, exact stopping point, blockers, next actions and remaining work**. The [milestone overview](docs/journey.md#full-milestone-roadmap) and [complete dated history](docs/journey.md#complete-journey) live in Journey. [NORTH_STAR.md](NORTH_STAR.md) owns reusable campaign procedure; the [documentation skill](.agents/skills/fitfinity-documentation/SKILL.md) owns every-PR documentation reconciliation.

## Current task — documentation and testing skills for every PR

Checkpoint: 31 October 2026 Singapore. PR113 merged as `0a36e8138be64680b349f5b9cbd76ae7d3e678bb` after all final-head gates passed on `ef458800f011570318fbb1f16d028df641a07b8c`. Fresh-main [run40811886578](https://github.com/LimYouSheng/FitfinityReact/actions/runs/40811886578) passed; PR112 fresh-main run40803386013 passed. Current scope is repository documentation and testing skills with explicit AGENTS entry points in draft PR114, not CI enforcement mechanisms.

### Completed in this task

| Item | Current evidence |
| --- | --- |
| Skill | `.agents/skills/fitfinity-documentation/SKILL.md` defines triggers, owner impact review, exact acceptance states, validation, delivery-event handling and a concise PR receipt. |
| Discovery | AGENTS requires explicit reading for every PR; hosts with repository skill discovery can also use its frontmatter. No claim that the current session's skill catalog auto-reloads. |
| Validation | Both skills’ YAML/name/description and 6 GFM tables, explicit AGENTS fallbacks, 20 Markdown files / 1,816 local links and balanced fences passed. Evidence-owner paths and prior Journey, business/API requirements, CI and verifier bytes preserved. |
| Testing skill | Expanded with same-PR runtime/schema/verifier/environment guard impact and positive/negative evidence, plus recurring-failure comparison, bounded diagnosis and causal repair criteria. Added `.agents/skills/fitfinity-testing/SKILL.md`, adapted from SoccerBot to actual Fitfinity unit/simulator/real-API/backend/infrastructure owners, strict verifiers and browser permissions. Includes every-PR test-impact receipt. |
| Development naming | Renamed the managed development route to Cloud Containers and updated its navigation anchor and AGENTS directory label. Existing browser/data/permission boundaries remain unchanged. |
| Campaign integration | NORTH_STAR checkpoint step invokes the skill; engineering authority and campaign budgets are unchanged. |
| State discipline | Progress/Journey updated for each PR; all other owners reviewed and changed when affected. Final-head green is recorded in the PR receipt without creating an endless status-commit loop. |

### Campaign contract and leave-off

| Field | Current contract |
| --- | --- |
| Outcome / scope | Two complementary documentation/testing procedures in repository SKILL.md files, wired into AGENTS/campaign guide; accurate current handover and dated evidence. No application/dependency/infrastructure change. |
| Starting evidence | Main `0a36e81`; existing checkout, branch `docs/documentation-state-skill`. Unknown work/stashes/older branches preserved. |
| Acceptance | Valid skill frontmatter and explicit discovery fallback; every canonical owner covered; update/no-change/pending classification; link/fence checks; previous history and domain requirements retained; full final-head CI before merge. |
| Work queue | Draft → inspect owner/discovery/acceptance semantics → validate → publish draft with documentation receipt → exact-head gates. |
| Budget | Initial 6-iteration/90-active-minute work block; documentation drafting/validation and testing-skill adaptation complete (3/6); expanded-skill validation complete (4/6). New 31 October work block: guard/failure guidance and naming drafted/validated (2/6); publish next. No new paid resource authority or claimed metered spend. |
| Unresolved evidence | Earlier PDF export timeout, clipped trace navbar and reassignment ECONNRESET remain unexplained. Subsequent green CI did not repair or diagnose them. |
| External boundary | Real Cognito, Lambda release, physical UAT, alert activation and tested restore remain independently pending; the skill grants no authority for them. |

### Resume in this order

1. Validate both skills, owner/verifier references, links and preservation; update draft PR114 with documentation-state and test-impact receipts.
2. Inspect PR113 fresh-main CI separately, then this PR's exact-head gates. Preserve new failures and update the current receipt honestly.
3. Merge only the eligible tested head. Reconcile merged/fresh-main state in the PR receipt and next substantive repository checkpoint as the skill specifies; no direct-main or recursive status-only changes.

## Current acceptance boundaries

The [canonical operation matrix](docs/api-contracts.md#domain-operation-inventory) remains **55/55 source accepted:54 server-connected operations and one local predicate**. M6 source exit is accepted; the remaining live/provider/device evidence is listed below. Real-API verification uses actual FastAPI/migrations/PostgreSQL and isolated object storage with synthetic records and a local signed-token Cognito substitute. It does not use production PostgreSQL and needs no Lambda redeployment.

No current-source Lambda deployment, real Cognito acceptance or current physical-device/UAT receipt is recorded. Historical application receipts and full milestone scope are in [Journey](docs/journey.md); documentation reconciliation does not change those acceptance boundaries.

## Remaining work

Follow the [full roadmap in Journey](docs/journey.md#full-milestone-roadmap). The 55-operation source target is complete; do not repeat accepted integrations or mark later milestones complete from this count.

1. Complete the documentation-state skill and its verification, then prepare the remaining environment-specific M6 acceptance in the table below through separately authorized release work. The source-exit implementation is accepted; do not repeat it or infer live acceptance from synthetic-provider tests.
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
