# North Star: AWS TEST hosting — reviewed release preparation

## Current safe stopping point — 9 October 2026

Continue on the owner-selected open draft PR #18, starting at `33075090a1fa601447b9b830d79e8426c4ff50c4`; PR #12 is already merged. Prepare the release evidence and execution gates using the existing canonical hosting implementation. No new operator implementation is currently required. Current AWS quota/capacity cannot be read here because no operator connection is configured; retain the guarded CloudShell fallback and require >=102 unreserved before reserving 2. The runbook owns the concrete bundle, source pins, missing local archive warning and recovery prerequisites.

IAM hosting authority is verified and the environment variable is owner-read back. One refreshed scan completed; the remaining zlib HIGH is unchanged, while the gcc-14 HIGH is no longer reported. The exact-set approval gate correctly stopped continuation. Prepare a draft policy re-review with unchanged image/provenance/expiry; only YS can merge it. No fresh image acceptance, hosting prepare, deployment, sign-in or recovery acceptance is claimed.

Merging this correction advances main and prevents consuming release 37743179778 from the new operator SHA. Preserve that historical artifact; obtain separate authorization for a replacement GitHub-only frontend release before continuing. Do not rebuild the backend, repeat the runtime proof, request another scan or relax same-source/freshness gates. The following implementation acceptance entries describe the retained PR #17 checkpoint; the runbook owns current live evidence and the blocking decision.

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

For this continuation: one agent; at most three repair iterations and 30 active minutes, CI waiting separate. Inspection, canonical documentation and existing draft-PR publication only; the three explicitly authorized quota-preflight reads require an existing authorized connection. No such connection is configured here. No AWS proof rerun, workflow dispatch, IAM provisioning, change-set execution, backend image rebuild/publication, infrastructure deployment or merge. YS alone merges. No quota resubmission, bootstrap replay or invitation resend. Preserve exact `86183723…` image/original `33d124f…` source and TEST exception expiry (11 October 2026, 20:41:44 Singapore); future execution rechecks scans and approval.

## Completed AWS phase

AWS-PRIVATE-RUNTIME-01 completed at 12:23:04 Singapore, 8 October, operation `aa2b2e439c3943b3b425de90302833ab`, run 37721383277. Runtime acceptance is digest-bound and does not declare application deployment/live authentication. Runbook owns evidence/procedure; Journey owns the completed phase; PROGRESS owns this prepared hosting implementation and development checks.

## Completed and deferred goals

SESSION-OPEN-01 is accepted for the demo: final feature `437e6e5c7a74356c5f75c31d7b4ba1fbf7cdd0c6`, merged PR #8, full PR/main frontend/backend verification and main Pages deployment passed. YS confirmed all postponement physical checks passed on 7 October 2026. Journey owns the completed receipt; live API, media and unrelated acceptance stay separate.

CLOUD-01 remains deferred and **incomplete**: the public PR-preview criterion is blocked by the recorded DNS/proxy failure. Main Pages is not a PR preview. No tunnel retry in this task.

## Owners

`PROGRESS.md` owns the current ledger; Journey owns completed history; the AWS runbook owns candidate review, approval format, usage and live prerequisites. `AGENTS.md` and the cloud guide own guarded development. Rules/Service Contracts retain accepted demo semantics.
