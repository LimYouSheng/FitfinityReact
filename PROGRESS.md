# Fitfinity current progress

## Current checkpoint — 23 October 2026 Singapore

Verified GitHub main is `df9cbbb75373eb7e57b31187eeb93077ea35cec8` (PR58). The restored checkout was clean but stale at `8945ca1`; fetched main and created `test/integrated-real-api-postgres` in the existing checkout. No unknown edits were discarded. Node24.19.0, Python3.12.14 and Docker28.4.0 are available; restored dependency/image receipts require input checks before reuse.

**27/55 integrated in merged source: 26 server-connected operations plus one local predicate.** Trainer update remains partial and 27 other operations are incomplete. [Service Contracts](docs/SERVICE_CONTRACTS.md#domain-operation-inventory) owns the only operation matrix. Reconciliation: its 25 connected rows plus the local predicate previously excluded Trainer deactivation; PR55's final CI subsequently passed and it merged. PR57 includes fixed weekly scheduling and session reads. Read routes do not add named operations. Counts of endpoints or browser cases are different inventories.

| Acceptance level | Verified evidence / limit |
| --- | --- |
| Implemented / merged | PR55 (including54), PR57 (including56), PR58 merged; main above |
| Final PR CI | [PR55 run38476697547](https://github.com/LimYouSheng/FitfinityReact/actions/runs/38476697547), [PR57 run38820138715](https://github.com/LimYouSheng/FitfinityReact/actions/runs/38820138715), [PR58 run38834044790](https://github.com/LimYouSheng/FitfinityReact/actions/runs/38834044790) succeeded; PR58 includes frontend/backend/api-browser |
| Real API browser | Candidate full63/63 passed locally with Playwright1.64.1 and isolated PostgreSQL per worker. Final-head CI remains required; prior failures are retained below |
| Backend | Full local gate passed970/970 backend and633/633 offline infrastructure cases; worker-isolation checks passed13/13. PR60 head29f68d2 backend CI passed the expanded975-case gate; final dependency-update head still requires CI |
| Simulator / demo | 18 HTTP simulator spec files; existing browser inventory1152. These do not prove browser→FastAPI→PostgreSQL persistence |
| Current candidate | Draft [PR60](https://github.com/LimYouSheng/FitfinityReact/pull/60) contains the documentation refactor, operation evidence map,63-case browser expansion, Docker stage separation and onboarding selection fix. Playwright1.64.1 follow-up passed locally; no merge claimed |
| Independent main CI | Historical ECR429 reported in handoff; connector returned no main-SHA runs during this audit. Do not infer a pass or repair |
| Deployment / provider | No AWS query or deployment this task. Retained runbook source/image remains historical; new integrations are not live-accepted |

Draft [PR59](https://github.com/LimYouSheng/FitfinityReact/pull/59) removes one historical fixture and updates the old ledger; head `01ef52916ca576cad3ebd76e5253b06127759620`, CI39881298542 now has successful frontend/backend jobs but its api-browser job was cancelled during browser installation; that is not complete final-head acceptance. Preserve its intended cleanup; reconcile its ledger when integrating. Do not approve obsolete image workflow78 to unblock a queue.

## Active sequence and acceptance

| Priority | Task | Dependencies | Completion evidence / boundary |
| --- | --- | --- | --- |
| 0 | Refactor docs and record hardening backlog | Inspect current source and SoccerBot recent merges | One reading order, North Star, ledger and operation matrix; historical evidence retained; links and consistency checked; source-only |
| 1 | Real API tests for all26 integrated server operations plus local-predicate evidence | Coverage audit; isolated PostgreSQL harness; ECR dependency repair | Trace every operation to actual route/DB tests, UI writes + reload/fresh login, foreign-record role checks, conflicts/retry/interruption; no simulator-only acceptance; final frontend/backend/api-browser CI |
| 1a | Separate app/test base from production Lambda-adapter stage | Inspect Docker and infrastructure guards | Tests build without adapter pull; production runtime retains adapter, user, entrypoint and source; validate both paths; no image publication or AWS change |
| 2 | Session scheduling writes / requests / approvals | Priority1 accepted; reuse session reads and weekly review | Complete next matrix operation with atomic persistence, permissions, prototype parity and real-browser evidence; do not redo completed operations |
| 3 | Plans/outcomes/summary/acknowledgement/credits | Scheduling dependencies | Durable histories, finality and exactly-once credit evidence |
| 4 | Remaining assessment/report/media and messaging/Undo/remuneration/profile gaps | Relevant owning operations | Permission, storage/recovery and full workflow evidence; Trainer email verification remains required |
| 5 | Release and live acceptance | Tested merged source; reviewed deployment plan | Separate authorization for AWS/image/provider actions; real Cognito, restart/recovery and devices distinct |

## Candidate validation and remaining work

- Docker test and runtime builds passed locally with the environment's public CA trust configuration. Test image omits the Lambda adapter; runtime retains it, UID10001 and the existing launch command, and excludes test code. No image was published.
- Every connected matrix row now links its real PostgreSQL/HTTP test owners. The local directory predicate has23 passing directory-unit cases, including its role variants; it is not a database operation.
- Browser candidate:21 scenarios across three projects (63 cases). Responsive navigation and real-response-loss injection repaired harness defects. A62/63 run exposed legitimate stale Trainer-catalogue reviews between parallel tests; separate worker databases now isolate scenarios without altering concurrency or relaxing conflicts. The isolated53/63 run exposed an onboarding default-selection race (fixed with a form regression) and WebKit stalls. Subsequent desktop21/21 passed.
- [PR60 CI39888114739](https://github.com/LimYouSheng/FitfinityReact/actions/runs/39888114739), head29f68d2: backend passed; API browser51/63 failed with WebKit internal network errors and `corrupted double-linked list`. [Upstream Playwright issue42803](https://github.com/microsoft/playwright/issues/42803) identifies bundled libsoup3.6.5 memory corruption, fixed in Playwright1.64. Pinning1.64.1 supplies libsoup3.6.6 (verified in the downloaded engine). The matching local Docker runner passed **63/63** in3 minutes, with unchanged assertions, concurrency, retries and timeouts. Final-head CI, including existing1152 browser cases, remains required. First-failure traces and logs are retained outside the checkout under `/workspace/work/fitfinity-handoff/`.
- Full unit gate1248/1248 in128 files passed after the onboarding selection fix; lint456 files, health222 reachable runtime modules and47 quality-checker tests passed. Temporary diagnostics are removed. Final frontend/backend/api-browser CI remains required.
- The backend harness rejects non-isolated database URLs before connecting. All data is synthetic, Compose projects/databases are temporary, Cognito signing/provisioning/delivery are local substitutes, and no production PostgreSQL/AWS resources are used.

## Engineering-hardening backlog (planned, not provisioned)

This is the only task ledger. Priorities below follow integrated-operation evidence; introduce tools only in a scoped implementation task. No paid services, AWS changes or deployment are authorized merely by this list.

| ID / priority | Scope | Dependencies | Acceptance evidence | Rollout boundary |
| --- | --- | --- | --- | --- |
| H1 / next | Mutation testing for critical JS/Python authorization, scheduling, credits, idempotency and persistence | Real-DB coverage map; stable focused tests | Baseline mutants by owner, classify surviving/equivalent/uncovered mutations, repair meaningful gaps; justify per-area gates from baseline, retain time/cost report | Start bounded locally/CI; do not substitute mock-only mutations for DB invariants or set arbitrary global score |
| H2 / next | Latency/throughput/errors/resources; p50/p95/p99, concurrency, representative data, cold/warm starts, DB queries and browser performance | Repeatable isolated data, functional correctness, source/environment fingerprints | Bounded baseline/fault/overload cohorts; sample counts, duration, query/connection/memory/CPU data and browser vitals; measured budgets and regression thresholds after baseline | Synthetic isolated targets first; no production load or claimed Lambda cold-start evidence from local containers |
| H3 / next | Secret scanning, static analysis and permission regression; rate limits, dependency failures, interrupted-write recovery | Permission matrix and operation coverage | Negative-role/foreign-record checks, forged actors, stale authority, 429/503/disconnect/restart recovery and no duplicate/partial writes; review false positives | Inspect supported GitHub controls before enabling; provider faults synthetic; no credential disclosure |
| H4 / next | Dependabot for npm/Python/Actions/container images; supply-chain review | Inventory exact pins/lockfiles, supported update ecosystems and CI | Grouped reviewed update PRs, lockfile/hash validation, vulnerability severity/triage deadlines, all final-head CI; assess SBOM and artifact/source provenance with verified digest | No auto-merge or unreviewed runtime updates; account settings remain unverified until read; provenance generation is not deployment |
| H5 / later | OpenTelemetry traces/metrics/structured logs and Grafana dashboards | H2 baseline, threat/data review, stable request correlation | Cross-layer correlation, latency/error/saturation dashboards, proposed SLOs/error budgets and actionable alert/runbook exercises; redact health/PII, tokens/cookies, SQL parameters; test sampling, retention, cardinality, export failures and cost caps | Prepare default-disabled instrumentation first; separately approve stack/credentials/ingestion/production activation; no planned-capability claim |
| H6 / release | Production operations: health/readiness, synthetic checks, incidents, rollback, backup/restore, migration recovery, capacity/cost | Release runbook, H2/H5 where relevant; reviewed recovery environment | Version/digest-bound health and synthetic evidence, incident ownership and drills, measured RPO/RTO, populated restore/forward-recovery and rollback constraints, capacity/cost alerts | Isolated restore drills first; never replay bootstrap, rewrite applied migrations, touch customer data or deploy under source authority |
| H7 / ongoing | Documentation/test impact and obsolete artifact audit | Source reference/loader scan and owners | Updated affected tests/fixtures/inventories, preserved first failures, no stale status, meaningful purpose comments; retain historical evidence by immutable link | No blanket deletion, architecture transplant or comment-only churn; coordinate PR59 |

## SoccerBot practices reviewed and disposition

Inspected current AGENTS, README, North Star, Progress and Service Contracts, plus latest merged PRs89,88,87,86 and engineering additions80,83,84. Source links below explain the adaptation; Fitfinity's own permissions and architecture govern execution.

| Source | Adopt / adapt / defer and reason |
| --- | --- |
| [PR89 document ownership](https://github.com/LimYouSheng/SoccerBotStudioSG/pull/89), [PR86 consolidation](https://github.com/LimYouSheng/SoccerBotStudioSG/pull/86) | Adopt one owner per document, clear current/history separation and short entry point. Keep Fitfinity's established specialist documents rather than recreating SoccerBot topology |
| [PR88 function summaries](https://github.com/LimYouSheng/SoccerBotStudioSG/pull/88) | Adapt concise purpose/constraint summaries for substantial new functions and test-impact review; defer bulk comment rewrite |
| [PR87 obsolete artifacts](https://github.com/LimYouSheng/SoccerBotStudioSG/pull/87) | Adopt reference/loader checks and immutable evidence links before cleanup; preserve PR59 and unknown files |
| [PR83 load campaign](https://github.com/LimYouSheng/SoccerBotStudioSG/pull/83), [PR84 overload recovery](https://github.com/LimYouSheng/SoccerBotStudioSG/pull/84) | Adapt bounded baseline/fault/overload campaigns, exact retry identity, failure receipts and source fingerprints to FastAPI/PostgreSQL; synthetic capacity does not establish production throughput |
| [PR80 telemetry](https://github.com/LimYouSheng/SoccerBotStudioSG/pull/80) | Adapt redaction allowlists, disabled export, bounded sampling/cost, failure isolation and honest correlation limits; defer Grafana activation and omit Cloudflare Tail/DO specifics |
| [Current Progress](https://github.com/LimYouSheng/SoccerBotStudioSG/blob/main/PROGRESS.md) | Adopt separate PR versus main/release acceptance and explicit security-maintenance gaps. Do not import owner-only browser execution or its merge/provider rules; Fitfinity authorization governs |

## Historical evidence

The complete prior ledger is retained at [main before refactor](https://github.com/LimYouSheng/FitfinityReact/blob/df9cbbb75373eb7e57b31187eeb93077ea35cec8/PROGRESS.md); [Journey](docs/FITFINITY_JOURNEY.md) retains earlier decisions. In particular, the full local baseline had five native-touch/WebKit failures, assertions unchanged; later authoritative macOS PR CI passed. Historical local failures are not erased by that pass. The AWS runbook owns exact retained deployment identities and expired exception evidence; old approvals never renew themselves.
