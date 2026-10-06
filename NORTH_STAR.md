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

- [ ] Intended local work is reconciled into reviewed GitHub commits; no unknown edits or duplicate files were discarded.
- [ ] A fresh cloud task reads the current instructions and records its repository, branch, HEAD and runtime versions.
- [ ] Dependencies install from the committed lockfile; relevant frontend checks and Playwright run against a fresh internal preview.
- [ ] Backend/container capability is verified, or its limitation is recorded and the unchanged authoritative backend CI gate passes.
- [ ] Full required GitHub Actions checks pass for the final PR candidate; macOS WebKit coverage remains intact.
- [ ] A usable user preview is demonstrated, with the exact revision and demo/API mode stated. If unavailable, this criterion remains blocked.
- [ ] The PR includes verification evidence and remaining human/device/AWS boundaries; no merge or deployment occurs in the development loop.

## Exclusions

- No business features, client production rollout, IAM/policy changes, deployment activation, database migrations or quota-request resubmission.
- No new CI preview deployment, always-running agent, scheduler, paid service, custom MCP server or code graph in this milestone.
- Existing hosted Pages is the merged-main demo; it must not be represented as a PR preview.

## Run policy

- One ready ledger task per run; stop at its acceptance or a concrete blocker.
- No unattended relaunches are configured. A future orchestrator needs an explicit run/time/spend limit and stop condition before activation.
- Run focused checks while changing code; consume existing full-CI results for the final candidate rather than repeatedly duplicating that suite.
- Do not enlarge scope or edit acceptance criteria to make the milestone appear complete. Ask the user for a changed outcome when needed.

## Owners

- Tasks, blockers and evidence: `PROGRESS.md`.
- Operating rules: `AGENTS.md`.
- Setup and verification commands: `docs/CODEX_CLOUD.md`.
- After acceptance, replace this bounded milestone with the next user-approved outcome; retain the completed receipt in Journey.
