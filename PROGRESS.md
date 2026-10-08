# Fitfinity current progress

## Active task — AWS-PRIVATE-RUNTIME-01, 8 October 2026 (Singapore)

- Started clean in the existing checkout on `fix/aws-private-runtime-permissions-2026-10-07`, full HEAD `4965ba9ed2fd83e7b03b09cefda0eaeb4669912c`, no tracked/untracked changes. Authenticated remote main matched accepted PR #14 merge `d80021b0f99ec4637e90c63ac0ad3d8332fdcb1a`; feature ancestry and merged PR verified. Created only authorized `fix/aws-runtime-oidc-2026-10-08` from that exact checkpoint; no reset/worktree.
- PR #14's final [CI run 37642066405](https://github.com/LimYouSheng/FitfinityReact/actions/runs/37642066405) passed both required jobs, with 416 backend/PostgreSQL and 482 infrastructure cases. Its permission fixes and all scopes remain intact.
- YS reports named-profile Mac provisioning from accepted main, template SHA-256 `00fa091151848d6a715a1193c20d781973712e7ec90f314ad1fd500cf6dae077`, stack `fitfinity-test-github-runtime-role` CREATE_COMPLETE. Owner-provided provisioning and OIDC readbacks remain on the Mac; Codex did not inspect those files or call AWS. Exact stack/role/boundary identities, paths and successful normalized calls are in the AWS runbook.
- Read-only GitHub inspection of [failed collection 37653771533](https://github.com/LimYouSheng/FitfinityReact/actions/runs/37653771533), runtime job `112915682111`, attempt 1, confirms both verification jobs passed; credentials failed, operator skipped, collector artifact upload failed. No runtime resources were created. Runtime OIDC and current-image acceptance remain pending.
- Canonical trust now uses only `repo:LimYouSheng@141623519/FitfinityReact@1353173586:environment:aws-test`, matching the owner's working verification-role readback. Provider, audience, environment, permissions/boundary and GitHub subject configuration stay unchanged. Workflow retains its action pin, replaces unsupported `allowed-account-ids` with an immediate fail-closed `aws-account-id` output check, and preserves collector STS/runtime-role checks. Plan remains offline.
- Workflow failure diagnostics contain only mode and step outcomes in a separate artifact, never credentials or recovery state. Failed authentication still fails the job and skips the operator. Operator artifact checks remain strict when the operator starts. Runbook prepares a reviewed trust-only CloudFormation UPDATE change set; nothing is executed.
- Added four IAM negative-control cases to the infrastructure owner (52 runtime/policy; expected 486 infrastructure total) and six actual-workflow tests to the existing quality checker (43 total). Original trust/workflow rejected; corrected focused cases pass. Unchanged canonical `PATH=/workspace/fitfinity-setup-evidence/backend-trust/bin:$PATH BUILDX_CONFIG=/workspace/fitfinity-setup-evidence/buildx npm run verify:backend` passed 416/416 backend/PostgreSQL (72.25 seconds) and 486/486 infrastructure. `npm run verify:quality-checker` passed 43/43; lint (312 files), Ruff format/check, source/CSS health, 23 relative links, 14 Bash blocks, embedded procedure Python compilation and diff checks passed. Initial test formatting/closure binding and workflow object-identity comparison were repaired without changing assertions or coverage. Final-SHA CI follows publication. Logs: `/workspace/work/runtime-oidc/`.
- Reused Node `v24.19.0`, npm `11.9.0`, Python `3.12.14`, Docker `28.4.0`, Compose `v2.40.3`, dependencies/caches and documented backend trust. One agent, maximum three repairs or 30 active minutes; CI waiting separate. No reinstall or environment republishing.
- Next: YS review/merge, separately authorized change-set review/update/readback and fresh collection. Existing ECR pull policy, authenticated artifact retrieval, capacity/identity, fresh complete scans and unexpired exact `86183723…` approval remain prerequisites. No approval exception is extended or transferred. Current-image proof/owned cleanup and full application/authentication acceptance remain separate.
- No AWS API calls, IAM updates, workflow dispatch/rerun, image rebuild/scan, deployment, merge or main push in this task. YS alone merges. Final new-SHA CI links/status belong in the PR/delivery, without another self-recording commit.

| Task | State | Next evidence |
| --- | --- | --- |
| AWS-PRIVATE-RUNTIME-01 | OIDC repair and operator procedure prepared; full local checks passed | Final-SHA CI; then separately approved trust update and live OIDC/collection/runtime evidence |

CLOUD-01 remains incomplete due to public PR-preview blockage. SESSION-OPEN-01 demo/device acceptance is preserved independently.

## Deferred CLOUD-01 receipt — incomplete public-preview acceptance

The following receipt is historical cloud setup/runtime evidence. It is not acceptance of SESSION-OPEN-01. Final CI for its documentation successor subsequently passed as linked above.

### Checkpoint — 7 October 2026 (Singapore)

- North Star: `CLOUD-01` remains **incomplete** because public-preview acceptance is blocked. Fresh-task runtime validation passed at `8945ca17121b3742a25aea4f16dffef190cbbf06`; normal cloud development can resume with the existing source guards and reusable setup. Device acceptance remains separate.
- Runtime validation and this documentation task started clean in `/workspace/FitfinityReact` on PR #8's existing `docs/codex-cloud-workflow-2026-10-06` branch at that exact SHA. Accepted main `7970f65b5975a6554c46eb521c7ca118939e4bb9` is an ancestor; remote branch and PR head matched. No worktree was created.
- The user confirmed that the setup conversation had published the correct ref. Runtime validation independently verified the checkout and retained setup; saved source-setting management/read-back was unavailable here and was not used as a runtime gate. No environment republishing occurred in these tasks.
- This receipt update changes only `NORTH_STAR.md`, this ledger and `docs/CODEX_CLOUD.md`. Application source, tests, dependencies, workflows, infrastructure, `AGENTS.md` and the accepted AWS runbook remain unchanged. Completed runtime checks were read from their logs, not rerun to document them.
- PR #8 remains draft, targeting main. Both required jobs passed for the tested starting SHA; the new documentation commit requires its own full normal CI. Its final SHA, CI URLs/status and remaining blockers belong in the PR/delivery report; do not create another commit solely to record its own successful CI. The user alone authorizes merge.

## Historical CLOUD-01 task ledger

| ID | Task and completion evidence | State | Next action |
| --- | --- | --- | --- |
| C1 | Canonical instructions and recurring guarded workflow; affected documentation checks and final normal PR CI | Consolidated; starting-SHA CI passed, documentation-successor CI required | Check both required jobs for the exact final PR head |
| C2 | Reconcile intended local source/runbook with reviewed GitHub commits | Complete: user merged PR #9 | Do not repeat reconciliation without new evidence |
| C3 | Prepare/publish environment; verify restored dependencies, runtime, browser and internal preview | Fresh-task runtime validation passed at the tested SHA; publication confirmed by the user | Resume normal cloud development; reuse setup and task-specific source guards |
| C4 | Final candidate full CI, usable public preview and final acceptance receipt | **Public preview blocked; documentation-successor CI required** | No Cloudflare retry without new network evidence; keep unmet boxes open |

## Fresh-task runtime validation and reused evidence

Tested source: `8945ca17121b3742a25aea4f16dffef190cbbf06`, 7 October 2026 (Singapore). The completed fresh-task validation passed; the following documentation-only successor still requires its own final normal CI. Historical setup/backend receipt source: `16eea945f9324b6f20610d0a0b98b1a1cb6014e9`.

| Check | Result and scope |
| --- | --- |
| Source guards | Exact repository origin, branch/HEAD, clean tracked/untracked tree before and after runtime validation, and accepted-main ancestry passed; matching GitHub PR head confirmed |
| Host versions | Node `v24.19.0`, npm `11.9.0`, Python `3.12.14`, Docker `28.4.0`, Compose `v2.40.3`; Debian trixie Linux |
| Locked dependency reuse | Prior `npm ci` installed 231 packages from unchanged lockfile; restored `npm ls --depth=0` passed. npm/buildx caches present; no reinstall |
| Browser/runtime reuse | Playwright `1.62.1`; Chromium/headless-shell `1234`, FFmpeg `1011`, WebKit `2336`. Retained `fitfinity-browser-runtime:node24-pw1.62.1`, image ID `sha256:941f737e88ad77ca08072691bbcd91c91babd10b5d3c12212ae20b25c9eca1c7`, launched Node 24. No recreation |
| Canonical smoke | Guide's saved-container `npm run test:e2e -- tests/m4-navigation.spec.js --grep 'password screen returns' --reporter=list`, `CI=true`: **3/3 passed in 4.9 seconds**, desktop Chromium/phone WebKit/tablet WebKit, exit 0. Fresh root/Pages/API-fixture builds and three PWA checks passed (39 resources each); `VITE_PORTAL_MODE=demo`, empty `VITE_API_BASE_URL`. Vite emitted a chunk-size warning; settings were unchanged |
| Earlier internal preview (historical setup SHA) | Fresh demo bundle, empty API base URL; HTML, referenced JS/CSS, manifest and worker returned 200. Browser verified synthetic owner sign-in and dashboard/navigation. Internal behavior evidence, not a public URL |
| Backend receipt reuse | Supporting log: **416/416 backend/PostgreSQL and 408/408 offline infrastructure**, no skips/failures/expected failures. Reused from the historical setup SHA, not rerun. Comparison through the tested SHA found changes only in `AGENTS.md`, `NORTH_STAR.md`, `PROGRESS.md` and `docs/CODEX_CLOUD.md`; backend, scripts, dependency locks and CI inputs are unchanged. Dockerfile/host and stored CA fingerprints match; generated Dockerfile matches the canonical source plus documented trust/permission additions; scoped Compose override and Docker shim retained |

Documentation checks for this receipt update: the existing `check-workflow-docs.py` passed eight relative links, four Bash syntax blocks, balanced fences, canonical ownership/acceptance consistency, six agent-rule sections and the unchanged AWS runbook. Its four-document scope check covers cumulative changes since the historical setup SHA; a separate guard confirmed this update changes exactly the three files listed above, with no untracked files. `git diff --check` passed. Check log: `/workspace/work/fitfinity-doc-publication/documentation-checks.log`.

Fresh-task browser/build/PWA output: `/workspace/work/fitfinity-fresh-validation/browser.log`; the command exited 0. Source/runtime guards and fingerprint comparisons were recorded in the validation task output and are summarized above. Historical setup evidence under `/workspace/fitfinity-setup-evidence/`: `C3-RECEIPT.md`, `restoration-browser.log`, `restoration-preview.log`, `restored-preview.png`, `backend-trust-permissions.log` and cloud-only trust helpers. These are local environment files, not public GitHub artifacts. The fresh-task receipt is consolidated here; no second tracking file is required. Repeated Docker logs do not count as extra test executions.

Commands: the guide's unchanged prepared-container smoke runs `npm run build`, `npm run build:pages-test`, `npm run build:api-test`, then `npm run verify:pwa -- dist /`, `npm run verify:pwa -- dist-pages /FitfinityReact/`, `npm run verify:pwa -- dist-api-test /` and the selected Playwright scenario. Log capture used `set -o pipefail`. The reused backend receipt was originally produced by `PATH=/workspace/fitfinity-setup-evidence/backend-trust/bin:$PATH BUILDX_CONFIG=/workspace/fitfinity-setup-evidence/buildx npm run verify:backend`; that command was not rerun during fresh-task validation or this documentation update.

Reuse fingerprints: canonical Dockerfile SHA256 `0cc408586b4b64971fc9646c3b3b5dc8c2b4a89fa840e882ac4197b1df33a3c4`; current host/stored public CA bundle SHA256 `43e169bf3454bc74c12d3df8c1403f0b4e7da135bf5959f8ab31eb634896bf73`. Generated setup adds trusted CA input/read-traverse permissions for cloud-copied files only. TLS, hashes, non-root/read-only runtime, isolated PostgreSQL, verifier arguments, receipts and cleanup remain intact. Do not apply this shim to authoritative CI or weaken gates.

## CI, publication and remaining boundaries

- Tested starting PR #8 head `8945ca17121b3742a25aea4f16dffef190cbbf06`: both `verify / frontend` and `verify / backend` passed in [run 37502509031](https://github.com/LimYouSheng/FitfinityReact/actions/runs/37502509031). This is starting-SHA evidence, not acceptance of the documentation successor. The unchanged workflow retains macOS 15 frontend/WebKit and Ubuntu Docker/PostgreSQL, with all inventories/gates intact. Final-successor CI links/status are recorded in PR #8 and the delivery report.
- The earlier repository-pin correction task was stopped after the user confirmed publication of the correct ref. There is no outstanding source-setting correction in this runtime-validation task. Existing Install script, Start skill, dependencies, browser runtime, caches and backend trust were preserved; no installation or successful CI rerun was needed to record this receipt.
- One Start skill begins “Follow the current authorized task…” and delegates lifecycle/commands to canonical owners; Install script is a separate Bash field. It optionally verifies `FITFINITY_EXPECTED_HEAD` supplied by the validation task, avoiding a permanent old-commit pin. Its owned temporary browser-container cleanup passed isolated failure/success checks, retaining failure even if cleanup fails; Bash syntax passed. The current prompt owns three repair iterations/30 minutes; reusable startup honors each task's budget. Saving a configuration draft does not apply/publish it. Any new saved draft needs review and separately authorized activation; no automatic republish.
- **Public preview is blocked.** Authorized Cloudflare trial on 7 October: host/container registration failed resolving `api.trycloudflare.com` (DNS refusal); HTTPS-proxy POST returned `403 — Your request was blocked`. No public URL/edge connection was created. This run did not retry. Existing Pages is merged-main demo only, never PR #8 preview evidence.
- Linux evidence does not establish macOS/Safari media, physical PWA/touch/device or live password/MFA/recovery acceptance. No AWS/customer credentials, real data, app publication, deployment or infrastructure writes were used.
- Accepted main's [run 37481747347](https://github.com/LimYouSheng/FitfinityReact/actions/runs/37481747347) passed both required verification jobs; overall conclusion is failure because `image / image` failed. AWS/image investigation is outside this task; no whole-workflow success claim or image retry.

## Preserved source reconciliation

- User's local inventory matched previous main `d2e8a4b7e44c1554b1f31b5337b87014e6446fdf` with no tracked changes/unpublished commits. Only intended AWS runbook was untracked. PR #9 preserved it; user merged `7970f65b5975a6554c46eb521c7ca118939e4bb9` at 22:46:11 Singapore, 6 October. Runbook blob remains `041d15c2e68e8b878d71455c30299a9b5b755ff4`. No unknown files/duplicates discarded.
- PR #9 candidate `959c31a896b857c6ff7c3700dd5095b47d122131` passed [run 37469198825](https://github.com/LimYouSheng/FitfinityReact/actions/runs/37469198825). Original PR #8 candidate `821005d50c764134865af8f00ae4aa561260b878` passed [run 37466883211](https://github.com/LimYouSheng/FitfinityReact/actions/runs/37466883211). Both historical, not final-candidate acceptance.

## Next run and update discipline

- Normal cloud development can resume using the guide's task-specific source guards and matching setup/receipts. Read final-head CI from the current task's PR; no duplicate full runs or indefinite polling. Pending is not passed. Stop for review; never merge, auto-merge, push main or force-push.
- Resolve public preview only after new supported network/capability evidence; keep `CLOUD-01` incomplete. Do not silently defer/remove the criterion.
- Budget: three repair iterations or 30 minutes active work; CI may continue afterward. No unattended relaunch. Preserve SHA, commands, environment, counts and logs/URLs; move milestone to Journey only after acceptance.
