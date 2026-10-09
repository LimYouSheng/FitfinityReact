# North Star: AWS TEST hosting — reviewed release preparation

## Current safe stopping point — 9 October 2026

Repair the confirmed hosting stop in run 37889740465 on a draft feature PR from merged main `b63fa5ef16904359a429e9048345b8ad13bea2be`. GitHub reported success because the CLI ignored the operator's return code; the receipt stopped after acknowledged edge change-set creation. Owner readback confirms an untagged `REVIEW_IN_PROGRESS` shell with the exact service role. Require ownership through the pinned acknowledged change set for that lifecycle state, retaining strict tags/role/template/resource checks elsewhere. The runbook owns exact evidence and pending live reconciliation.

Complete canonical backend and final-SHA frontend/backend CI. Keep existing operation `769df115e6ea4f478426f75c8a283a32`, source/release evidence and all write intents intact. A repair merge changes source; recovery cannot reuse the old release or bypass source binding. Separate review of a bounded same-operation source transition and replacement frontend artifact is required before resuming. Deployment/sign-in/recovery acceptance remains pending.

## Outcome

Prepare the first persistent AWS TEST hosting release from the reviewed retained hosting operator, consuming a verified immutable API-mode frontend artifact and exact accepted backend image. Private-runtime proof is completed; hosting, actual user sign-in and deployment/database recovery acceptance remain separate.

## Acceptance

- [x] Expected main/operator `087f744884f7ed0d3374aa8e4e2ba1e9ddbf3932` and PR #15 merge verified; existing clean checkout/setup retained.
- [x] Runtime run 37721383277 attempt 1 and both uploaded ZIPs authenticated; receipt/state/template/probe and all four responses agree. Both subnets and owned cleanup accepted.
- [x] Existing runbook/Journey/registry reconcile successful OIDC, collection, runtime and capacity while preserving failures, original image provenance and release refusal.
- [x] Recover exact October 6 hosting source; outer/payload hashes, safe paths, revision and all 57 manifest entries verified without historical execution.
- [x] Adapt canonical hosting owner, separate least-privilege role/manual protected workflow, reviewed change sets, immutable uploads and interruption/recovery behavior.
- [x] Implement immutable API-mode release builder/manifest and authenticated consumption with backend compatibility, build/PWA and exact source checks.
- [ ] Separately dispatch/review the final merged-main release artifact for live execution.
- [x] Meaningful changed-hosting failure/recovery checks: 61 hosting cases, 547 total infrastructure cases, and 416 backend/PostgreSQL cases retained.
- [ ] Complete final-SHA frontend/backend CI and draft PR review (results recorded in PR).
- [ ] Separately authorized hosting deployment, user sign-in/MFA and recovery acceptance.

## Boundaries

For this repair: one agent; at most three repair iterations and 30 active minutes, CI waiting separate. Evidence inspection, focused code/tests, canonical documentation and draft PR publication are authorized. No AWS mutations, hosting execution, workflow rerun, IAM change, image rebuild, scan request or merge. YS alone merges. Preserve exact `86183723…` image/original `33d124f…` source and TEST exception expiry (11 October 2026, 20:41:44 Singapore); future execution rechecks scans and approval.

## Completed AWS phase

AWS-PRIVATE-RUNTIME-01 completed at 12:23:04 Singapore, 8 October, operation `aa2b2e439c3943b3b425de90302833ab`, run 37721383277. Runtime acceptance is digest-bound and does not declare application deployment/live authentication. Runbook owns evidence/procedure; Journey owns the completed phase; PROGRESS owns this prepared hosting implementation and development checks.

## Completed and deferred goals

SESSION-OPEN-01 is accepted for the demo: final feature `437e6e5c7a74356c5f75c31d7b4ba1fbf7cdd0c6`, merged PR #8, full PR/main frontend/backend verification and main Pages deployment passed. YS confirmed all postponement physical checks passed on 7 October 2026. Journey owns the completed receipt; live API, media and unrelated acceptance stay separate.

CLOUD-01 remains deferred and **incomplete**: the public PR-preview criterion is blocked by the recorded DNS/proxy failure. Main Pages is not a PR preview. No tunnel retry in this task.

## Owners

`PROGRESS.md` owns the current ledger; Journey owns completed history; the AWS runbook owns candidate review, approval format, usage and live prerequisites. `AGENTS.md` and the cloud guide own guarded development. Rules/Service Contracts retain accepted demo semantics.
