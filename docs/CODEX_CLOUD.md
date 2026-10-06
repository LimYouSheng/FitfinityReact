# Fitfinity Codex Cloud workflow

Prepared 6 October 2026 against GitHub `main` at `d2e8a4b7e44c1554b1f31b5337b87014e6446fdf`. This guide prepares the transition; environment activation and local-source reconciliation require their own evidence.

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

## 2. One-time source cutover

- The user reported local repositories ahead of GitHub. A cloud checkout cannot see uncommitted Mac files. Do not declare the migration complete from GitHub alone.
- Preserve the complete local work and inventory tracked, staged and untracked changes. In the existing checkout, `git status --short --branch --untracked-files=all`, `git diff --stat`, `git diff --cached --stat`, and `git log --oneline origin/main..HEAD` are read-only starting points. Refresh `origin` before making the final ahead/behind comparison.
- Compare local docs with this candidate before replacing anything. The newly copied `docs/AWS_DEPLOYMENT_RUNBOOK.md` is intended work. Compare its contents, not just its filename.
- The earlier status listed many untracked names containing ` 2`. Do not commit, delete or classify them as disposable merely from that suffix. Compare them with their canonical files, preserve any unique work, and record their disposition.
- Review intended changes, stage exact paths and preserve them on a dedicated migration branch. No `git add .`, reset, stash, clean, force push or direct push to `main` as a shortcut.
- Reconcile the documentation PR with that source branch, resolve conflicts in canonical owners, and run required checks. The user controls merging. Record the final accepted main SHA before starting ordinary cloud feature work.
- After cutover, GitHub is canonical. Optional local use pulls reviewed GitHub state; Mac installers and local AWS login are no longer routine development prerequisites.

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

### Paste into the environment setup conversation

```text
Prepare LimYouSheng/FitfinityReact for Codex Cloud using its AGENTS.md and
docs/CODEX_CLOUD.md. Confirm the reconciled source branch and SHA first.
Use Node 24 and npm ci from the committed lockfile. Install Chromium and
WebKit through the repository's Playwright dependency. Record versions.
Verify Docker and Compose for the existing isolated backend test gate;
backend Python is 3.12 and test PostgreSQL is 17.11-bookworm. Report an
unavailable capability rather than weakening or replacing the gate.
Use demo mode, synthetic test data and no AWS/production credentials.
Prepare the Install script and Start skill using the canonical commands.
Demonstrate a fresh internal preview and an affected browser scenario.
Provide an accessible preview if this environment supports one; otherwise
record the exact missing capability. Do not publish application hosting,
change CI/infrastructure, merge a branch or deploy. Report setup evidence
and unresolved work for review before the environment is published.
```

### Canonical preparation commands

Run from the repository root after verifying Node 24:

```bash
npm ci
npx playwright install --with-deps chromium webkit
docker info
docker compose version
```

- Dependencies and browser installation belong in environment preparation. Do not reinstall them on every loop when the lockfile/setup is unchanged.
- The setup/start procedure must recheck dependencies after a changed lockfile and start only required services. Repository refresh alone is not proof that dependencies or running processes match the new revision.
- If Docker is unavailable, record that limitation. The unchanged GitHub Actions backend gate remains required; do not fake its receipt, use SQLite, skip database tests or invent a second verifier. Improving cloud backend capability is a separately bounded task.
- macOS WebKit/media evidence still comes from the existing macOS CI job. Linux cloud browser results are useful evidence but do not establish Safari/macOS or physical iPhone acceptance.

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

## 5. Efficient Ralph runs

- Treat Ralph as a bounded work cycle: read the small state files, choose one ready task, implement, verify, checkpoint, stop. No perpetual process is installed.
- A North Star states one milestone outcome, exclusions, objective evidence and stopping point. Do not use “finish Fitfinity” or the entire production roadmap as one autonomous run.
- The task ledger is the only queue. Each entry has a completion test, state and next action. An unresolved external dependency becomes a blocker, not a reason to spin or change goals.
- Reuse discovered owner paths and previous evidence. Search only relevant code/contracts; carry forward a concise diagnosis. Re-read after relevant changes or contradictory evidence.
- Run focused checks after each material fix and the complete required CI once the candidate is ready. Reuse an existing run for the same commit; do not start duplicate full suites or repeatedly poll while waiting.
- Stop a repeated failure when there is no new diagnosis or useful next experiment. Do not cycle model prompts, add speculative tools or increase test retries.
- Keep a single working agent by default. Delegate only when explicitly requested and when the split would avoid duplicated investigation; no standing swarm or heartbeat is part of this setup.
- Do not automatically escalate model size/reasoning for routine edits. Select a more expensive configuration only for an identified need and within the task's agreed limits.
- Before enabling unattended orchestration, specify finite run/time/spend limits and a resume policy. No numeric cost promise or billing cap is claimed by these Markdown rules; enforcement belongs in the actual runner/account controls.

## 6. Review and release boundary

- Review intended source/docs and checks, checkpoint the feature branch, then open or update its PR. Keep it draft while acceptance or required evidence is blocked.
- A full-green PR remains subject to user review/merge. Verify the resulting main commit separately. Main changes can trigger existing Pages/image workflows; do not treat a merge as a harmless development step.
- Never broaden GitHub permissions, change branch protection, enable release flags or alter AWS resources simply to finish a coding task.
- AWS automation should reuse proven repository operators and the runbook with separate least-privilege roles, source/digest binding, reviewable changes, idempotency and recovery evidence. Successful CLI history is the input to that work, not proof that unattended deployment is ready.
- The existing image/verification OIDC roles do not establish a complete application deployment role. Routine cloud development does not depend on native `aws login`; any unfinished AWS operator transition remains a release workstream.
- Last AWS hosting evidence remains quota-blocked, with first-owner creation accepted but live hosting/login unaccepted. Check current request status and applied capacity before any authorized resume; do not infer approval from an open support case.

## 7. Completion receipt

Record in `PROGRESS.md` and the PR: source SHA; scope/diff; actual commands and results; full-CI run URLs; preview revision/mode; unresolved limitations; next action. Move the completed milestone summary to Journey once accepted. A new cloud task must be able to continue from these files without rereading chat history.

Official behaviour checked on 6 October 2026: [Cloud environments](https://learn.chatgpt.com/docs/environments/cloud-environments), [AGENTS.md discovery](https://learn.chatgpt.com/docs/agent-configuration/agents-md). Repository instructions remain concise; detailed guidance is loaded by relevance.
