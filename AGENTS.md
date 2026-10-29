# Fitfinity engineering

## Authority and document ownership

For every PR and delivery-state review, read and apply the repository [documentation reconciliation skill](.agents/skills/fitfinity-documentation/SKILL.md). This includes documentation-only and automated dependency PRs. Read it explicitly when the host does not discover repository skills. Review all document owners, update every affected one and include its documentation-state receipt; this is an instruction requirement, not an installed CI hook.

This file owns engineering instructions. User instructions take precedence. Old root Journey, Rules & Architecture, CODEX_CLOUD, AWS_DEPLOYMENT_RUNBOOK and history-folder references are superseded; do not recreate those files. The user-requested docs/journey.md is the current complete-history owner. The user-requested `docs/runbook.md` is the current operational procedure owner. Documentation paths under `docs/` are lowercase; keep the remaining conventional root filenames unchanged. Root README.md was removed at the user’s request; use this directory and the development/runbook references instead.

| File | Unique purpose |
| --- | --- |
| [Owner](docs/uat/owner.md), [Admin](docs/uat/admin.md), [Trainer](docs/uat/trainer.md) worksheets | Role-specific developer AWS acceptance worksheets with blank results/remarks; not executed test receipts |
| [Code owners](docs/code-owners/index.md) | Hierarchical feature/module navigation, responsibility diagrams and the linked function-level technical-behavior/recovery map |
| [Development](docs/development.md) | Local VS Code, Codex Cloud and ZIP workflows; setup, verification commands and PR/CI guidance |
| [Runbook](docs/runbook.md) | Operational checks, incidents, release/recovery procedures and configuration; planned capabilities labelled |
| [Data lifecycle](docs/data-lifecycle.md) | Source-based storage, expiry/deletion inventory and pending policy-to-implementation mapping; not disposal authorization |
| [Security](docs/security.md) | Security trust boundaries, control/evidence map and future layers; not a second rules or backlog owner |
| [Versions](docs/versions.md) | Repository dependency/version inventory and manual patch lookup; not deployed acceptance |
| [Documentation skill](.agents/skills/fitfinity-documentation/SKILL.md) | Every-PR documentation impact review, state reconciliation, validation and delivery receipts |
| [AGENTS](AGENTS.md) | Engineering workflow, verification and action boundaries |
| [Campaign operating guide](NORTH_STAR.md) | Reusable campaign contract, bounded Ralph loop, budgets, evidence and handover procedure |
| [Progress](PROGRESS.md) | Detailed current task, completed work, exact stopping point/handover, blockers, next actions and remaining-work backlog |
| [Architecture decisions](docs/architecture/adr.md) | Stack rationale, tradeoffs, scaling triggers and contingency options |
| [Architecture diagram](docs/architecture/diagram.md) | Component topology and connections |
| [Business rules](docs/business-rules.md) | Current BR requirements, product decisions and cross-cutting acceptance criteria |
| [API contracts](docs/api-contracts.md) | Canonical55-operation matrix, detailed HTTP/schema reference and evidence owners |
| [Journey](docs/journey.md) | Full milestone overview, followed by complete dated decisions, implementation, failures, repairs and acceptance history |


Use this structure as a guide for other projects, but re-establish their runtime, test commands, data boundaries, browser permissions and merge/deployment authority. Fitfinity's permissions and technology choices do not transfer automatically. Keep reusable engineering practice here and project business rules in Business Rules; do not create parallel rulebooks.

## Choose the reading path for the task

Start every task with this file, [North Star](NORTH_STAR.md) and the current [Progress](PROGRESS.md) checkpoint. Then use the relevant route below; current source and actual environment evidence override assumptions from historical receipts. Read the owning BR in full, not just its Code Owners topic label.

| Use case | Read next, in order | Work owner / required result |
| --- | --- | --- |
| Feature development or behavior change | [Business rules](docs/business-rules.md#current-business-rules) → [API contracts](docs/api-contracts.md) → [Code Owners](docs/code-owners/index.md) → relevant source → [Development commands](docs/development.md#verification-commands) | Change the existing feature/domain owner; trace persistence, authority and recovery. Update applicable BR mapping and role UAT; retain meaningful acceptance evidence. |
| Bug investigation / incorrect data | Relevant BR → [Code Owners](docs/code-owners/index.md#11-business-rule-to-owner-index) → [Runbook incidents](docs/runbook.md#5-incident-response-and-recovery) → failing source/tests | Reproduce and distinguish app, fixture, environment and provider failure. Preserve original evidence and verify the focused repair before full gates. |
| Slow or unresponsive UI/API | [Runbook monitoring](docs/runbook.md#4-monitoring-and-observability) → relevant code owner → [Progress H2/H5](PROGRESS.md#m10-work-packages--planned) | Measure device/network/first-repeat/server behavior; record perceived delays. Do not invent budgets or claim planned Grafana is active. |
| Dependency/security maintenance | [Security](docs/security.md) → [Versions](docs/versions.md) → [Runbook policy](docs/runbook.md#dependency-maintenance) → [Runbook update procedure](docs/runbook.md#3-dependency-maintenance-and-dependabot) | Patch exact owning manifests/locks/images/Action pins, refresh inventory and verify complete CI; distinguish repository alerts from deployed remediation. |
| CI failure or PR/source merge | [Development gates](docs/development.md#verification-commands) → affected workflow/test owner → this file's Verify and publish rules | Diagnose the exact run/head; preserve inventories and budgets. Merge only after all required exact-head gates and GitHub requirements. |
| AWS image publication / deployment / rollback | [Runbook releases](docs/runbook.md#6-deployments-and-rollback) → [Runbook configuration](docs/runbook.md#10-configuration) → [Contracts deployment rules](docs/business-rules.md#deployment-migration-and-acceptance) → relevant infrastructure owner | Bind actual account/resources/source/artifacts, compatibility and concrete action plan. Source-merge authority does not authorise AWS/provider mutations. |
| Database migration, backup or restore | [Data lifecycle](docs/data-lifecycle.md) → [Contracts schema/recovery rules](docs/business-rules.md#deployment-migration-and-acceptance) → [Runbook restore](docs/runbook.md#7-data-protection-and-restore) → migration/infrastructure source | Preserve applied migrations, populated evidence and external-effect consistency. Separate local preparation from authorised environment execution. |
| Login, email or lost-authenticator incident | [Contracts identity rules](docs/business-rules.md#authority-and-privacy) → [Runbook account recovery](docs/runbook.md#52-operator-assisted-lost-authenticator-recovery) → auth/email owner | Protect exact identity and original uncertain outcome; real recovery needs separate operator authority, never new app-admin powers. |
| User acceptance / physical device checks | Relevant [Owner](docs/uat/owner.md), [Admin](docs/uat/admin.md) or [Trainer](docs/uat/trainer.md) worksheet → relevant BR for ambiguity | Use designated developer AWS records for live UAT; keep blank masters and completed evidence separate. Record failures, blocked cases and lag; no acceptance from drafting. |
| Architecture or documentation changes | [Architecture decisions](docs/architecture/adr.md) → [diagrams](docs/architecture/diagram.md) → ownership table above | Edit the unique owner, maintain lowercase links, stable BR IDs and full history; validate diagrams and references. Do not duplicate procedures or acceptance ledgers. |

Record **current task / exact stopping point / handover / next action** in Progress, **dated evidence / decisions** in Journey, **business requirements** in Business Rules, **code navigation** in Code Owners, **operating steps** in Runbook, **versions** in the inventory and **tester-facing actions** in the role worksheets. Development owns setup, development workflows and command reference; Runbook owns operational configuration. Link to the owning document instead of copying its instructions.

## Start and verify the checkpoint

Read North Star, Progress, Architecture and relevant current Business Rules and API Contracts before editing. Verify repository identity, local branch/HEAD, index/working tree, remote main, open PRs, CI and required base ancestry. Compare any explicitly requested checkpoint with actual source; stop dependent work on a mismatch and reconcile it without resetting or discarding edits. An old receipt SHA is not a permanent starting pin.

Record relevant runtime/tool versions and check required services are ready. Reuse dependencies, browser engines, images and receipts only when their inputs match; do not reinstall or repeat full setup at every startup. Follow applicable environment/Start instructions, but stale filenames or historical budgets do not override current repository or user instructions. Never execute a prose skill as a shell script.

Use the existing checkout and one active feature branch. Preserve unknown edits, stashes, caches and original evidence; inspect a dirty tree rather than assuming it is disposable. No new worktree or additional agents unless requested. GitHub is canonical after source cutover, but verify how the local checkout differs before proceeding.

## Plan and iterate

For sustained work, apply the [campaign operating guide](NORTH_STAR.md). Keep the active objective, budget and leave-off in Progress; this file continues to own engineering constraints and permissions.

Choose one ready task serving the active campaign outcome in Progress and define completion evidence before implementation: expected behavior, owning code, dependencies, failure/permission cases and applicable acceptance gates. Keep one coherent slice per PR. Fix routine implementation and test failures autonomously; seek decisions for unresolved business requirements, material architecture/security/cost tradeoffs or actions beyond existing authority. Do not repeatedly ask for permission already granted.

Inspect → implement → review affected tests and contracts → run focused checks → diagnose → update owning documents → checkpoint. Retry a failed check only with a new diagnosis, material fix or evidence of a transient cause; preserve the first failure. Reuse findings and inspect changed sections instead of repeatedly restarting broad audits.

Continue authorized work toward all 55 operations during the active session, respecting the user's current priority. PR readiness is a checkpoint; continue independent work while CI runs. Dependent draft PRs may be stacked with exact ancestry and acceptance boundaries recorded. Never count unmerged dependencies as accepted main. Stop only for a concrete blocker, required decision or authority boundary, with completed evidence and the next action recorded. Do not imply unattended background work.

## Implement

Edit canonical component/domain/service/style owners and remove superseded logic. Keep UI, business rules, persistence and infrastructure separate; production authority remains server-side. Prefer the simplest implementation that meets the requirement without duplicate patched owners, speculative abstractions, CSS override tails or unrelated cleanup. Preserve approved presentation, accessibility, responsiveness and unrelated behavior.

Trace field and rule changes through schema/migration, backend model/validation/service, API contract, frontend and affected tests. Recheck identity, current permissions, ownership and business state at the authoritative write boundary. Preserve transaction, concurrency, idempotency and recovery guarantees; a UI guard is not server authorization. Domain-specific invariants and schema-evolution rules belong to Business Rules.

Give substantial JavaScript/Python functions a short purpose or constraint summary; keep detailed rationale beside sensitive logic. Avoid redundant parameter prose, blanket comment rewrites and generated-code churn. Respect existing source/import/lint boundaries and dependency pins; dependency upgrades must be deliberate, scoped and validated. Refresh `docs/versions.md` in the same PR whenever dependency manifests/locks, image references, browser engines or workflow tool pins change; preserve unknown deployed/OS versions as unknown. Never modify applied migrations or expose credentials/customer data.

## Verify and publish

After each logical change, inspect affected services, browser/backend tests, fixtures, inventories and documentation. Use meaningful independent expectations, not tests that merely repeat the implementation. For a defect, reproduce it and add a regression where useful. Run focused checks during iteration, then the applicable complete gates; broaden or repeat only when changes or unresolved concerns justify it. Reuse complete receipts only with an explicit comparison of relevant inputs.

Every integrated Fitfinity server operation needs actual API tests against isolated Docker PostgreSQL. New writes require UI save/reload or fresh-login persistence, unauthorized/foreign records, stale/conflicting requests and interrupted-write recovery. Include foreign records so scope assertions can detect leaks. Simulator coverage remains supplementary. Codex may prepare browsers, run Playwright and inspect internal previews; real Cognito, restart, macOS browser CI and physical-device/live acceptance are distinct evidence.

Never weaken assertions, skip coverage, reduce required inventories, add fixed sleeps/retries/forced interactions, raise timeouts or alter runner settings to manufacture green results. Legitimate test additions update inventory owners together. Diagnose application, fixture, environment and infrastructure failures separately; blocked, cancelled, skipped and partial runs are not passed. Older green heads and focused smoke checks do not establish final acceptance.

Record exact SHA, command, environment, scope and outcome, retaining original failed logs/traces. Preserve exit status through log capture. Use the real commands in [Development](docs/development.md#verification-commands). Documentation-only edits need structure, preservation, links, instructions and affected diagram checks; unchanged full local application suites need not be repeated solely to publish. Full final-head GitHub CI remains required.

Review the final diff for unintended files, secrets, stale claims and changed behavior. Stage exact intended paths and commit/push the task branch. Keep the PR draft while acceptance is blocked. Describe the concrete problem, resulting behavior, validation and remaining limits; do not use abandoned plans as the final description.

Fitfinity source acceptance requires complete `verify / frontend`, `verify / backend` and `verify / api-browser` for the exact final head, including authoritative macOS WebKit and real PostgreSQL, plus GitHub requirements. The user authorizes routine eligible source merges without another confirmation. Merge only the tested head; never bypass protection, directly push main or enable unattended auto-merge. New source changes require the corresponding new-head gates. Main/release validation is separate from successful PR validation.

## Documentation and handoff

Update each document's unique owner and link elsewhere. Refresh `docs/code-owners/index.md` when responsibilities move between modules; keep business rules in Business Rules and infrastructure topology in Architecture. Preserve canonical BR IDs and anchors when moving/editing rules; allocate the next unused ID for new rules, never reuse retired IDs, and keep every current BR mapped to code or an explicitly labelled operational/planned owner in Code Owners. Update affected `docs/uat/` worksheets when user-visible rules or workflows change; keep unexecuted cases distinct from acceptance evidence. Keep one North Star, one current progress ledger and one canonical operation matrix. Business Rules, API Contracts and Journey own current rules, the operation matrix/schema reference and full dated evidence respectively; historical instructions, approvals and counts do not govern current work. Preserve business/security decisions and first failures when consolidating; verify content preservation and references before deleting obsolete files.

Report implemented, tested, CI-verified, merged, deployed and production/provider/device-accepted states separately. Record historical receipts once in Journey; keep Progress focused on the current task: completed work, exact checkout/PR/CI evidence, unresolved issues, the stopping point and ordered resume actions, followed by remaining work. Link to Journey for milestone scope and historical receipts; replace stale handovers rather than accumulating them. Backlog entries need dependencies, acceptance evidence and rollout boundaries; a planned capability is not implemented or authorized for activation. At handoff, record the actual branch/head, dirty/stashed work, PR/CI status, unresolved failures and next action without exposing secrets.

## Execution environment and boundaries

Follow Development for tools and Runbook section10 for configuration. Preserve network proxy/CA settings, TLS checks and dependency hashes. Check credential presence without printing values. Use supported permissions; a denied tool action is not permission to bypass controls. Avoid concurrent heavy suites that distort evidence; preserve runner settings and scope cleanup to resources owned by the invocation.

Synthetic Docker tests must never connect to production PostgreSQL, use real customer records or make real provider actions. Routine coding requires no AWS/production credentials. No reset, force push, destructive cleanup, credential export or applied-migration edits. Connected tools grant no additional authority; no background agents or standing service.

Source-merge authority does not authorize AWS changes, image publication/scans, deployment, IAM changes, security-exception renewal, paid services, real invitations/messages or customer/provider actions. Complete authorized preparation and make the proposed action concrete before any required separate approval. Preserve source/artifact bindings, resource identities, ownership checks, write intents and recovery evidence. Never replay historical first-create/deletion/bootstrap operations or use replacement actions to evade reconciliation. Expired approval is not renewed by documentation, a successful test or an earlier merge.
