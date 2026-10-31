# Fitfinity current progress and handover

This file owns the **current task, exact stopping point, blockers, next actions and remaining work**. The [milestone overview](docs/journey.md#full-milestone-roadmap) and [complete dated history](docs/journey.md#complete-journey) live in Journey. [NORTH_STAR.md](NORTH_STAR.md) owns reusable campaign procedure; the [documentation skill](.agents/skills/fitfinity-documentation/SKILL.md) owns every-PR documentation reconciliation.

## Current task — post-merge review and documentation reconciliation

Checkpoint: 1 November 2026 (Singapore). PR116 is merged as `1aafcbef6377f36d093260d4a63e57239cfcaefc`. Its exact final head `f4fb46acd6f3332088973dd7b3578aca6f8df987` passed [all required gates](https://github.com/LimYouSheng/FitfinityReact/actions/runs/41233711408). [Fresh-main verification and staff-demo publishing](https://github.com/LimYouSheng/FitfinityReact/actions/runs/41236825212) also passed. This accepts source and demo publishing, not a current-source Lambda rollout or real-provider/physical-device acceptance.

The user requested a new review and accurate documentation. This follow-up removes stale draft/pending claims, corrects the API snapshot totals and records the completed evidence. It does not change runtime behavior or implement the deferred approval-vetting redesign or global2px typography increase.

### Completed in this task

| Item | Evidence / limitation |
| --- | --- |
| Admin management and approvals | System contains Admin and Packages. Owner-only versioned Admin details, fixed approval requirements and lifecycle are merged. New Admins default to Exercise Library and Content approval checked; all other requirements are unchecked. Existing selections are retained. Deactivation invalidates old application sessions; reactivation requires fresh login. |
| Durable approval execution | Frozen original-Admin proposals, current authority/version checks, private notices, immutable decisions and uncertain-outcome recovery cover the registered domain commands. Trainer approval automatically dispatches the reserved invitation; uncertain sends are not resent. Actual provider delivery remains unverified. |
| Upload, download and sharing | Upload/download remain approval-free. Library Save reviews the complete details/attachment before publication. Progress/session sharing have separate optional requirements and an explicit final device Share action. Downloads cannot prevent redistribution outside the app. |
| Independent purchases | Future Singapore start dates, overlapping validity, independent Trainers/credits and package-specific reassignment are merged. Actual booking conflicts remain forbidden. General Details lists associated Trainers; renewal is suppressed by another usable active/upcoming purchase. |
| Recordings | Optional original audio,10MiB original limit,5MiB conversion target and original retention after conversion failure are merged. Isolated HTTP/PostgreSQL/object-storage readback verified exact10MiB bytes; physical capture remains pending. |
| Final-head verification |1504 units/155 files;1422 backend cases against isolated PostgreSQL;396 real-API browser cases/26 files;1155 macOS browser cases;100 quality checks. Backend and infrastructure gate passed; the earlier focused offline infrastructure receipt was636 cases. No skipped tests, retries, increased timeouts or changed runner settings. |
| Original failures and repairs | Fixture dates/navigation, alias serialization, pool isolation, message-alert targeting and both strict browser inventories were repaired. Local Linux finished1153 passed/2 native-touch failures; both unchanged assertions passed in the complete macOS run. Full first-failure and repair history is retained in [Journey](docs/journey.md#complete-journey). |

### Campaign contract and leave-off

| Field | Current checkpoint |
| --- | --- |
| Outcome / scope | Reconcile every affected documentation owner with accepted PR116 source and fresh-main evidence; retain product rules, full history and external acceptance boundaries. |
| Repository / branch | Existing checkout on `docs/post-116-reconciliation`, based on main1aafcbe. PR116 is closed/merged. Preserve all8 stashes. This documentation follow-up needs its own published-head CI before merge. |
| Acceptance | Verify operation/schema counts and evidence links; inspect affected rule, security, lifecycle, navigation and UAT owners; validate links/fences and unchanged diagram bodies. Full local runtime suites are reused from identical accepted source; follow-up GitHub gates remain required. |
| Budget | One bounded documentation-review block, up to6 substantive iterations/90 minutes; no unrelated code changes, agents, paid resources or production data. |
| Unresolved | Follow-up documentation publication/CI remains pending. Local Linux synthetic-touch limitations are recorded, not a failed macOS source gate. AWS/provider/device/recovery work remains below; deferred UI work remains deferred. |
| External boundary | No Lambda deployment, live invitation or cleanup activation occurred. Current-source real Cognito, populated recovery and physical desktop/Samsung/iPad UAT require separate evidence. General inactive-record disposal remains undecided. |

### Resume in this order

1. Validate and publish this documentation reconciliation; require its complete exact-head CI and GitHub requirements before source merge. Do not redo accepted PR116 implementation.
2. Resume the separately scoped developer-AWS/M6 acceptance plan only through a concrete reviewed deployment plan and applicable authorization. Verify source/artifact/schema bindings and rollback compatibility first.
3. Perform real-provider and physical-device acceptance with the role worksheets, recording failures and perceived lag. Synthetic Cognito and native-share substitutions are not live-provider/device evidence.
4. Keep approval-vetting redesign and global2px typography work deferred until resumed. Monthly cleanup activation and general inactive-record disposal remain distinct operational/policy tasks.

## Current acceptance boundaries

The [canonical operation matrix](docs/api-contracts.md#domain-operation-inventory) retains the original **55/55 source-accepted operations:54 server-connected operations and one local predicate**. PR116 separately adds three source-accepted Admin-management operations, making58 named operations in current source. Their acceptance comes from PR116’s final-head and fresh-main receipts, not from inheriting the earlier milestone count.

M6 source exit is accepted; live/provider/device evidence remains outstanding. Real-API verification uses actual FastAPI, migrations, PostgreSQL and isolated object storage with synthetic records and a local signed-token Cognito substitute. No production PostgreSQL is used. GitHub Pages staff-demo publishing passed; no current-source Lambda deployment, live-provider acceptance or current physical-device/UAT receipt is recorded.

## Remaining work

Follow the [full roadmap in Journey](docs/journey.md#full-milestone-roadmap). The 55-operation source target is complete; do not repeat accepted integrations or mark later milestones complete from this count.

1. Resolve or explicitly disposition the retained UI/transport findings below before physical acceptance, then prepare the remaining environment-specific M6 acceptance in the table below through separately authorized release work. The source-exit implementation is accepted; do not repeat it or infer live acceptance from synthetic-provider tests.
2. Scope M7 durable events, scheduling/notifications and media processing/retention, preserving provider and deployment boundaries.
3. Prepare M8/M9 release, real Cognito, Owner/Trainer UAT, physical-device and populated recovery evidence. Actual AWS changes, provider actions and deployment require their own authorization.
4. Schedule the M10 packages below by dependency and launch criticality; mutation, latency and Grafana remain planned; dependency automation/audit is partially implemented, with remaining supply-chain work under H4.
5. Map business privacy/retention clauses using [Data lifecycle](docs/data-lifecycle.md); approve category-specific periods and exclusions before any general disposal implementation. Verify existing auth/media worker scheduling and backup/object-copy settings through separately authorized environment work.
6. Deliver the separate public website and its content management after staff-portal acceptance. Preserve the canonical document ownership, the user-requested docs/versions.md inventory, docs/code-owners/index.md navigation map and docs/uat/ role worksheets and all eight existing stashes.

7. **Approval vetting UI cleanup — documented, implementation deferred by the user (1 November 2026).** Review all approval screens for a consistent, uncluttered layout rather than polishing only Exercise Library. Depends on stable proposal/decision contracts, protected attachment preview and approved publication behavior. Exercise Library’s Messages → Review panel should show requesting Admin/time and new/edit intent; name/category/description/proposed active status; playable video or image preview with filename/size; current-versus-proposed changes for edits, including attachment replacement/removal; and **Approve & Save**, **Reject**, **Back**. No library-wide Publish button is agreed. Acceptance evidence: desktop/phone/tablet readability and keyboard navigation, complete exact-intent review, foreign-attachment denial, stale-review rejection without overwrite, rejection preserving the existing entry, original-key recovery after lost responses, and fresh-login verification that Trainers see only the approved version. Rollout boundary: no visual redesign now; resume with a reviewable design before implementation, preserve server guards, and obtain complete final-head verification before source acceptance. No AWS/provider actions are authorized by this backlog.

8. **Global typography increase — documented, implementation deferred with UI cleanup (1 November 2026).** Increase every application UI text size by2px from its existing baseline, including headings, navigation, labels, inputs/selects, buttons, tables, calendars, dialogs, approval panels, helper/error/status text and empty states. This is app-wide, not limited to approval screens. Dependencies: inventory the shared typography tokens and component-specific font sizes, including responsive rules, before editing their canonical style owners. Acceptance evidence: verify the2px increase across representative computed styles and all roles; inspect desktop/phone/tablet layouts, keyboard focus and browser zoom for clipped/truncated labels, unintended overflow, inaccessible controls and broken wrapping; retain readable hierarchy and complete existing frontend/browser gates. Rollout boundary: document now, implement when the deferred UI work resumes; do not claim this visual change is already present.

### Dependency/security maintenance and deferred refactors

PR103's grouped Dependabot policy and blocking npm high/critical audit are merged. PR104's PyJWT/urllib3 fixes and browser-runner mirror repair are merged and passed exact-head plus fresh-main verification. They are completed source changes, not active dependent branches. Detailed advisories, first failures and receipts remain in [Journey](docs/journey.md#complete-journey).

The latest recorded security-alert state is the user's **0 open /26 closed** report after PR104. Independent alert reads previously returned403; no fresh alert audit or deployed remediation is claimed by this documentation update. Routine proposals105/107/108 were closed unmerged; closing PRs is not a vulnerability fix. Future grouped updates remain configured under the [runbook policy](docs/runbook.md#dependency-maintenance).

Current observed npm audit in run41228690689 reports five moderate development-dependency findings rooted in minimatch glob-parts amplification, propagated through ESLint packages; the configured high/critical gate passed. This is an npm audit receipt, not a fresh GitHub-alert count. Triage a compatible upstream patch under H4; no forced downgrade/upgrade or vulnerability suppression is included in the approval-workflow candidate.

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
