# Fitfinity current progress and handover

This file owns the **current task, exact stopping point, blockers, next actions and remaining work**. The [milestone overview](docs/journey.md#full-milestone-roadmap) and [complete dated history](docs/journey.md#complete-journey) live in Journey. [NORTH_STAR.md](NORTH_STAR.md) owns reusable campaign procedure; the [documentation skill](.agents/skills/fitfinity-documentation/SKILL.md) owns every-PR documentation reconciliation.

## Current task — optional recording audio and monthly cleanup policy

Checkpoint: 31 October 2026. The user requested an original-audio checkbox and selected monthly S3 cleanup. Existing limits and seven-day playback expiry remain unchanged. AWS deployment remains paused; no AWS action or scheduler activation has occurred. PR115 merged at `764ce1fff6c6c4c602b9f6caea949bc7e1279b30` after exact-head run 41201564978 passed all three required gates; fresh-main verification is separate. The earlier PDF stall's exact cause remains unproven despite the accepted mitigation and retained evidence in Journey.

### Completed in this task

| Item | Evidence / limitation |
| --- | --- |
| Optional original audio | Checkbox defaults off and freezes with the prepared candidate. Canvas caption conversion uses Web Audio only when requested; no microphone capture or speaker output. Preview playback can be heard. Deferred originals explicitly say captions/audio selection were not applied. |
| Actual encoded output | Chromium synthetic 440Hz clip: unchecked output has VP8 video only; checked output has VP8+Opus with audible samples (mean−21.1dB). Roughly 1.1s conversion for a 1s clip; not a device latency budget. |
| Isolated persistence |9/9 focused session-media browser cases passed across desktop Chromium and phone/tablet WebKit profiles, including audible saved bytes after fresh sign-in where converted, lost-response recovery, stale writes, foreign denial and durable removal. Actual PostgreSQL and isolated object storage; no AWS/customer data. |
| Unit/guard coverage | Four dialog regressions cover default silent, opted-in audio, honest fallback and cancelled late result. Unit inventory updated to 1476 cases/151 files; full candidate run passed (112.87s). API inventory remains369; existing cases were strengthened. Lint, code health and98 quality guards passed, including the additional stale-inventory rejection fixture. |
| Monthly policy | Routine session-media physical cleanup selected for the first day in Asia/Singapore; exact time and activation remain release work. Runbook requires draining beyond the 100-item CLI bound, retry execution and backlog evidence. Expiry still denies playback after 7 days; S3 versions/backups need separate inspection. |

### Campaign contract and leave-off

| Field | Current checkpoint |
| --- | --- |
| Outcome / scope | Add optional original audio with truthful browser fallback and record monthly cleanup policy; BR049/050. |
| Repository / branch | Existing checkout, `feat/session-video-audio`, based on main764ce1f. Preserve all 8 existing stashes. |
| Acceptance | Meaningful silent/audio output checks, focused real-API persistence and all three final-head CI gates before eligible merge. |
| Budget | One bounded 90-minute block; no new dependencies, cloud services or AWS changes. |
| Unresolved | Safari/physical capture/audio behavior remains device acceptance; Firefox is outside automated coverage. Monthly scheduler, retry orchestration, bucket versioning/copy erasure and measured cleanup cost remain unverified. Original PDF stall remains a mitigation with unproven root cause. |
| External boundary | Current-source Lambda, real Cognito, populated recovery and desktop/Samsung/iPad UAT remain separate from source acceptance. |

### Resume in this order

1. Publish the separately verified audio/policy PR and inspect final-head CI. Full 1476-unit/151-file validation, 9 focused API cases, 98 quality guards, lint/code health and documentation checks passed.
2. Require all three exact-head CI gates and normal GitHub requirements before source merge; track fresh-main separately. Do not claim unchecked browser/physical compatibility.
3. Prepare developer AWS acceptance only after the user's paused reliability objective is resolved or remaining uncertainty is explicitly accepted. Bind source/artifacts, migrations, backup/recovery and rollback; no bootstrap replay.
4. During separately authorized media rollout, implement and verify the monthly schedule, bounded draining/retries and actual bucket-copy deletion behavior. A documented policy is not a running scheduler.
5. Complete designated real-Cognito and physical M6 worksheets before M7; keep remaining engineering packages below.

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
