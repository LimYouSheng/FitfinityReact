# Fitfinity engineering

## Authority and document ownership

This file owns engineering instructions. User instructions take precedence. Old Journey, Rules & Architecture, CODEX_CLOUD, runbook and history-folder references are superseded; do not recreate those files.

| File | Unique purpose |
| --- | --- |
| [README](README.md) | Development prerequisites, configuration and commands |
| [AGENTS](AGENTS.md) | Engineering workflow, verification and action boundaries |
| [North Star](NORTH_STAR.md) | Current outcome and priority |
| [Progress](PROGRESS.md) | Current revision, evidence, blockers, next actions and hardening backlog |
| [Architecture explanation](docs/Architecture/README.md) | Component responsibilities and interactions |
| [Architecture diagram](docs/Architecture/diagram.md) | Component topology and connections |
| [Service Contracts](docs/SERVICE_CONTRACTS.md) | Part 1: business rules, design decisions, operation matrix and acceptance criteria; Part 2: full dated history |

Read North Star, Progress, Architecture and relevant Service Contracts before work. Verify local branch/HEAD/index, remote main, open PRs and CI; GitHub is canonical but the checkout may differ. Use the existing checkout and one active feature branch; preserve unknown edits and original evidence. No new worktree or agents unless requested. Update each owning document and link to it elsewhere. Historical instructions, approvals and counts do not govern current work.

## Implement

Edit canonical component/domain/service/style owners and remove superseded logic. Preserve approved presentation and unrelated behavior; avoid duplicate implementations and speculative abstractions. Apply Service Contracts at every affected path. Never modify applied migrations or expose credentials/customer data.

Give substantial new JavaScript/Python functions a short purpose or constraint summary; avoid redundant comments and generated-code churn. Inspect → implement → review test impact → run affected checks → diagnose → update owning documents → checkpoint. Continue the authorized North Star during the active session; PR readiness is a checkpoint. Dependent draft PRs may be stacked with exact dependencies recorded. Respect the user's current priority and stop only for a concrete blocker, decision or authority boundary.

## Verify and publish

Every integrated server operation needs actual API tests against isolated PostgreSQL. New writes require UI save/reload or fresh-login persistence, unauthorized/foreign records, stale conflicts and interrupted-write recovery. Simulator coverage is supplementary. Record command, source, environment and result; retain first failures. Real Cognito, service restart, devices and deployed acceptance remain distinct.

After a logical change, inspect affected services, tests, fixtures and inventories. Run meaningful focused checks using [README](README.md#verification-commands); reuse complete receipts only when relevant inputs match. Never weaken assertions, skip coverage, lower counts, add retries, force interactions or raise timeouts to manufacture green results. Codex may run Playwright and inspect internal previews; macOS CI and physical acceptance remain separate. Documentation-only edits need structure, preservation, link and diagram checks, not repeated full local application runs.

Review the diff and stage exact intended paths. Commit/push the task branch and prepare a draft PR. Source acceptance requires complete `verify / frontend`, `verify / backend` and `verify / api-browser` for the exact final head plus GitHub requirements. The user authorizes routine eligible source merges without another confirmation; merge only the tested head, never bypass protection or enable unattended auto-merge. Record merge evidence in Contracts history and current status in Progress, then continue authorized work.

## Execution environment and boundaries

Follow README for tools and commands. Reuse valid dependencies/caches; do not rerun installers at every startup. Preserve network proxy/CA settings and TLS checks. Check credential presence without printing values. Synthetic Docker tests must never connect to production PostgreSQL or real provider/customer accounts. Preserve exit status when capturing logs and clean up only resources owned by the invocation.

No direct main push, reset, force push, destructive cleanup or credential export. Source merge does not authorize AWS changes, image publication/scans, deployment, IAM changes, exception renewal, real invitations/messages or customer/provider actions. Prepare concrete release work before seeking any required separate approval. Historical first-create, deletion and recovery operations must not be replayed. Connected tools grant no additional authority; no background agents or standing service.
