# Continuous development guide

> **Guidance only, not a strict requirement.** These workflows are practical examples. [AGENTS](../AGENTS.md) owns engineering rules and action boundaries; this guide does not expand merge, deployment or provider authority.

Commands assume the repository root. GitHub is canonical; a checkout or attached ZIP is a revision snapshot. Establish its branch and revision before combining work.

## Choose a development workflow

| Way | Best suited to | Where work happens | How changes return |
| --- | --- | --- | --- |
| [1. Local VS Code](#1-local-development-with-vs-code) | Interactive editing, debugging and local browser checks | Your computer and task branch | Reviewed commit, push and draft PR |
| [2. Codex Cloud](#2-development-with-codex-cloud) | Repository investigation, implementation and isolated verification | Connected repository and managed workspace | Task branch and draft PR |
| [3. ZIP attached to chat](#3-development-through-a-zip-attached-to-chat) | Review when repository access is unavailable | Identified source snapshot | Reviewed patch integrated into a task branch, then normal CI |

All three routes converge on the same source review and verification process. A chat response or ZIP is not a deployment pipeline.

## What to read before changing code

Start with [AGENTS](../AGENTS.md), [North Star](../NORTH_STAR.md) and [Progress](../PROGRESS.md), then follow AGENTS' task directory.

- [Business rules](business-rules.md): current requirements; [API contracts](api-contracts.md): the55-operation matrix and detailed schemas; [Journey](journey.md): complete dated evidence.
- [Architecture](architecture/adr.md) and [diagrams](architecture/diagram.md): component responsibilities and test coverage.
- [Code owners](code-owners/index.md): feature and BR-to-module navigation.
- [Versions](versions.md): configured and locked dependencies, not deployed versions.
- [Runbook](runbook.md): operations, dependencies, release, configuration and recovery.
- [Owner](uat/owner.md), [Admin](uat/admin.md) and [Trainer](uat/trainer.md): developer AWS acceptance worksheets, separate from local synthetic testing.

## 1. Local development with VS Code

### Clone or refresh safely

Use approved GitHub authentication; never embed tokens in remote URLs. For a first checkout:

```bash
git clone https://github.com/LimYouSheng/FitfinityReact.git
cd FitfinityReact
git status --short
git remote -v
code .
```

Open the repository root with VS Code's Open Folder if `code` is unavailable. Inspect format-on-save changes and use the repository's existing lint/style conventions.

For an existing clean checkout, inspect branch, HEAD, remote and open PRs first. An example task branch flow is:

```bash
git fetch origin
git switch main
git pull --ff-only origin main
git switch -c fix/short-task-name
```

Use `feat/…` or `docs/…` as appropriate. Preserve unfamiliar edits, stashes, caches and failure evidence; do not reset or automatically stash them. Inspect divergence instead of rewriting history. Fitfinity uses the existing checkout and one active branch; additional worktrees or agents require a user request.

### Install and run

Use the current [setup reference](#development-setup) and [version inventory](versions.md), rather than old chat versions. Check the selected Node, npm, Python and Docker versions before setup:

```bash
node --version
npm --version
python3 --version
docker compose version
npm ci
npm run dev
```

`npm ci` installs reviewed locked dependencies; do not broadly update dependencies just to start. Reuse matching installations and browser caches. Python runs the FastAPI backend and verification/infrastructure tooling. Docker is required for isolated real-database verification.

Use the URL printed by Vite. Default local composition is demo; an API build must explicitly select its API origin and mode. A demo or static preview does not prove backend persistence. The Pages demo uses `/FitfinityReact/`; root and Pages builds have separate checks. See [configuration](runbook.md#10-configuration) for API/test composition and feature switches.

Use VS Code and browser breakpoints to reproduce a problem. Record steps, expected/actual behavior, perceived delays and redacted evidence. Routine development and isolated tests require no production database or AWS credentials.

### Iterate and verify

Edit the existing owning module and meaningful affected tests. Run focused checks from the [command reference](#verification-commands), then applicable full gates. Trace permission, persistence, stale/conflicting requests and interrupted writes through the authoritative backend boundary. For new writes, exercise UI save and reload or fresh-login persistence against isolated Docker PostgreSQL, with foreign-record and unauthorized cases.

Install matching Playwright browsers/system dependencies when needed; do not upgrade the package just to obtain an executable. Fitfinity permits Codex browser preparation and Playwright execution. Simulator tests establish frontend contracts; real API tests exercise FastAPI, migrations, PostgreSQL and protected storage with a synthetic Cognito provider. Real Cognito, physical devices and deployed AWS acceptance remain separate.

## 2. Development with Codex Cloud

Connect the intended repository/account and verify workspace readiness, branch, HEAD, working tree, remote main, open PRs and CI. A reused workspace may contain unfinished work. Follow its runtime instructions and network/CA policy; check credential presence without printing values.

A useful task prompt supplies:

```text
Repository and branch/revision:
Goal or reproducible bug:
Expected behavior and relevant BR IDs:
Observed behavior and redacted evidence:
Scope and work to preserve:
Deliverable: reviewed change and draft PR
Test boundary: isolated Docker PostgreSQL; no production/provider actions
```

Ask the agent to inspect the owning code, implement a coherent change, verify it, update the owning documents and publish a draft PR. Existing source-merge authority applies only after exact-head gates and GitHub requirements. AWS image publication, deployment and real provider actions require separate authority.

Use managed credentials and scoped connections. Do not paste secrets/customer data into chat, source, screenshots or archives. An access error does not justify replacing injected credentials, bypassing network policy or disabling TLS. If Docker or trust is unavailable, record the blocker; SQLite and simulator tests do not substitute for required PostgreSQL evidence.

Inspect the exact pushed head and its CI. Preserve the first failure, diagnose its cause and keep assertions, inventories and budgets intact. At a pause, record branch/HEAD, PR/run links, performed checks, blockers and the next action. Do not imply unattended monitoring after the turn ends.

## 3. Development through a ZIP attached to chat

### Prepare an identifiable source snapshot

Prefer a clean committed revision. Inspect tracked paths for secrets and customer data before packaging; Git archive is not a privacy scrubber and includes tracked dotfiles.

```bash
git status --short
git rev-parse HEAD
git ls-files
git archive --format=zip --output=../fitfinity-source.zip HEAD
```

Record the full source SHA and archive checksum: `shasum -a 256 ../fitfinity-source.zip` on macOS or `sha256sum ../fitfinity-source.zip` on Linux. Name the archive by task/revision where practical. `git archive HEAD` excludes uncommitted changes; supply a reviewed patch with its baseline if those changes matter.

Include required source, manifests/locks, workflows, AGENTS, docs and tests. Exclude credentials, `.env` files, customer/provider exports, `.git`, dependencies, build output, caches and unrelated logs. Tracked sensitive files require removal from the delivery and exposure remediation; `.gitignore` does not remove tracked files.

Attach the archive with repository, branch, full SHA, checksum, task and expected outcome. State whether repository/tool access is available. Archive-only work cannot establish remote GitHub status or claim a push.

### Review the returned changes

Request a changed-file summary, patch or complete changed files, test evidence, limitations and baseline. Inspect archive paths before extraction; reject traversal, unsafe symlinks and case collisions. Extract into an isolated directory, never blindly over the active checkout.

Integrate into a branch matching the supplied baseline. Review deletions/configuration carefully and use `git apply --check` before applying a returned patch. Reconcile intervening changes explicitly; do not force mismatched patches. Restore local secrets through secure setup.

Run affected checks on the integrated bytes and use the normal PR process. Snapshot test reports do not replace final-head CI. Fitfinity has no documented guarded installer delivery workflow; do not copy SoccerBot installer commands or run an unreviewed bundled script.

## GitHub publishing and what CI does

### Review, commit and push

Inspect the diff and stage only intended files, replacing these example paths and branch:

```bash
git status --short
git diff
git diff --check
git add path/to/changed-file path/to/related-test
git diff --cached
git commit -m "Describe the concrete change"
git push -u origin fix/short-task-name
```

Open/update a draft PR against main. Keep the title/body aligned with the final scope and report meaningful validation and remaining acceptance. Do not force-push or push directly to main. Fetch and inspect upstream changes; if needed, merge main into the branch, resolve conflicts in owning files and verify the resulting head.

Dependent draft PRs may target an unmerged task branch with exact ancestry recorded. The current PR workflow filters for base `main`, so a stacked PR may have no automatic checks until retargeted. After its dependency merges, reconcile with main, retarget and require complete checks for the final head; dependency CI is not child acceptance.

### Expected Actions behavior

| Action | Expected behavior | What it does not establish |
| --- | --- | --- |
| PR opened/updated against main | Reusable verification runs frontend, backend and API-browser gates | Merge, AWS publication or deployment |
| Frontend gate | Locked npm audit, lint/verifier regressions, units, builds, PWA/simulator browsers and source health | Real database or provider acceptance |
| Backend gate | Container, isolated PostgreSQL/storage and offline infrastructure verification | AWS infrastructure execution |
| API-browser gate | Two isolated real-API shards plus aggregate checking every discovered case passed exactly once | Real Cognito, physical-device or live AWS acceptance |
| Authorized source merge | Fresh main verification; Pages demo publishing follows successful verification/build | Lambda updated or production accepted |
| Manual AWS image workflow | Exact main revision, fresh verification and existing release/approval gates | Automatic runtime deployment; dispatch still needs authority |
| Dependabot generation | Grouped version proposals; security proposals may arrive separately | A patch merged or deployed |

[Workflows](../.github/workflows) own executable behavior; the [runbook](runbook.md#6-deployments-and-rollback) owns release procedures. Preserve original failing logs/traces and distinguish failed, cancelled, queued and approval-blocked jobs. A green update-generation job is not application CI. Keep a PR draft until ready; all three required gates and GitHub requirements must pass for the exact final head before the authorized source merge. Verify main separately; deployment/provider acceptance remains separate again.

## Current engineering expectations

[AGENTS](../AGENTS.md) remains the rules authority. Use existing owners, preserve business invariants and unknown work, keep verification strict and report implemented/tested/merged/deployed/accepted states accurately. Update the unique owning document rather than copying its rules here. Preserve stable BR IDs and their code-owner mappings, the full Journey and milestone roadmap.

Dependency updates follow the [runbook](runbook.md#3-dependency-maintenance-and-dependabot). Refresh the manually maintained [version inventory](versions.md) when its inputs change; Fitfinity does not currently have SoccerBot's versions generator/freshness gate. Do not use `npm audit fix --force` as routine setup.

## Development setup

Use Node 24, Python 3.12, Git and Docker Compose. Install frontend dependencies with `npm ci` from the reviewed lockfile; reuse matching dependencies, prepared images and Playwright caches during routine work. Backend versions and hashes are owned by `backend/pyproject.toml`, its requirements files and `backend/Dockerfile`.

`npm run dev` starts Vite; `npm run build` creates `dist/`; `npm run preview` serves it locally. `npm run build:pages-test` creates the `/FitfinityReact/` demo export. Local ports are not public preview URLs.

## Verification commands

| Command | Scope |
| --- | --- |
| `npm run verify:lint` / `verify:health` | Semantic lint and source ownership/health |
| `npm run verify:quality-checker` / `verify:health-checker` | Verifier regressions |
| `npm test -- --reporter=verbose` | Frontend units; append a real test path for focused work |
| `npm run verify:assessments` | Assessment form parity |
| `npm run verify:backend` | Full backend against isolated Docker PostgreSQL and S3-compatible storage, including offline infrastructure checks |
| `npm run verify:infrastructure` | Offline infrastructure checks alone |
| `CI=true npm run test:e2e -- --reporter=list` | Root/Pages/API-fixture builds, PWA and simulator browser suite |
| `npm run test:api-browser` | Real frontend/FastAPI/migrations/PostgreSQL and protected-media browser suite |

The [full-suite diagram](architecture/diagram.md#full-verification-suite) explains existing test scopes and planned mutation, performance, security, telemetry and operational verification. Planned suites have no executable command here until implemented.

CI runs the real-API suite in two complementary shards, each with its own disposable databases/storage and the existing 20-minute budget. The required `verify / api-browser` aggregate checks both successful jobs and every discovered case identity, rejecting missing, duplicated, skipped, retried or failed cases. Local `npm run test:api-browser` still runs the complete suite; `-- --shard=1/2 --reporter=list,json` selects a shard for diagnosis, with `PLAYWRIGHT_JSON_OUTPUT_FILE` selecting its report path. A shard alone is not complete acceptance. Overall job budgets are 60 minutes each for frontend/backend, 20 minutes per API-browser shard and 5 minutes for the aggregate; these are separate from test and database timeouts.

Required CI and evidence rules belong to [AGENTS](../AGENTS.md#verify-and-publish). Test inventories are defined by the verifiers, not historical counts in documentation.

