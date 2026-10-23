# Fitfinity development commands and environment

[AGENTS](../AGENTS.md) owns execution rules; [Progress](../PROGRESS.md) owns current branch, evidence and blockers. Use the existing checkout and preserve unknown edits. A restored image may contain stale source: verify remote main and local HEAD before reuse. Old receipts are reusable only when relevant inputs match.

Historical setup, source cutover, preview failures and private-runtime receipts remain in [the pre-refactor guide](https://github.com/LimYouSheng/FitfinityReact/blob/df9cbbb75373eb7e57b31187eeb93077ea35cec8/docs/CODEX_CLOUD.md) and [AWS runbook](AWS_DEPLOYMENT_RUNBOOK.md). Their old branches, budgets and authorizations do not govern new work. No setup republishing or AWS credentials are required for ordinary source testing.

## Environment and commands

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

Supply the current task checkpoint through `FITFINITY_EXPECTED_HEAD` when running the saved Install script; never reuse a historical pin. Browser preparation traps exit to remove only its owned temporary container and preserves the original failure status. Startup remains prose, with each task's agreed budget.

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


## Test quality review and real API browsers — 16 October 2026

The existing `tests/` suite has two distinct purposes: demo/prototype behavior and frontend HTTP-contract behavior against `auth-api-fixture.js`. The latter hosts a Node HTTP simulator, not FastAPI. Its successful writes do not demonstrate SQL constraints, server authorization or persistence across backend processes. Keep its deliberate transport-failure injection; use the new `tests-api/` suite for integrated behavior.

`npm run test:api-browser` builds API mode and runs the actual FastAPI application over HTTP with an isolated PostgreSQL database, real migrations, auth-session cookies, CSRF, production JWT verification and domain routes. Only the external Cognito boundary uses a local provider with generated RSA keys and local invitation provisioning/delivery. No real email is sent. The test harness is under backend tests, is absent from the production runtime image, and adds no reset/test routes or production auth bypass. It refuses any control connection except the `postgresql+psycopg` driver, `test-db` host, default PostgreSQL port, `fitfinity_test` user/database, and no query parameters. This check runs before connecting. Each invocation owns a unique Compose project. A test-only dispatcher gives each browser worker its own migrated PostgreSQL database and real application; the worker header never grants authentication or domain permissions. Fresh-login contexts retain that worker scope. This prevents unrelated parallel tests changing global catalogue review versions; runner concurrency and stale-review assertions remain intact. Cleanup targets only databases created by this invocation and its Compose resources. Browser contexts authenticate through the UI with scenario-specific seeded accounts; production authentication limits remain unchanged. They do not inject demo storage or fulfill application requests. The interrupted-content-save case wraps native fetch before application initialization, waits for the real server to return a successful committed response, then discards that response at the client transport boundary. It checks the durable receipt, verifies exactly one write and reloads. This avoids WebKit service-worker routing differences; it is deterministic response-loss evidence, not a physical network outage drill.

The initial suite covers Owner/Admin package create/edit/deactivation and persistence through an independently authenticated browser context; immutable purchased terms; stale-version/conflicting-idempotency rejection; assigned Trainer session reads and server-enforced package/initial-assessment denial. Read returned identities and business dates; use unique names for parallel writes. The real API suite supplements the unchanged macOS prototype/HTTP-fixture CI gate and runs as an unconditional verification job. It does not certify real Cognito delivery, AWS or physical devices.

For a prepared cloud environment, `FITFINITY_BROWSER_BACKEND_IMAGE` may select the existing locked test image; the current backend is mounted read-only. `FITFINITY_BROWSER_RUNNER_IMAGE` optionally selects the prepared browser runtime and requires `PLAYWRIGHT_BROWSERS_PATH`; it shares only the isolated API container network namespace. Otherwise Playwright runs on the host. No dependency upgrades, retries or timeout relaxation are required. Port4180 binds only loopback; an occupied port fails rather than attaching to an unknown service.

Audit findings and actual pass/failure receipts belong in `PROGRESS.md`. Prioritize simulator/server drift, fixed waiting or repeated interactions, positional selectors without semantic scope, and assertions that only check fixture mutation. Hardcoded expected prices, counts, dates and permissions can be legitimate independent expectations; do not replace them with the production calculation and make the test self-confirming. Exact suite inventories protect against omitted coverage; retain them until a separately reviewed manifest-based replacement is justified. Mutation testing and performance testing remain noted future work, not implemented by this review.
