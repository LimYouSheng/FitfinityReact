# Continuous development guide

> **Guidance only, not a strict requirement.** These workflows are practical examples. [AGENTS](../AGENTS.md) owns engineering rules and action boundaries; this guide does not expand merge, deployment or provider authority.

**Where development left off:** read the [current task, evidence and ordered resume steps](../PROGRESS.md#resume-in-this-order) before starting. Progress is the single current checkpoint; [Journey](journey.md#complete-journey) retains decisions and completed receipts.

Commands assume the repository root. GitHub is canonical; a checkout or attached ZIP is a revision snapshot. Establish its branch and revision before combining work.

## Choose a development workflow

| Way | Best suited to | Where work happens | How changes return |
| --- | --- | --- | --- |
| [1. Local VS Code](#1-local-development-with-vs-code) | Interactive editing, debugging and local browser checks | Your computer and task branch | Reviewed commit, push and draft PR |
| [2. Cloud Containers](#2-development-with-cloud-containers) | Repository investigation, implementation and isolated verification | Connected repository and managed workspace | Task branch and draft PR |
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

### Real API tests with disposable PostgreSQL

The commands below use a POSIX shell (macOS/Linux, or Windows with WSL2 plus Docker Desktop integration). Node24.15+ within major24 and a running Docker daemon/Compose are required. The database and Python runtime run in containers; a separate local Python install is not required for these two npm wrappers. Use the repository root, close any existing local API-test stack on ports4180/4181, and keep production credentials out of this session.

```bash
npm ci
docker info
npx playwright install --with-deps chromium webkit
npm run verify:backend
npm run test:api-browser
```

`verify:backend` creates its own Compose project with isolated PostgreSQL and S3-compatible storage, applies migrations and runs backend/infrastructure checks. `test:api-browser` first builds the API frontend, starts a separate isolated database/storage/API project, seeds synthetic identities and runs the browser suite. Each wrapper removes its own containers and volumes on completion, including normal test failure; these are not servers to leave running for manual use. After abrupt process termination, inspect `docker compose ls` and remove only the specific abandoned test project, never another developer's project. A focused command such as `npm run test:api-browser -- tests-api/staff.spec.js --workers=1` is useful for diagnosis but is not full-suite acceptance.

The suites use real FastAPI, migrations, PostgreSQL, JWT verification, cookies, CSRF and storage IO. Cognito/invitation delivery is substituted locally. They never use RDS, production PostgreSQL or paid AWS services. Browser downloads/container registries still require network access; preserve proxy/CA trust in Cloud Containers rather than disabling TLS. On Windows, run these wrappers inside WSL2 because they use POSIX process/user IDs.

### Manual browser session with the isolated API

Use a dedicated project name and the existing browser harness; it serves the built frontend and real API together. This test database is disposable, not a durable development database. Ports4180 and4181 must be free; do not run the automated API suite simultaneously.

```bash
npm run build:api-test
export FITFINITY_BROWSER_UID="$(id -u)"
export FITFINITY_BROWSER_GID="$(id -g)"
docker compose -p fitfinity-manual-api -f backend/compose.yaml -f backend/compose.browser.yaml --profile test --profile browser up -d --build --wait browser-api
curl --fail http://127.0.0.1:4180/health/ready
curl --fail -H 'X-Fitfinity-Browser-Worker: 0' http://127.0.0.1:4180/auth/policy
```

The user/group exports let the container read your mounted checkout without changing file permissions. The harness deliberately requires a bounded worker header, including for frontend files. A normal browser opened directly at the address receives400; it does not mean the database failed. On a computer with a graphical desktop and installed Playwright Chromium, open this dedicated browser context so every request carries the same isolated worker identity:

```bash
node --input-type=module <<'JS'
import { chromium } from '@playwright/test'
const browser = await chromium.launch({ headless: false })
const context = await browser.newContext({
  extraHTTPHeaders: { 'X-Fitfinity-Browser-Worker': '0' },
})
const page = await context.newPage()
await page.goto('http://127.0.0.1:4180')
await new Promise(resolve => browser.on('disconnected', resolve))
JS
```

Synthetic sign-in: `owner@example.test`, `admin@example.test` or `trainer@example.test`; password `browser-test-password-only`; authenticator code `123456`. These are local fixture identities, not usable Cognito/customer credentials. Use Owner for Admin management. Writes survive browser reload while that API process/database is running. The fixture creates fresh migrated/seeded databases at startup; an API restart or teardown is not a way to retain manual-test data. Invitations/recovery use local substitutes, so this does not accept email delivery, real Cognito or physical devices.

This is a built frontend, not Vite hot reload: rebuild with `npm run build:api-test` after UI changes and open a fresh context to avoid a retained service-worker build. Restart the owned API service after backend changes, understanding that its synthetic data will be recreated. Inspect errors with `docker compose -p fitfinity-manual-api -f backend/compose.yaml -f backend/compose.browser.yaml --profile test --profile browser logs browser-api`. Close the browser and remove only this test stack when finished:

```bash
docker compose -p fitfinity-manual-api -f backend/compose.yaml -f backend/compose.browser.yaml --profile test --profile browser down --volumes --remove-orphans
```

Cloud Containers may reuse an inspected, dependency-matching test image through `FITFINITY_BROWSER_BACKEND_IMAGE` and an inspected browser image through `FITFINITY_BROWSER_RUNNER_IMAGE`; those are environment-specific accelerators, not prerequisites or production images. The published commands above use the checked-in Docker build. Do not copy another environment's image name without verifying its inputs.

### Persistent local backend — a different workflow

For database/backend development with records retained across restarts, the base Compose file owns a named local PostgreSQL volume and a one-shot migration service:

```bash
docker compose -p fitfinity-local -f backend/compose.yaml up -d --build --wait api
curl --fail http://127.0.0.1:8080/health/live
curl --fail http://127.0.0.1:8080/health/ready
docker compose -p fitfinity-local -f backend/compose.yaml logs api migrate
docker compose -p fitfinity-local -f backend/compose.yaml down
```

The dependency chain starts `db`, completes `alembic upgrade head`, then starts `api`. Plain `down` retains this project's `dev-postgres` volume; adding `--volumes` deliberately deletes those local records. No database port is exposed on the host. Authentication is disabled by default and this stack has no synthetic staff seed or local identity substitute: successful health checks do **not** enable interactive staff workflows. Use the isolated browser workflow above for those. Real Cognito configuration requires its separately reviewed configuration/authority; do not point local tests at production. The base `api`/`migrate` services build the runtime stage, which downloads the Lambda adapter; the isolated test stage intentionally does not.

### Iterate and verify

Edit the existing owning module and meaningful affected tests. Run focused checks from the [command reference](#verification-commands), then applicable full gates. Trace permission, persistence, stale/conflicting requests and interrupted writes through the authoritative backend boundary. For new writes, exercise UI save and reload or fresh-login persistence against isolated Docker PostgreSQL, with foreign-record and unauthorized cases.

Install matching Playwright browsers/system dependencies when needed; do not upgrade the package just to obtain an executable. Fitfinity permits Codex browser preparation and Playwright execution. Simulator tests establish frontend contracts; real API tests exercise FastAPI, migrations, PostgreSQL and protected storage with a synthetic Cognito provider. Real Cognito, physical devices and deployed AWS acceptance remain separate.

## 2. Development with Cloud Containers

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

Run affected checks on the integrated bytes and use the normal PR process. Snapshot test reports do not replace final-head CI. Fitfinity has no documented guarded installer delivery workflow; do not run an unreviewed bundled installer script.

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

[Workflows](../.github/workflows) own executable behavior; the [runbook](runbook.md#6-deployments-and-rollback) owns release procedures. API-browser evidence includes browser-process diagnostics (`pw:browser`) and PDF readiness timing annotations. Intercepted real requests use `tests-api/fixtures.js`’s `fetchRoute` to close pooled test connections; browser-originated traffic is unchanged. Preserve original failing logs/traces and distinguish failed, cancelled, queued and approval-blocked jobs. A green update-generation job is not application CI. Keep a PR draft until ready; all three required gates and GitHub requirements must pass for the exact final head before the authorized source merge. Verify main separately; deployment/provider acceptance remains separate again.

## Current engineering expectations

[AGENTS](../AGENTS.md) remains the rules authority. Use existing owners, preserve business invariants and unknown work, keep verification strict and report implemented/tested/merged/deployed/accepted states accurately. Update the unique owning document rather than copying its rules here. Preserve stable BR IDs and their code-owner mappings, the full Journey and milestone roadmap.

Dependency updates follow the [runbook](runbook.md#3-dependency-maintenance-and-dependabot). Run `npm run versions:refresh` after a locked install when inventory inputs change, review the [generated inventory](versions.md), then run `npm run verify:dependencies`. The blocking freshness/consistency gate is implemented in PR120; handwritten explanations and deployed state still require review. Do not use `npm audit fix --force` as routine setup.

## Development setup

Use Node24.15.0 or newer within major24, Python3.12, Git and Docker Compose. `.nvmrc` owns the selected Node major for local `nvm use` and every setup-node workflow; `package.json` engines owns the supported patch floor. `npm run verify:dependencies` checks the actual runtime against every locked npm engine requirement. Install frontend dependencies with `npm ci` from the reviewed lockfile; reuse matching dependencies, prepared images and Playwright caches during routine work. Backend versions and hashes are owned by `backend/pyproject.toml`, its requirements files and `backend/Dockerfile`.

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

CI runs the real-API suite in two complementary shards, each with its own disposable databases/storage and the existing 20-minute budget. The required `verify / api-browser` aggregate checks both successful jobs and every discovered case identity, rejecting missing, duplicated, skipped, retried or failed cases. Local `npm run test:api-browser` still runs the complete suite; `-- --shard=1/2 --reporter=list,json` selects a shard for diagnosis, with `PLAYWRIGHT_JSON_OUTPUT_FILE` selecting its report path. A shard alone is not complete acceptance. Job limits are60 minutes for each macOS browser profile and backend execution/check group,20 for quality/unit/browser-build and each API shard, and5 for the three aggregate gates. These limits are distinct from test and database timeouts.

Independent CI work starts concurrently: quality/audit, frontend units, browser builds, backend source checks, offline infrastructure, three backend domain groups and the existing two API shards. Only browser profiles wait for their shared root/Pages/API-fixture build; aggregate gates wait for complete evidence. Desktop Chromium, phone WebKit and tablet WebKit each run385 cases on macos-15 with one browser worker. Unit/build jobs also retain macOS; quality and backend jobs use Ubuntu. This separates job concurrency from per-job worker concurrency without changing the device matrix.

Backend ownership is explicit in [test-groups.json](../backend/scripts/test-groups.json): identity/clients628, scheduling/packages449 and records/platform345 cases at this checkpoint. Each group discovers the complete1422-case inventory before selecting whole files, owns separate Docker PostgreSQL/storage and retains setup/call/teardown outcomes. New/unassigned or duplicate files fail. Backend source checks also collect all cases in two fresh processes and require identical stable IDs; random scenario data must not make case identities vary between shards. The [group verifier](../scripts/verify-ci-groups.mjs) checks complete identity coverage and successful dependencies under the unchanged frontend/backend gate names; missing, duplicated, failed, skipped or wrong-source backend receipts are rejected. Local full-suite commands remain available. `FITFINITY_TEST_GROUP=<group> FITFINITY_BACKEND_RECEIPT=/absolute/path/report.json node scripts/verify-backend.mjs` selects a diagnostic group; it is not complete acceptance.

Browser jobs consume one build artifact bound to the current source SHA and run attempt. Browser and backend jobs retain disk/process or Docker resource snapshots around execution. This is diagnostic evidence, not a latency or memory-peak benchmark. Automatic one/two-case runtime recycling is not enabled: restart frequency must follow measured PostgreSQL/browser lifecycle needs, and restarting hundreds of processes adds overhead. Revisit measured growth/leaks before selecting a batch size; preserve complete transaction/race/restart scenarios and cleanup.

Required CI and evidence rules belong to [AGENTS](../AGENTS.md#verify-and-publish). Test inventories are defined by the verifiers, not historical counts in documentation.

Browser media compatibility is a feature-specific acceptance question under the [coverage matrix](#browser-testing-coverage), not a blanket browser support guarantee. Conversion depends on recording APIs and input codecs, with explicit original-file fallback. Actual Samsung/iPad capture and audio playback still require physical UAT. Browser preparation uses no microphone permission; it processes audio already present in the selected clip.

Dependency updates: run `npm ci`, then `npm run versions:refresh` and review `docs/versions.md`; `npm run verify:dependencies` is the read-only CI/local gate. It validates Python manifest/runtime/test pins, Node/Action/Compose consistency, React pairing, browser metadata and the security override before checking generated inventory. Refresh is not permission to accept a version change or rewrite a security/resource guard. The generator requires the lock-matching installed Playwright package.

For failed/queued CI, follow the [CI diagnosis skill](../.agents/skills/fitfinity-ci-diagnosis/SKILL.md) for exact-run evidence and bounded experiments; this document remains the setup/command owner.

## Browser testing coverage

This section owns configured browser coverage and its limits; [Versions](versions.md#browser-engines) owns the generated package/engine inventory. Every dependency PR needs the [before/after support comparison](../.agents/skills/fitfinity-dependencies/SKILL.md#required-support-range-comparison-in-every-dependency-pr). **Upstream-supported ranges, repository configuration and verified coverage are three different claims.** No customer minimum-browser policy or continuous supported range is established by this matrix.

Configuration reviewed:3 November2026. Accepted maincc243fb and PR120 both pin Playwright1.64.1. The following engine versions/revisions are from the exact installed playwright-core1.64.1 browsers.json, checked against the lock; they are bundled configuration, not independently captured browser.version() output. Hosted runner images and platform-specific engine overrides require their own run evidence.

| Configured engine | Bundled version / revision | Platform qualification |
| --- | --- | --- |
| Chromium and Chromium headless shell |156.0.8078.4 /1248 | Selected by desktop-chromium; not branded Chrome/Edge certification |
| WebKit |27.2 /2370 | Selected by phone/tablet; package records mac14 and mac14-arm64 revision2251 overrides, which are not evidence those hosts were tested |
| Firefox |157.0 /1555 | Available in the package but not selected by either suite; no Firefox acceptance |

[playwright.config.js](../playwright.config.js) defines these projects; [playwright.api.config.js](../playwright.api.config.js) reuses them. Descriptor fields below come from the installed Playwright1.64.1 device registry; screen/scale/user-agent settings are emulation inputs, not physical hardware or OS evidence.

| Project | Engine / descriptor | Viewport, CSS pixels | Screen, CSS pixels / scale | Mobile / touch | Evidence limit |
| --- | --- | --- | --- | --- | --- |
| desktop-chromium | Chromium / Desktop Chrome |1280 ×720 |1920 ×1080 /1 |no /no | Descriptor's Windows user agent does not establish Windows execution; CI host is macOS for the frontend suite and Ubuntu for API shards |
| phone | WebKit / iPhone13 |390 ×664 |390 ×844 /3 |yes /yes | Emulation, not a physical iPhone, iOS version or installed Safari release |
| tablet | WebKit / iPad(gen7) |810 ×1080 |No separate screen field in this descriptor /2 |yes /yes | Emulation, not physical iPadOS/Safari acceptance |

Playwright1.64 forwards descriptor screen dimensions ([upstream release notes](https://github.com/microsoft/playwright/releases/tag/v1.64.0)); viewport alone does not fully describe the profile. The descriptor user-agent's OS/version text is not an observed OS. Capture actual browser/host versions when an acceptance claim requires them.

| Evidence observation | Source / configured hosts | What passed / what remains unverified |
| --- | --- | --- |
| Accepted main after PR117 |cc243fb; [run41260731060](https://github.com/LimYouSheng/FitfinityReact/actions/runs/41260731060); frontend macos-15, real-API shards ubuntu-latest | Complete frontend/backend/API gates, including1155 frontend browser and396 real-API cases. Exact hosted OS patch/browser.version() values are not recorded in this table; labels do not prove them. |
| Separate reviewed dependency candidates | PR118 head50c1335 [run41371397837](https://github.com/LimYouSheng/FitfinityReact/actions/runs/41371397837); PR119 head6ad701a [run41371414485](https://github.com/LimYouSheng/FitfinityReact/actions/runs/41371414485); same configured profiles/host labels | All required gates passed on those separate heads. They do not accept the combined PR120 head. |
| PR120 verified candidate |7f36ae8; [run41403809510](https://github.com/LimYouSheng/FitfinityReact/actions/runs/41403809510); macos-15 unit/build/browser profiles; ubuntu-latest quality/backend/API groups | All16 verification jobs passed:1511 units,1155 simulator browser cases,1422 backend cases,636 infrastructure cases and396 real-API cases, plus133 quality regressions. Exact OS patch/browser.version() observations are not retained here. Later source heads require fresh CI; merge/deployment remain separate. |
| Physical developer-AWS acceptance | Designated Owner/Admin/Trainer records | Current deployed revision/device evidence remains pending; no real Samsung/iPad, branded Edge or Firefox acceptance inferred. |

These are discrete source/configuration observations, not coverage of every earlier, later or intermediate browser/runtime version. Playwright's [exact package metadata](https://registry.npmjs.org/@playwright/test/1.64.1) declares Node>=20; Fitfinity deliberately selects Node24 via .nvmrc with a >=24.15.0,<25 project range and checks all locked engine requirements. That declared range is a configuration policy, not proof every patch in it has been tested. `macos-15` and `ubuntu-latest` are workflow selections, not a complete upstream OS/architecture support matrix; consult the selected release's documented platform requirements before changing hosts. Externally prepared browser images/caches need their own matching metadata and acceptance.

Record physical results in the [Owner](uat/owner.md), [Admin](uat/admin.md) and [Trainer](uat/trainer.md) worksheets: device model, exact OS and browser versions, deployed revision, outcome and remarks/lag. Leave unexecuted cases blank. A customer minimum-browser policy requires a separate explicit decision and evidence; developer tooling requirements do not automatically change customer support policy.

CodeQL runs independently of application verification in [codeql.yml](../.github/workflows/codeql.yml): JavaScript/TypeScript and Python in parallel on PRs/main pushes, manual dispatch and Mondays09:00 Singapore. Both use `build-mode: none` on GitHub-hosted Ubuntu with the Action’s Node24 runtime; this adds no customer browser/runtime support requirement. Inspect Security → Code scanning for findings. Review full main-branch SARIF and the alert list as well as PR reports: a sparse PR report does not establish a complete clean baseline. Finding assessment and severity-based merge protection remain separate from successful workflow execution. The reviewed dispositions and alert-management limitations live in [Security](security.md). Existing three application aggregate gates remain required.
