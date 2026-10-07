# Fitfinity Codex Cloud workflow

Updated 7 October 2026 (Singapore). Accepted main for AWS-HOSTING-PREFLIGHT-01: `c66acf9032b9bf7b9b71fcf118f375e8bb6e9fd1`, PR #11 merged by LimYouSheng. This task uses authorized `docs/aws-test-hosting-preflight-2026-10-07`; image acceptance is verified separately from hosting/runtime acceptance. Future tasks must use their own explicitly authorized branch/checkpoint. Fresh-task runtime validation passed at `8945ca17121b3742a25aea4f16dffef190cbbf06`; normal cloud development can resume. Full CI for each new candidate, public-preview acceptance and device acceptance remain separate. [PROGRESS.md](../PROGRESS.md) owns exact receipts and blockers.

## 1. Canonical files

| File | Owns |
| --- | --- |
| [AGENTS.md](../AGENTS.md) | Short instructions loaded by Codex |
| [NORTH_STAR.md](../NORTH_STAR.md) | One bounded milestone: outcome, scope, acceptance and stop conditions |
| [PROGRESS.md](../PROGRESS.md) | Current task ledger, results, blockers and next action |
| [Rules and Architecture](FITFINITY_RULES_AND_ARCHITECTURE.md) | Current product rules, architecture and engineering principles |
| [Service Contracts](SERVICE_CONTRACTS.md) | Existing operation/service contract reference |
| [Journey](FITFINITY_JOURNEY.md) | Historical decisions and completed milestone evidence |
| [AWS Deployment Runbook](AWS_DEPLOYMENT_RUNBOOK.md) | Proven AWS calls, evidence, corrections and deployment blockers |
| This guide | Cloud setup, verification commands and source cutover |

Do not add a competing `ENGINEERING_RULES.md` or second task list. Existing canonical owners serve those roles. Read relevant sections using search; the large Rules/Journey files are not mandatory full-context input on every loop.

## 2. Accepted source and experiment branch

- Fresh user Git output confirmed local and remote main at `d2e8a4b7e44c1554b1f31b5337b87014e6446fdf`, with no tracked changes or unpublished commits. Only `docs/AWS_DEPLOYMENT_RUNBOOK.md` was untracked; its user-confirmed blob was `041d15c2e68e8b878d71455c30299a9b5b755ff4`.
- PR #9 preserved that exact file. Both required PR checks passed; the user merged it on 6 October at 22:46:11 Singapore as `7970f65b5975a6554c46eb521c7ca118939e4bb9`. Main contains the accepted local checkpoint. Post-merge verification remains a separate receipt; see `PROGRESS.md`.
- Earlier ` 2` duplicate entries were absent from the latest user inventory. This task did not delete them or infer that they were disposable. Preserve any newly discovered unknown local work and inspect it separately.
- PR #8 merged as `40e8bb36868958e56813e2daa27c6ff074b9aced`; its demo milestone is accepted. Use the current task's authorized branch and exact source checkpoint. Create a new branch only when authorized, after fetching/verifying main and a clean checkout; stop if main advanced. Never merge to obtain a preview.
- Confirm the actual branch and HEAD at setup and every fresh cloud task; instructions and source guards must match the current authorized task. Read its `AGENTS.md`, `NORTH_STAR.md` and `PROGRESS.md` before work.
- GitHub is canonical for this accepted checkpoint. Optional Mac use must preserve new edits and pull reviewed GitHub state; Mac installers and local AWS login are no longer routine development prerequisites. No `git add .`, reset, stash, clean, force push or direct main push as a shortcut.

The October hosting operator has an exact source manifest and saved state. A newer docs commit cannot silently become its accepted release baseline. Retain its original evidence; separately review any replacement release manifest/operator before resuming deployment.

## 3. Cloud environment setup

Use the current **Codex Cloud** environment flow: select the Fitfinity repository, ask Codex to prepare and test its setup, review the report, then publish. A new task starts from the published environment; setup changes need republishing. Current configuration uses an **Install script** and **Start skill**. The older setup/maintenance-script UI belongs to the legacy environment flow. [Official environment guide](https://learn.chatgpt.com/docs/environments/cloud-environments)

### Repository requirements

| Requirement | Source and treatment |
| --- | --- |
| Node 24 | `.github/workflows/verify.yml`; record actual Node/npm versions. No `.nvmrc` exists at the reviewed base. Do not import another project's version pins. |
| Frontend dependencies | `npm ci` from `package-lock.json`; no opportunistic upgrades or lockfile regeneration |
| Browsers | Lockfile-installed Playwright; Chromium and WebKit used by the existing projects |
| Backend Python | `backend/pyproject.toml`: Python 3.12 only; not a generic Python 3.11+ assumption |
| Backend/container gate | `backend/compose.yaml`, `backend/Dockerfile` and `scripts/verify-backend.mjs`; verify Docker daemon and Compose capability |
| Database | Isolated test PostgreSQL `17.11-bookworm`, created and removed by the canonical Compose verifier; never AWS RDS or customer data |
| Application mode | `VITE_PORTAL_MODE=demo`, empty `VITE_API_BASE_URL`; existing API test fixtures remain separate from live AWS |

### Install once; guard each task

Use the existing isolated checkout; no worktree unless explicitly requested. **Install script contains Bash; Start skill contains prose.** The saved Install script uses `npm ci`, downloads the lockfile's Chromium/WebKit, prepares container libraries and cloud-only backend trust, then runs initial lint, browser/build/PWA and full backend validation. Do not execute installation or full backend validation on every task startup. Preserve signatures, TLS and dependency hashes.

For initial C3 validation, explicitly supply `FITFINITY_EXPECTED_HEAD=16eea945f9324b6f20610d0a0b98b1a1cb6014e9` when running the saved Install script; it compares full HEAD with the supplied value before installation. Later validation uses that task's authorized checkpoint, not this historical SHA. Browser preparation traps exit to remove only its owned temporary container and preserves the original failure status. Startup remains prose, with each task's agreed budget.

Read the canonical rules/goal/ledger/guide at entry and compare the requested checkpoint before editing. Run these lightweight guards; also require equality with the task's explicit HEAD when supplied. A historical receipt SHA is not a permanent starting HEAD for future tasks.

```bash
set -euo pipefail
cd /workspace/FitfinityReact
git rev-parse HEAD
test -z "$(git status --porcelain=v1 --untracked-files=all)"
: "${FITFINITY_EXPECTED_BRANCH:?Supply the current task branch}"
: "${FITFINITY_EXPECTED_HEAD:?Supply the current task full HEAD}"
: "${FITFINITY_ACCEPTED_MAIN:?Supply the current task accepted main}"
test "$(git branch --show-current)" = "$FITFINITY_EXPECTED_BRANCH"
test "$(git rev-parse HEAD)" = "$FITFINITY_EXPECTED_HEAD"
git merge-base --is-ancestor "$FITFINITY_ACCEPTED_MAIN" HEAD
node --version
npm --version
python3 --version
test "$(node -p 'process.versions.node.split(".")[0]')" = 24
python3 -c 'import sys; assert sys.version_info[:2] == (3, 12)'
export npm_config_cache=/workspace/fitfinity-setup-evidence/npm-cache
export PLAYWRIGHT_BROWSERS_PATH=/workspace/fitfinity-setup-evidence/browsers
export BUILDX_CONFIG=/workspace/fitfinity-setup-evidence/buildx
export VITE_PORTAL_MODE=demo
export VITE_API_BASE_URL=''
```

Stop on a mismatch or unexpected edits; never reset/discard them. A detached restored checkout may have feature-branch metadata restored at its configured HEAD after the clean-tree/source check; do not silently move to a newer tip. Record Docker/Compose versions when those services are needed.

The user confirmed publication of the correct source ref, and the fresh-task runtime receipt is recorded in `PROGRESS.md`. Missing configuration-management tools do not block runtime validation against the authorized checkpoint; runtime success alone does not verify saved settings. Do not republish as part of routine validation.

Reuse valid dependencies, npm/buildx caches, pinned engines and prepared images. `npm ls --depth=0` checks dependency availability; reinstall/recreate only if missing or relevant lockfiles/setup inputs changed. Start only required services and verify behavior: retained files/images are not live-process readiness. Restart processes after restoration.

### Prepared Linux browser runtime

The non-root host lacks WebKit library registration. Retained image `fitfinity-browser-runtime:node24-pw1.62.1` uses Node 24/Debian trixie and Playwright-installed system libraries. The saved Install script recreates it from a pinned official Node image when missing; an engine-version change requires a matching runtime. Engine archives stay in the workspace path above. Do not bypass dependency checks or change Playwright settings.

Run this canonical restoration smoke in the prepared container. It retains fresh root/Pages/API-fixture builds, PWA checks and all three projects. Later iterations substitute a real affected spec/filter; full local suites run only when warranted by the change.

```bash
pw_version="$(node -p 'require("@playwright/test/package.json").version')"
browser_runtime="fitfinity-browser-runtime:node24-pw${pw_version}"
docker run --rm --init --shm-size=1g --user "$(id -u):$(id -g)" \
  --workdir /workspace/FitfinityReact \
  --mount type=bind,source=/workspace/FitfinityReact,target=/workspace/FitfinityReact \
  --mount type=bind,source=/workspace/fitfinity-setup-evidence/browsers,target=/workspace/fitfinity-setup-evidence/browsers,readonly \
  -e PLAYWRIGHT_BROWSERS_PATH=/workspace/fitfinity-setup-evidence/browsers \
  -e npm_config_cache=/tmp/fitfinity-npm-cache \
  -e VITE_PORTAL_MODE=demo -e VITE_API_BASE_URL= -e CI=true \
  "$browser_runtime" npm run test:e2e -- tests/m4-navigation.spec.js --grep 'password screen returns' --reporter=list
```

These are Linux container results. Existing macOS WebKit/media CI and physical-device acceptance remain distinct. The container gate owns its internal port 4173; it provides no user-facing preview surface.

### Cloud-only backend trust and receipt reuse

The saved Install script generates files outside checkout under `/workspace/fitfinity-setup-evidence/backend-trust/`. A named build context supplies the current **public** host CA bundle and `PIP_CERT` for verified pip downloads. A generated Dockerfile retains canonical instructions and normalizes copied `/app` read/traverse permissions before the existing non-root user runs. The local Docker shim adds a supported Compose override only for canonical backend tests; verifier arguments, isolated PostgreSQL, logs, cleanup and exit status remain intact. Tracked source and authoritative CI are unchanged.

Refresh generated setup after CA/Dockerfile/path changes. Run the unchanged gate with its saved setup:

```bash
PATH=/workspace/fitfinity-setup-evidence/backend-trust/bin:$PATH \
  BUILDX_CONFIG=/workspace/fitfinity-setup-evidence/buildx npm run verify:backend
```

Use full backend verification during initial validation or relevant backend, lockfile, container, verifier, infrastructure or trust changes. Reuse an earlier complete receipt only with supporting logs and matching inputs; document input comparison for a documentation-only successor. Do not use SQLite, skip database tests or invent another verifier. If Docker/Compose/trust is unavailable, record a blocker; unchanged full backend CI remains mandatory.

### Access

- Routine development should work from the user's OpenAI login with 2FA and connected repository access. Initial connection/reauthorization may still be required; this is not a guarantee that other accounts never prompt again.
- Allow package/download hosts actually needed by setup. Test connectivity and permissions independently. GitHub access in ChatGPT does not prove the same connection is enabled in every Codex environment.
- Current cloud variables reach programs directly; network-secret placeholders are substituted by the HTTPS proxy for allowed destinations. Do not assume the legacy setup-only secret behaviour applies. [Official configuration reference](https://learn.chatgpt.com/docs/environments/cloud-environments#configure-environment-variables-and-network-secrets)
- This development environment needs no AWS profile, client password, Cognito token, real DB URL or long-lived AWS key. Leave production/provider write tools outside the coding loop.
- MCP is an access mechanism, not persistent memory or extra authority. Add a connection only for an identified task; repo files own project state. No custom MCP server or always-running bot is required for this migration.

## 4. Verification and preview

Use actual scripts in `package.json`; there is no generic `npm run lint`, typecheck or formatter command to invent. Changed behaviour determines the focused scope. Preserve existing test inventory checks and update their owners together only when legitimate tests are added.

| Purpose | Existing command |
| --- | --- |
| Semantic lint/quality | `npm run verify:lint` |
| Quality-checker regression | `npm run verify:quality-checker` |
| Full frontend units | `npm test -- --reporter=verbose` |
| Affected units | `npm test -- path/to/affected.test.jsx --reporter=verbose` (substitute a real affected owner) |
| Full browser/build/PWA gate | `CI=true npm run test:e2e -- --reporter=list` |
| Affected browser gate | `CI=true npm run test:e2e -- tests/affected.spec.js --reporter=list` (substitute a real affected spec; retain all applicable projects) |
| Health verifier regression | `npm run verify:health-checker` |
| Shared source health | `npm run verify:health` |
| Paper-form parity | `npm run verify:assessments` |
| Full backend/PostgreSQL, including offline infrastructure | `npm run verify:backend` |
| Offline infrastructure alone | `npm run verify:infrastructure` |

- The browser command builds and verifies the root, Pages and API-test bundles before Playwright. Do not run browsers against stale output or mistake a selected spec for full acceptance.
- The backend gate already includes infrastructure checks; do not repeat the latter immediately without a specific reason.
- `.github/workflows/verify.yml` owns authoritative full verification. `scripts/verify-test-results.mjs` and the backend verifiers own required receipts/counts. Read current owners instead of copying historical numbers into new scripts.
- Preserve command failures through log capture (`set -o pipefail` when piping through `tee`). Keep complete logs/traces as artifacts, with a short summary in `PROGRESS.md`.
- For documentation-only edits, check changed links, instructions and diff. Do not run full app tests repeatedly in the agent workspace; unchanged required CI remains in force.

### Internal preview

```bash
VITE_PORTAL_MODE=demo VITE_API_BASE_URL='' npm run build
npm run verify:pwa -- dist /
npm run preview -- --host 0.0.0.0 --port 4173
```

- Use this for the cloud preview surface when supported. Stop the manually started preview before the full `CI=true` Playwright gate, which owns port 4173 itself.
- For fast development feedback, `npm run dev -- --host 0.0.0.0` is available; final browser evidence uses fresh production builds.
- Record the exact source revision and demo/API mode. A running internal server is not automatically a user-accessible URL. Show the actual preview link/surface or state the blocker.
- Playwright screenshots/traces assist review; the user need not watch each run live. Physical PWA, touch/media and live password/MFA/recovery acceptance remain separately recorded.
- Existing `.github/workflows/pages.yml` deploys the main-branch staff demo after verification. It does **not** deploy PR previews. A new preview hosting workflow needs its own reviewed scope; never merge just to obtain a preview.
- Public preview remains **blocked** after the authorized Cloudflare trial: direct DNS registration failed and HTTPS-proxy provisioning returned `403 — Your request was blocked`. No public URL was created. Do not retry without new network evidence, represent internal addresses as accessible links or close this criterion. A saved network draft is not working connectivity.

## 5. Efficient Ralph runs

| Phase | Work and completion evidence |
| --- | --- |
| Initial preparation | Saved Install script prepares and validates locked dependencies, services and canonical gates; report setup/restoration separately from publication. |
| Task entry | Saved Start skill reads rules/goal/ledger, guards the requested source/runtime and reuses valid setup. Lightweight guards do not trigger full installation/backend tests. |
| Ralph iteration | Select one ready ledger task, define evidence, inspect/implement at canonical owners, run affected section-4 checks, diagnose, update progress and checkpoint. Retry only after a material correction/new diagnosis. |
| Feature-branch publication | Review diff, validate affected behavior/docs, commit/push only the existing branch and update its draft PR. Existing PR CI runs the full normal gates for the final candidate. Require both `verify / frontend` and `verify / backend`, retaining macOS coverage; stop for user review, never merge. |

`PROGRESS.md` is the only queue; `NORTH_STAR.md` supplies the bounded goal. Reuse matching receipts and CI runs, not older green status for a changed final candidate. Record concrete blockers. This guarded-workflow task allows **3 repair iterations or 30 minutes of active work**; CI may continue afterward and remains pending until completed. No duplicate full local suites, indefinite polling, scheduler or unattended relaunch is required.

Use one working agent unless delegation is explicitly requested. A future unattended orchestrator requires explicit finite run/time/spend limits and stopping conditions; no numeric billing enforcement is claimed here.

## 6. Review and release boundary

- Review intended source/docs and checks, checkpoint the feature branch, then open or update its PR. Keep it draft while acceptance or required evidence is blocked.
- A full-green PR remains subject to user review/merge. Verify the resulting main commit separately. Main changes can trigger existing Pages/image workflows; do not treat a merge as a harmless development step.
- Never broaden GitHub permissions, change branch protection, enable release flags or alter AWS resources simply to finish a coding task.
- AWS automation should reuse proven repository operators and the runbook with separate least-privilege roles, source/digest binding, reviewable changes, idempotency and recovery evidence. Successful CLI history is the input to that work, not proof that unattended deployment is ready.
- The existing image/verification OIDC roles do not establish a complete application deployment role. Routine cloud development does not depend on native `aws login`; any unfinished AWS operator transition remains a release workstream.
- Last AWS hosting evidence remains quota-blocked, with first-owner creation accepted but live hosting/login unaccepted. Check current request status and applied capacity before any authorized resume; do not infer approval from an open support case.

## 7. Completion receipt

Record the tested source SHA, scope/diff, actual commands/results, reused-receipt provenance, evidence locations, preview revision/mode and unresolved limitations in `PROGRESS.md` and the PR. Record the new final commit's full-CI links/status in the PR and delivery report after publication; do not create another commit solely to record its own successful CI. Move the completed milestone summary to Journey once accepted. A new cloud task must be able to continue from these files without rereading chat history.

Official behaviour checked on 6 October 2026: [Cloud environments](https://learn.chatgpt.com/docs/environments/cloud-environments), [AGENTS.md discovery](https://learn.chatgpt.com/docs/agent-configuration/agents-md). Repository instructions remain concise; detailed guidance is loaded by relevance.
