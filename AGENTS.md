# Fitfinity engineering

## Authority and document ownership

This file owns engineering instructions. User instructions take precedence. Old Journey, Rules & Architecture, CODEX_CLOUD, runbook and history-folder references are superseded; do not recreate those files.

| File | Unique purpose |
| --- | --- |
| [README](README.md) | Development prerequisites, configuration and commands |
| [UAT walkthrough](docs/UAT.md) | Manual user acceptance cases, expected results and run-record format; not an executed test receipt |
| [Code owners](docs/Code-Owners.md) | Hierarchical feature/module navigation and responsibility diagrams |
| [Versions](Versions.md) | Repository dependency/version inventory and manual patch lookup; not deployed acceptance |
| [AGENTS](AGENTS.md) | Engineering workflow, verification and action boundaries |
| [North Star](NORTH_STAR.md) | Current outcome and priority |
| [Progress](PROGRESS.md) | Full milestone roadmap, current evidence, blockers, next actions and hardening backlog |
| [Architecture explanation](docs/Architecture/README.md) | Component responsibilities and interactions |
| [Architecture diagram](docs/Architecture/diagram.md) | Component topology and connections |
| [Service Contracts](docs/SERVICE_CONTRACTS.md) | Part 1: business rules, design decisions, operation matrix and cross-cutting acceptance criteria; Part 2: full dated history |


Use this structure as a guide for other projects, but re-establish their runtime, test commands, data boundaries, browser permissions and merge/deployment authority. Fitfinity's permissions and technology choices do not transfer automatically. Keep reusable engineering practice here and project business rules in Service Contracts; do not create parallel rulebooks.

## Start and verify the checkpoint

Read North Star, Progress, Architecture and relevant current Service Contracts before editing. Verify repository identity, local branch/HEAD, index/working tree, remote main, open PRs, CI and required base ancestry. Compare any explicitly requested checkpoint with actual source; stop dependent work on a mismatch and reconcile it without resetting or discarding edits. An old receipt SHA is not a permanent starting pin.

Record relevant runtime/tool versions and check required services are ready. Reuse dependencies, browser engines, images and receipts only when their inputs match; do not reinstall or repeat full setup at every startup. Follow applicable environment/Start instructions, but stale filenames or historical budgets do not override current repository or user instructions. Never execute a prose skill as a shell script.

Use the existing checkout and one active feature branch. Preserve unknown edits, stashes, caches and original evidence; inspect a dirty tree rather than assuming it is disposable. No new worktree or additional agents unless requested. GitHub is canonical after source cutover, but verify how the local checkout differs before proceeding.

## Plan and iterate

Choose one ready task serving the North Star and define completion evidence before implementation: expected behavior, owning code, dependencies, failure/permission cases and applicable acceptance gates. Keep one coherent slice per PR. Fix routine implementation and test failures autonomously; seek decisions for unresolved business requirements, material architecture/security/cost tradeoffs or actions beyond existing authority. Do not repeatedly ask for permission already granted.

Inspect → implement → review affected tests and contracts → run focused checks → diagnose → update owning documents → checkpoint. Retry a failed check only with a new diagnosis, material fix or evidence of a transient cause; preserve the first failure. Reuse findings and inspect changed sections instead of repeatedly restarting broad audits.

Continue authorized work toward all 55 operations during the active session, respecting the user's current priority. PR readiness is a checkpoint; continue independent work while CI runs. Dependent draft PRs may be stacked with exact ancestry and acceptance boundaries recorded. Never count unmerged dependencies as accepted main. Stop only for a concrete blocker, required decision or authority boundary, with completed evidence and the next action recorded. Do not imply unattended background work.

## Implement

Edit canonical component/domain/service/style owners and remove superseded logic. Keep UI, business rules, persistence and infrastructure separate; production authority remains server-side. Prefer the simplest implementation that meets the requirement without duplicate patched owners, speculative abstractions, CSS override tails or unrelated cleanup. Preserve approved presentation, accessibility, responsiveness and unrelated behavior.

Trace field and rule changes through schema/migration, backend model/validation/service, API contract, frontend and affected tests. Recheck identity, current permissions, ownership and business state at the authoritative write boundary. Preserve transaction, concurrency, idempotency and recovery guarantees; a UI guard is not server authorization. Domain-specific invariants and schema-evolution rules belong to Service Contracts.

Give substantial JavaScript/Python functions a short purpose or constraint summary; keep detailed rationale beside sensitive logic. Avoid redundant parameter prose, blanket comment rewrites and generated-code churn. Respect existing source/import/lint boundaries and dependency pins; dependency upgrades must be deliberate, scoped and validated. Refresh root `Versions.md` in the same PR whenever dependency manifests/locks, image references, browser engines or workflow tool pins change; preserve unknown deployed/OS versions as unknown. Never modify applied migrations or expose credentials/customer data.

## Verify and publish

After each logical change, inspect affected services, browser/backend tests, fixtures, inventories and documentation. Use meaningful independent expectations, not tests that merely repeat the implementation. For a defect, reproduce it and add a regression where useful. Run focused checks during iteration, then the applicable complete gates; broaden or repeat only when changes or unresolved concerns justify it. Reuse complete receipts only with an explicit comparison of relevant inputs.

Every integrated Fitfinity server operation needs actual API tests against isolated Docker PostgreSQL. New writes require UI save/reload or fresh-login persistence, unauthorized/foreign records, stale/conflicting requests and interrupted-write recovery. Include foreign records so scope assertions can detect leaks. Simulator coverage remains supplementary. Codex may prepare browsers, run Playwright and inspect internal previews; real Cognito, restart, macOS browser CI and physical-device/live acceptance are distinct evidence.

Never weaken assertions, skip coverage, reduce required inventories, add fixed sleeps/retries/forced interactions, raise timeouts or alter runner settings to manufacture green results. Legitimate test additions update inventory owners together. Diagnose application, fixture, environment and infrastructure failures separately; blocked, cancelled, skipped and partial runs are not passed. Older green heads and focused smoke checks do not establish final acceptance.

Record exact SHA, command, environment, scope and outcome, retaining original failed logs/traces. Preserve exit status through log capture. Use the real commands in [README](README.md#verification-commands). Documentation-only edits need structure, preservation, links, instructions and affected diagram checks; unchanged full local application suites need not be repeated solely to publish. Full final-head GitHub CI remains required.

Review the final diff for unintended files, secrets, stale claims and changed behavior. Stage exact intended paths and commit/push the task branch. Keep the PR draft while acceptance is blocked. Describe the concrete problem, resulting behavior, validation and remaining limits; do not use abandoned plans as the final description.

Fitfinity source acceptance requires complete `verify / frontend`, `verify / backend` and `verify / api-browser` for the exact final head, including authoritative macOS WebKit and real PostgreSQL, plus GitHub requirements. The user authorizes routine eligible source merges without another confirmation. Merge only the tested head; never bypass protection, directly push main or enable unattended auto-merge. New source changes require the corresponding new-head gates. Main/release validation is separate from successful PR validation.

## Documentation and handoff

Update each document's unique owner and link elsewhere. Refresh `docs/Code-Owners.md` when responsibilities move between modules; keep business rules in Service Contracts and infrastructure topology in Architecture. Preserve canonical BR IDs and anchors when moving/editing rules; allocate the next unused ID for new rules, never reuse retired IDs, and keep every current BR mapped to code or an explicitly labelled operational/planned owner in Code Owners. Update affected `docs/UAT.md` cases when user-visible rules or workflows change; keep unexecuted cases distinct from acceptance evidence. Keep one North Star, one current progress ledger and one canonical operation matrix. Current rules precede full dated evidence in Service Contracts; historical instructions, approvals and counts do not govern current work. Preserve business/security decisions and first failures when consolidating; verify content preservation and references before deleting obsolete files.

Report implemented, tested, CI-verified, merged, deployed and production/provider/device-accepted states separately. Record historical receipts once in Contracts Part 2; keep Progress limited to the current checkpoint, blockers and remaining work. Backlog entries need dependencies, acceptance evidence and rollout boundaries; a planned capability is not implemented or authorized for activation. At handoff, record the actual branch/head, dirty/stashed work, PR/CI status, unresolved failures and next action without exposing secrets.

## Execution environment and boundaries

Follow README for tools and configuration. Preserve network proxy/CA settings, TLS checks and dependency hashes. Check credential presence without printing values. Use supported permissions; a denied tool action is not permission to bypass controls. Avoid concurrent heavy suites that distort evidence; preserve runner settings and scope cleanup to resources owned by the invocation.

Synthetic Docker tests must never connect to production PostgreSQL, use real customer records or make real provider actions. Routine coding requires no AWS/production credentials. No reset, force push, destructive cleanup, credential export or applied-migration edits. Connected tools grant no additional authority; no background agents or standing service.

Source-merge authority does not authorize AWS changes, image publication/scans, deployment, IAM changes, security-exception renewal, paid services, real invitations/messages or customer/provider actions. Complete authorized preparation and make the proposed action concrete before any required separate approval. Preserve source/artifact bindings, resource identities, ownership checks, write intents and recovery evidence. Never replay historical first-create/deletion/bootstrap operations or use replacement actions to evade reconciliation. Expired approval is not renewed by documentation, a successful test or an earlier merge.
