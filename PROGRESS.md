# Fitfinity current progress

## Current checkpoint — 23 October 2026 Singapore

Accepted main is `ba00ca51a68dd003aad461f080f7c385c9589d26` (PR60). Final PR60 head `09c0596818e21c3136d424216dfb2346e9ebba38` passed frontend/backend/api-browser in [run39890050639](https://github.com/LimYouSheng/FitfinityReact/actions/runs/39890050639): 1248 units, 1152 simulator browser cases, 975 backend, 633 infrastructure and 63 real-API browser cases. No deployment or production PostgreSQL access was performed.

**27/55 integrated in merged source: 26 server-connected plus one local predicate.** Trainer update remains partial; 27 other operations remain incomplete. [Service Contracts](docs/SERVICE_CONTRACTS.md#domain-operation-inventory) owns the only operation matrix. The earlier26/55 omitted Trainer deactivation, subsequently accepted in PR55. Session/calendar reads do not add named operations.

| Work | Current state / acceptance boundary |
| --- | --- |
| PR60 | Merged: real PostgreSQL coverage expansion, Docker application/test/runtime separation and initial documentation cleanup. The initial cleanup did **not** fulfill the requested architecture-folder refactor. |
| Documentation correction | Current branch `docs/architecture-and-contracts`: SoccerBot-style Architecture explanation/diagrams, concise contracts retaining55 rows, historical material relocated, unique ownership and current ledger corrected. Local55-operation registry equality, current link/anchor checks, history-preservation checks and633/633 offline infrastructure tests passed. Final-head CI remains pending. |
| PR59 cleanup | Original head01ef529: frontend/backend passed; API browser cancelled during engine installation before tests. It also conflicts with main. Its sole fixture deletion is carried into this documentation candidate; its obsolete ledger is replaced here, not cherry-picked. PR59 is closed as superseded by [PR63](https://github.com/LimYouSheng/FitfinityReact/pull/63); acceptance belongs to that replacement's final CI/merge. |
| PR61 numbering | Original head9c8c887 passed all three jobs in run39894499184, but GitHub required an updated base. Updated heada066c23 includes main; run39898033276 is the new acceptance gate. No bypass or auto-merge. Does not increase27/55. |
| PR62 booking edits | Candidate head71b99e2 on PR61 dependency. Local1255 units,1006 backend,633 infrastructure and75 real-API browser cases passed. Its own final CI and current-base requirements remain required; it is not accepted main. |
| Postponement candidate | Resumed on `feat/session-postponement-api`; the original named local stash remains preserved. Focused101 backend/46 frontend passed. Full browser82/87: three outdated disabled-button assertions and two message-opening failures. A new regression reproduces an active read being exposed as recovery-pending. Fix and validate before publication; no completed-operation claim. |
| Deployment / provider / devices | Separate pending evidence. Synthetic Cognito is substituted in test; API and isolated Docker PostgreSQL are real. No image publication, AWS changes or production test traffic under this work. |

## Immediate next actions

1. Complete this documentation/PR59 reconciliation, validate the55-row inventory, current links, history preservation and fixture consumers, and publish a focused PR.
2. Finish the scheduling candidates with all final-head gates and normal GitHub requirements. Retarget dependencies only after their acceptance; update matrix status only on accepted integration.
3. Repair the reproduced message read/recovery race, strengthen postponement stale/conflict browser coverage, validate full isolated PostgreSQL and browser suites, then continue the remaining operations.

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
| 6 | Approved public website and website content management | Staff portal complete; retained public HTML design and product rules | Separate public-site delivery and acceptance; the55-operation staff goal does not mark the whole website delivered; publishing requires its applicable authority |

## Historical PR60 validation receipts

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
| [PR89 document ownership](https://github.com/LimYouSheng/SoccerBotStudioSG/pull/89), [PR86 consolidation](https://github.com/LimYouSheng/SoccerBotStudioSG/pull/86) | Adopt one owner per document, clear current/history separation and short entry point. Adapt the Architecture folder with explanation and diagrams; retain Fitfinity's own runtime topology and concise operation matrix |
| [PR88 function summaries](https://github.com/LimYouSheng/SoccerBotStudioSG/pull/88) | Adapt concise purpose/constraint summaries for substantial new functions and test-impact review; defer bulk comment rewrite |
| [PR87 obsolete artifacts](https://github.com/LimYouSheng/SoccerBotStudioSG/pull/87) | Adopt reference/loader checks and immutable evidence links before cleanup; carry PR59's verified unused-fixture deletion into the documentation correction; preserve unknown files |
| [PR83 load campaign](https://github.com/LimYouSheng/SoccerBotStudioSG/pull/83), [PR84 overload recovery](https://github.com/LimYouSheng/SoccerBotStudioSG/pull/84) | Adapt bounded baseline/fault/overload campaigns, exact retry identity, failure receipts and source fingerprints to FastAPI/PostgreSQL; synthetic capacity does not establish production throughput |
| [PR80 telemetry](https://github.com/LimYouSheng/SoccerBotStudioSG/pull/80) | Adapt redaction allowlists, disabled export, bounded sampling/cost, failure isolation and honest correlation limits; defer Grafana activation and omit Cloudflare Tail/DO specifics |
| [Current Progress](https://github.com/LimYouSheng/SoccerBotStudioSG/blob/main/PROGRESS.md) | Adopt separate PR versus main/release acceptance and explicit security-maintenance gaps. Do not import owner-only browser execution or its merge/provider rules; Fitfinity authorization governs |

## Historical evidence

The complete prior ledger is retained at [main before refactor](https://github.com/LimYouSheng/FitfinityReact/blob/df9cbbb75373eb7e57b31187eeb93077ea35cec8/PROGRESS.md); [Journey](docs/FITFINITY_JOURNEY.md) retains earlier decisions. In particular, the full local baseline had five native-touch/WebKit failures, assertions unchanged; later authoritative macOS PR CI passed. Historical local failures are not erased by that pass. The AWS runbook owns exact retained deployment identities and expired exception evidence; old approvals never renew themselves.

## Documentation correction evidence

Reference inspected: SoccerBot main96814c08ecef, merged PR89 (ownership/client delivery), PR88 (function summaries), PR87 (obsolete evidence) and PR86 (architecture consolidation). Adopt `docs/Architecture/README.md` and `diagram.md`; keep Fitfinity's own AWS/FastAPI/PostgreSQL/Cognito system and standing browser/merge authority. Its381KB contracts/history file is not copied: Fitfinity current contracts remain concise and frozen detail lives under `docs/history/`. Planned client staging, Tail Worker, D1/DO and provider-specific rules are not Fitfinity capabilities or permissions. H1–H7 retain the requested hardening dependencies/evidence/boundaries.

The full pre-refactor Rules/Architecture and service detail are retained with relative links relocated. The operation matrix exists only in current Service Contracts; Git history preserves the original verbose rows. The former rules filename is a compatibility map with no separate authority. No product/security rule is intentionally relaxed by moving its historical evidence.

## Session booking API work in progress

`feat/session-details-api` continues from PR61 head9c8c887. The unmerged candidate adds reviewed Owner/Admin booking changes, immutable actor-private retry receipts, atomic history/notices and chronological positions. The expanded23 booking cases and52 schema/contract cases passed against isolated Docker PostgreSQL (75/75). Seven focused adapter cases pass, including the configured application boundary and response-loss reconciliation. The first browser run exposed a missing configured-service binding; it is fixed with a regression test. Browser/full acceptance remains pending; no new operation is counted until UI persistence, conflict and recovery coverage passes. Source integration remains27/55.

Booking validation checkpoint: full frontend units1255/1255 in129 files, lint459 files, source health223 reachable runtime modules,20 health-checker cases and47 quality-checker cases passed. The12-case focused real-browser run passed11; phone fresh-login persistence reached its deadline while full unit/backend/checker jobs shared the host (load average13.27). Trace shows the persisted14:00–15:00 state in the fresh Admin session. This is retained as a failure, not acceptance. No timeout/retry/concurrency setting changed; the full75-case real-API browser gate will run separately after backend completion. The earlier configured-service binding and synthetic Open-fixture defects are fixed.

## Booking validation complete locally; postponement next

Draft [PR62](https://github.com/LimYouSheng/FitfinityReact/pull/62), head `71b99e2a22b6780718a64a8218e5174883d32954`, passed1006/1006 backend/PostgreSQL cases,633/633 offline infrastructure cases,1255/1255 units in129 files, and the full75/75 real-API browser cases (including12 new booking cases). The standalone browser run retained all original settings and passed its strict receipt validator after other heavy local jobs finished. Previous failures above remain historical evidence. Final-head CI [run39895921353](https://github.com/LimYouSheng/FitfinityReact/actions/runs/39895921353) is pending; this is not a merged or deployed operation. PR61 backend and63-case API-browser CI passed in run39894499184; frontend is pending.

`feat/session-postponement-api` continues from PR62. Next acceptance: real review and atomic postponement of upcoming current-package bookings, retained IDs/plans/credits/validity, chronological numbering, Owner/Admin or assigned autonomous Trainer application, supervised Trainer proposals without premature calendar changes, actor-private replay/reconciliation, pending-request and stale-review guards, and real UI/database evidence. Approval resolution and Undo remain separately incomplete.

Postponement candidate:18 new HTTP/PostgreSQL cases and affected booking/schema/directory/contract checks passed101/101. Five new adapter cases plus affected UI/contract checks passed46/46; semantic lint passed462 files. An initial test assertion opened a nested connection against the existing one-connection pool; moving that assertion outside the active transaction fixed the fixture without changing pool/time limits. Full87-case real-API browser validation is running. PR62 backend and75-case API-browser CI passed in run39895921353; frontend remains pending.

## Postponement validation follow-up — 23 October

PR59 is closed as superseded by documentation/cleanup PR63 (head4b234ab); that replacement contains the missing Architecture folder and concise55-row contracts. Its final CI is pending. Scheduling source below remains a candidate.

Full postponement browser run1:82/87; run2:86/87. A background snapshot exposed an active message-read save as uncertain recovery; the new unit reproduces the failure before repair. Active saves are now excluded from recovery projections until their outcome is uncertain. A second regression reproduces session-detail refresh unmounting a reviewed dialog; retain the same authorized identity/generation while refreshing. Focused services37/37 and session-detail4/4 pass after fixes. Full backend/unit/browser gates remain in progress/pending; unchanged timeouts, assertions and concurrency. First failure evidence remains outside the checkout.

Independent main run39894139373 passed backend/API browser but failed1/1152 simulator cases: desktop sidebar scroll-lock expected body top-120px, observed0px. Retrieved its trace via the connector after direct artifact download was forbidden. No main rerun or passed-main claim; scroll/navigation timing remains to diagnose. This is distinct from PR60's green final-head receipt.

The documentation merge removed the unused fixture while a local health-checker copy was already running; that invocation failed with ENOENT. Rerun that checker on the settled source; do not change its assertions.

## Current scheduling repair checkpoint

The message read and same-session detail refresh regressions now pass (37 affected service cases and4 detail-route cases). The sidebar main failure exposed a delayed animation-frame restoration that can overwrite scrolling after the page is interactive; the new two-case regression fails before the repair and verifies both retained user scrolling and normal saved-position restoration after it. Combined affected regression run40/40 passed. Full1262-unit gate passed before this final navigation repair; expanded1264-unit gate is running. Lint462 files, health224 reachable modules,47 quality-checker and20 health-checker cases passed; the failed checker invocation caused by the concurrent fixture removal remains recorded above.

PR63 head4b234ab has successful backend/API-browser CI in run39899636421; frontend remains pending. Source is not yet merged, deployed or production-accepted. Once documentation acceptance lands, the scheduling candidate can carry the already-tested PR61/62 dependencies through one final aggregate gate instead of treating their earlier heads as acceptance for later changes. All GitHub requirements still apply.
