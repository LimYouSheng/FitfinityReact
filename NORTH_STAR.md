# North Star: AWS-IMAGE-ACCEPT-01

## Outcome

Evaluate an already-published immutable TEST image against fresh complete scan evidence and an explicit user-reviewed approval, without rebuilding, republishing, starting a scan or deploying. The original build revision and current approval-policy revision are separate. Existing strict image-candidate behavior remains unchanged.

## Acceptance — local checks passed; final CI and live acceptance separate

- [x] Verify trusted GitHub build/artifact provenance, original source manifest and ECR manifest/digest.
- [x] Reuse canonical scan validation: complete pagination/counts/identity, COMPLETE status, evidence no older than 24 hours and never future dated.
- [x] Exact TEST approvals bind reviewer/reference/reason/time/expiry, account/region/repository/digest, finding identities and original provenance; missing, revoked, malformed or mismatched approvals fail closed. Critical/unclassified findings remain blocked.
- [x] Separate read-only `image-accept` command and manual main-only protected Actions entry; no AWS writes, rebuild, publish or silent scan start.
- [x] Distinguish strict pass, TEST-exception acceptance and blocked; exception keeps strict policy false and full findings. No deployment/runtime/live-auth claim.
- [x] Meaningful regressions, full canonical backend/PostgreSQL gate, browser restoration smoke, lint/health and documentation/workflow checks pass.
- [ ] Both complete final-SHA GitHub CI jobs pass, retaining macOS/WebKit; results belong in the new draft PR and delivery report.

## Boundaries

Start from exact accepted main `40e8bb36868958e56813e2daa27c6ff074b9aced` on authorized `feat/aws-image-test-acceptance-2026-10-07`, existing checkout only. One agent, maximum three repair iterations or 30 minutes active work; existing CI waiting is separate. Reuse setup and caches. No live approval or AWS execution is authorized. No merge, auto-merge, main/force push, installation, IAM/protection change, deployment, tunnel retry or environment republishing. Only YS authorizes merge and subsequent live acceptance.

## Completed and deferred goals

SESSION-OPEN-01 is accepted for the demo: final feature `437e6e5c7a74356c5f75c31d7b4ba1fbf7cdd0c6`, merged PR #8, full PR/main frontend/backend verification and main Pages deployment passed. YS confirmed all postponement physical checks passed on 7 October 2026. Journey owns the completed receipt; live API, media and unrelated acceptance stay separate.

CLOUD-01 remains deferred and **incomplete**: the public PR-preview criterion is blocked by the recorded DNS/proxy failure. Main Pages is not a PR preview. No tunnel retry in this task.

## Owners

`PROGRESS.md` owns the current ledger; Journey owns completed history; the AWS runbook owns candidate review, approval format, usage and live prerequisites. `AGENTS.md` and the cloud guide own guarded development. Rules/Service Contracts retain accepted demo semantics.
