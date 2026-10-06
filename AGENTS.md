# Fitfinity engineering

## 1. Start

- Read `NORTH_STAR.md` and `PROGRESS.md`; confirm repository, branch, HEAD and existing changes.
- After source cutover, GitHub is canonical. Preserve unknown edits.
- Search relevant sections of `docs/FITFINITY_RULES_AND_ARCHITECTURE.md` and `docs/SERVICE_CONTRACTS.md`; do not load all history.
- Commands/cutover: `docs/CODEX_CLOUD.md`. AWS evidence: `docs/AWS_DEPLOYMENT_RUNBOOK.md`.

## 2. Build

- Use one cloud feature branch. Edit canonical owners; remove superseded logic and avoid duplicate implementations.
- Separate UI, business rules, persistence and infrastructure. Production authority stays server-side.
- Preserve unrelated behaviour. Add meaningful coverage for changed behaviour.
- Fix routine failures autonomously; escalate requirement, business-rule, architecture, security or material-cost decisions.

## 3. Ralph loop

- Choose one ready task serving the North Star; define completion evidence first.
- Inspect → implement → run affected checks → diagnose → update progress → checkpoint.
- Reuse findings/caches and read changed sections. Retry only with a new diagnosis or material fix.
- Stop at task acceptance, a blocker, the run budget or PR readiness. No unattended relaunch without explicit finite limits.

## 4. Verify

- Run focused checks while iterating. Codex may prepare browsers, run Playwright and inspect internal previews.
- Full final GitHub Actions validation remains authoritative, including macOS WebKit and real PostgreSQL.
- Never weaken assertions, skip coverage, lower required counts, add retries, raise timeouts or alter runner settings to obtain green results.
- Record SHA, command, environment and result. Separate cloud/CI, visual/device and live-AWS evidence; blocked is not passed.

## 5. Deliver

- Update affected docs/progress; review the diff and stage exact intended paths.
- Commit/push the task branch and open/update its PR when access permits. Reuse existing CI; require green checks for the final commit.
- Stop at PR-ready. Provide the PR, evidence, preview or blocker, and next action. Never merge, push to `main`, deploy or alter protected infrastructure in the loop.

## 6. Boundaries

- No reset, force push, destructive cleanup, real customer data, credential export or applied-migration edits.
- Keep AWS/production credentials outside coding tasks; connected tools grant no extra authority.
- One North Star, one ledger, relevant context. No speculative tooling, background agents or duplicated full test runs.
