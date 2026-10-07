# North Star: SESSION-OPEN-01

## Outcome

Implement undated postponement and package-scoped chronological session numbering in the demo portal, through existing draft PR #8. Normal cloud development is validated; this is its first functional task. The user alone authorizes merge.

## Acceptance — local verification passed; final CI pending

- [x] Eligible Postpone releases only the selected booking into an explicit undated open state, preserving its identity, attachments, credits, package validity and standing schedule.
- [x] Authorized trainer and Owner/Admin users can find multiple open sessions first in both Upcoming Sessions and All Sessions, including after refresh, and schedule the same record through the existing ad-hoc date/time flow.
- [x] Bringing the last eligible scheduled session forward requires no postponement or new credit; all three 12-session numbering examples pass.
- [x] Conflicts, approval, stale requests, idempotency, completion protection and atomic 24-hour Undo remain enforced for booking and numbering changes.
- [x] Affected unit/browser checks pass in all three canonical browser projects with fresh builds/PWA checks. Reuse matching backend receipts only when relevant inputs are unchanged.
- [ ] Both complete final-SHA GitHub CI jobs pass, including macOS/WebKit; record results in PR #8 and the delivery report without a self-referential commit.
- [x] Rules, Service Contracts, Progress and Journey record the scenarios, actual evidence and demo/API/device limitations together.

## Boundaries and budget

- Existing checkout and feature branch only. Preserve unknown work; no reset, clean, stash or silent source advance.
- One agent; maximum three repair iterations or 30 minutes of active work. Waiting for existing CI is separate from the active repair budget; do not stop CI monitoring solely at 30 elapsed minutes. No unattended relaunch.
- Reuse dependencies, engines, browser runtime, caches and backend trust. Unsupported API business writes remain disabled until transactional backend support exists.
- No merge, auto-merge, main/force push, AWS/image work, live migration, deployment, tunnel retry or environment republishing.
- Passing checks leads to user review, not merge permission. Physical-device and live API acceptance remain separate.

## Deferred goal: CLOUD-01 — incomplete

Fresh-task runtime validation passed at `8945ca17121b3742a25aea4f16dffef190cbbf06`. Documentation successor `53aefd6ae8dcaf2f639bbf40548368fb111cce43` passed both required jobs in [run 37560945624](https://github.com/LimYouSheng/FitfinityReact/actions/runs/37560945624). Existing setup and reconciliation receipts remain in `PROGRESS.md` and Journey.

Public-preview acceptance remains blocked by the recorded Cloudflare DNS/proxy provisioning failure. No public PR-preview URL exists; main-branch Pages is not a PR preview. Preserve this unmet criterion and separate physical-device acceptance. Do not retry tunnels in this task.

## Owners

- Business scenarios: `docs/FITFINITY_RULES_AND_ARCHITECTURE.md`.
- State/operations/persistence/Undo: `docs/SERVICE_CONTRACTS.md`.
- Current task/evidence/blockers: `PROGRESS.md`.
- Decision/history: `docs/FITFINITY_JOURNEY.md`.
- Engineering rules and commands: `AGENTS.md` and `docs/CODEX_CLOUD.md`.
