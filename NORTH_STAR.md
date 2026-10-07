# North Star: CLOUD-01

## Outcome

- Make Fitfinity's routine development reproducible from a fresh Codex Cloud task, with reviewed GitHub source, strict validation and a usable preview.
- End at a reviewable PR and recorded setup evidence. Merging, publishing and AWS deployment remain separate decisions.

## Scope

- Concise `AGENTS.md`, cloud operating guide and compact progress/task ledger.
- Reconcile intended Mac-only work, including the AWS runbook, before declaring GitHub canonical.
- Configure and verify the cloud environment using existing repository commands.
- Preserve application behaviour, test strength and canonical ownership.

## Acceptance

- [x] Intended local work is reconciled into reviewed GitHub commits; no unknown edits or duplicate files were discarded. User merged PR #9 at `7970f65b5975a6554c46eb521c7ca118939e4bb9`; evidence is in `PROGRESS.md`.
- [x] A fresh cloud task reads the current instructions and records its repository, branch, HEAD and runtime versions. Fresh-task runtime validation passed on 7 October 2026 at `8945ca17121b3742a25aea4f16dffef190cbbf06`; normal cloud development can resume; see `PROGRESS.md`.
- [x] Dependencies install from the committed lockfile; relevant frontend checks and Playwright run against a fresh internal preview. Locked setup reused; all three focused browser projects, fresh root/Pages/API-fixture builds and all three PWA checks passed. Earlier internal demo behavior evidence remains separately recorded.
- [x] Backend/container capability is verified, or its limitation is recorded and the unchanged authoritative backend CI gate passes. Matching-input cloud receipt: 416 backend/PostgreSQL and 408 infrastructure cases; cloud-only trust remains separate from CI.
- [ ] Full required GitHub Actions checks pass for the final PR candidate; macOS WebKit coverage remains intact. Both jobs passed for the tested starting SHA; the documentation successor needs its own CI, recorded in PR #8 without a self-referential follow-up commit.
- [ ] A usable user preview is demonstrated, with the exact revision and demo/API mode stated. **Blocked:** authorized Cloudflare trial failed at DNS/proxy provisioning; no public URL. Do not retry without new network evidence.
- [ ] The PR includes verification evidence and remaining human/device/AWS boundaries; no merge or deployment occurs in the development loop.

## Exclusions

- No business features, client production rollout, IAM/policy changes, deployment activation, database migrations or quota-request resubmission.
- No new CI preview deployment, always-running agent, scheduler, paid service, custom MCP server or code graph in this milestone.
- Existing hosted Pages is the merged-main demo; it must not be represented as a PR preview.

## Run policy

- One ready ledger task per run; stop at its acceptance or a concrete blocker.
- No unattended relaunches are configured. A future orchestrator needs an explicit run/time/spend limit and stop condition before activation.
- Run focused checks while changing code; consume existing full-CI results for the final candidate rather than repeatedly duplicating that suite.
- This guarded-workflow run permits at most three repair iterations or 30 minutes of active work. CI may continue afterward; pending is not passed.
- Do not enlarge scope or edit acceptance criteria to make the milestone appear complete. Ask the user for a changed outcome when needed.

## Owners

- Tasks, blockers and evidence: `PROGRESS.md`.
- Operating rules: `AGENTS.md`.
- Setup and verification commands: `docs/CODEX_CLOUD.md`.
- After acceptance, replace this bounded milestone with the next user-approved outcome; retain the completed receipt in Journey.
