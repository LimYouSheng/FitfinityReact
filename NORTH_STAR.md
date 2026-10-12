# North Star: Fitfinity AWS TEST login ready

Carry Fitfinity from M6.21 to a working, secure AWS TEST login that YS can use. This goal persists across repairs, PRs and operational checkpoints. Passing CI, merging a repair or preparing hosting advances the goal; none completes it. `PROGRESS.md` owns individual tasks and evidence; the AWS runbook owns exact release inputs, recovery commands and approval gates.

## Definition of done

- [ ] A verified public AWS TEST HTTPS URL serves the exact immutable API-mode frontend release and working backend.
- [ ] The existing Owner completes the applicable password setup and MFA flow and reaches the authenticated application.
- [ ] Reload/session refresh, expiry and sign-out work; signed-out navigation cannot restore protected access.
- [ ] YS's agreed desktop, Samsung and iPad checks are recorded separately from automated CI.
- [ ] Final source, frontend/runtime artifacts, image provenance, operational receipts and remaining limitations are recorded.

Broader M6 functionality, populated-database recovery and production readiness remain separate. Preserve the existing database, secrets, Cognito pool and Owner.

## Current path

Owner-merged PR #22 main is `58b771bd4e35f1ffb6c5ff1ccba1853f31796678`. The IAM repair completed. App deletion was acknowledged in run 38262560845; later owner readback confirms DELETE_COMPLETE, while the immutable workflow checkpoint remains pending. The successful edge and retained bucket are preserved. The fresh scan adds two glibc HIGHs to the existing zlib HIGH; YS authorized the explicit TEST-only three-finding renewal proposal ending 13 October 2026, 23:42:58 Singapore.

1. Require the reviewed renewal/source-transition PR with full final-SHA frontend/backend CI. Preserve the original operation, image/proof, all source/release records, write intents and receipts.
2. YS alone merges. Authenticate the exact owner merge and its matching immutable API release.
3. Separately authorize read-only app-deletion reconciliation from run 38262560845. Require fresh provider evidence and unchanged edge/bucket; never replay deletion. Review the new token before replacement app preparation and exact change-set execution.
4. Continue immutable upload, HTTPS/API smoke and Owner login/session/device acceptance through current scan, approval, capacity, source and ownership gates. A renewal or green CI does not complete the goal.

## Authority and iteration

One agent; reuse the existing checkout, dependencies, caches and valid receipts. Continue authorized investigation, focused repairs, tests and canonical documentation autonomously. Do not inherit the obsolete 30-minute automatic stop from earlier repairs. Honor explicitly agreed execution budgets with CI waiting separate; carry unfinished work forward accurately. Stop at a concrete blocker, required user action or authorization boundary with the next action prepared.

YS is the sole merge authority. No merge, auto-merge, main/force push, account reset, bootstrap replay or replacement operation to evade reconciliation. AWS mutations, hosting execution, scan requests, IAM changes and approval renewal require applicable explicit authorization. Keep credentials outside coding work. Source binding, historical receipts, resource identities, write intents and ownership checks remain mandatory.

Preserve image `sha256:861837230551824fdf37f868def500ca14abdbe489583f60ddacee932451eb5a`, original image source `33d124fcd59ffd3f9cb30d645660bdad99a21278` and the historical TEST exception expiry **11 October 2026, 20:41:44 Singapore**. Owner-merged PR #21 records the separately authorized bounded renewal ending 12 October 2026, 23:41:30 Singapore; historical receipts must not be rewritten. PR #23 proposes the separately authorized three-finding renewal ending 13 October 2026, 23:42:58 Singapore; only owner merge makes it effective. Stale scan evidence or expired approval blocks execution; never silently extend, transfer or weaken approval.

## Retained acceptance and limits

Private-runtime proof completed on 8 October at 12:23:04 Singapore, operation `aa2b2e439c3943b3b425de90302833ab`, run 37721383277, for the exact accepted digest with owned cleanup. Preserve that evidence; it is not live hosting/sign-in acceptance. Existing hosting source/operator, IAM preparation and release evidence are retained in the runbook.

SESSION-OPEN-01 is accepted for the demo, including YS's 7 October physical checks. Those results do not accept the AWS TEST login. CLOUD-01 public PR preview remains incomplete; no tunnel retry is implied. Journey owns completed history; Rules/Service Contracts own product behavior; AGENTS and the cloud guide own development workflow.
