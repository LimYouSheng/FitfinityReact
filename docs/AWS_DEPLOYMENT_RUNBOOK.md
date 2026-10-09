# AWS deployment runbook

## Hosting preparation stopped after CREATE change set — 9 October 2026

Run [37889740465](https://github.com/LimYouSheng/FitfinityReact/actions/runs/37889740465) reported GitHub success, but authenticated `receipt.json` records `stopped: Stack ownership tags differ`. AWS creation was attempted and acknowledged; deployment remains pending. The CLI discarded the hosting return code. The repair propagates it through the actual process entry point; an operational stop retains its receipt and exits 1.

- Source: `b63fa5ef16904359a429e9048345b8ad13bea2be` (merged PR #18); operation: `769df115e6ea4f478426f75c8a283a32`.
- Evidence: artifact `11600513161`, ZIP SHA-256 `a384b8b2d8989ac269a4023786ad9c307d78a94b7ee890cfb5dad8477431ec90`, authenticated against GitHub metadata. Receipt checkpoint and state agree. Exactly one write is recorded: edge `create-change-set`, intent at 9 October 15:02:52 Singapore. `create_response_received=true`; no execute intent or completion is recorded.
- Stack: `arn:aws:cloudformation:us-east-1:418638389566:stack/fitfinity-test-login-edge/72a316e0-c3af-11f1-a593-0e4fbbd8106d`.
- Change set: `arn:aws:cloudformation:us-east-1:418638389566:changeSet/first-login-769df115e6ea4f478426f75c8a283a32/bebba252-f9c4-4293-ae4c-8e2f2b61d081`.
- User-supplied read-only CloudShell readback confirms the exact stack ID, `REVIEW_IN_PROGRESS`, `Tags: []`, and role `arn:aws:iam::418638389566:role/fitfinity-test-hosting-cloudformation`. Caller is the exact `arn:aws:iam::418638389566:user/fitfinity-deployer`. The original artifact retains response hashes, not these provider bodies; do not infer returned tags from hashes.
- Expected ownership tags are `Application=Fitfinity`, `Environment=test`, `Purpose=first-login-v1`, `OperationId=769df115e6ea4f478426f75c8a283a32`, and `TemplateSHA256=4f2d886e8d8517fcc359cf465944365d2a9ecd2694af4203baa51383988b9cdb`. User-supplied change-set readback confirms all five tags match exactly, the pinned stack/change-set IDs and names match, and status is `CREATE_COMPLETE` / `AVAILABLE`. The only proposed change is Add `EdgeAcl` (`AWS::WAFv2::WebACL`); creation time is `2026-10-09T07:02:53.595000+00:00`. Independent live template-body and empty-resource-inventory readback remain recovery prerequisites.

[CloudFormation CREATE change sets](https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_CreateChangeSet.html) first create an unexecuted stack shell. The old operator incorrectly required its proposed tags to be materialized on that shell. The repair permits empty stack tags only in `REVIEW_IN_PROGRESS`, with acknowledged durable stack/change-set IDs, exact matching change-set identity and all five proposed tags, an empty resource inventory before execution, the exact service role, and unchanged template/resource review. Deployed stacks and nonempty mismatching tags retain strict stack ownership checks. Missing acknowledgement, foreign IDs/tags/role, duplicate tags, unexpected resources and template drift fail closed. The receipt now records the bounded ownership readback. No retagging, deletion, creation replay or AWS write occurs in this repair task.

### Existing-operation recovery gate (not execution authorization)

1. Preserve the original ZIP, source, release and operation directory. Read only the exact stack/change-set ARNs above in `us-east-1`, guarding account `418638389566` and the reviewed operator identity. Reconcile `describe-stacks`, `describe-change-set`, `get-template --template-stage Original` for that change set, and `list-stack-resources`. Require unchanged IDs, exact proposed tags/template/Add-only edge inventory, `CREATE_COMPLETE`/`AVAILABLE` change-set state, empty stack resources and no unrecorded execution. Stop on ambiguity; never replay `create-change-set` or invent another operation to avoid reconciliation.
2. Preserve release run `37885447016`/attempt 1, artifact `11596294683`, ZIP `fd7f2e0eca27aee6b36c88cf3cd0c092477c10b2589b7943ffb15aa32abbc7ac` at original source `b63fa5ef16904359a429e9048345b8ad13bea2be`. Merging this repair advances main. Existing restoration and release checks intentionally reject cross-source recovery; simply passing the old resume run to the new operator is **not a valid recovery command**.
3. PR #19 now proposes the bounded `--source-transition` preparation described below. It authenticates the exact original evidence and YS-merged repair, preserves original IDs/intents and release provenance, verifies the unchanged edge template/image, and binds a replacement same-source API frontend. It remains blocked until owner merge, matching release and separately approved reconciliation; retain the existing AWS shell meanwhile. Ordinary recovery still rejects cross-source inputs.
4. Recheck current owner approval, scan freshness, permissions and >=102 unreserved Lambda concurrency. Keep image `sha256:861837230551824fdf37f868def500ca14abdbe489583f60ddacee932451eb5a`, original source `33d124fcd59ffd3f9cb30d645660bdad99a21278`, runtime evidence and TEST expiry **11 October 2026, 20:41:44 Singapore** unchanged. The recorded scan reaches freshness limit **9 October 23:29:27 Singapore**; stale evidence blocks, and read-only reevaluation does not refresh it.
5. Only after source recovery and all gates pass may the owner separately authorize resumption to produce the edge review token. Edge execution, app creation/execution, uploads, public smoke and scoped rollback each remain subject to the existing reviewed modes/approvals and durable intent reconciliation. Live hosting/sign-in/recovery acceptance remains pending. No workflow rerun, mutation or merge is authorized by this repair.

### Reviewed source transition proposed in PR #19

The persistent goal is AWS TEST login ready as defined in `NORTH_STAR.md`. A green repair PR or successful read-only transition does not accept hosting, Owner login or YS's devices.

`hosting_binding.restore_transition` supports only operation `769df115e6ea4f478426f75c8a283a32`, run `37889740465`, artifact `11600513161`, the original ZIP/source pins above, and original raw `hosting/state.json` SHA-256 `6d1ccd4dad76e9683bd5c4d93cfa12e82c360c7ec3d6684a815c796b7dc46014`. It requires authenticated PR #19 merged by LimYouSheng into this repository's main, with merge SHA exactly equal to the clean current-main operator source. Main advancement fails closed. The immutable old state and matching stopped receipt must describe the acknowledged, unexecuted edge-only checkpoint. The entire original checkpoint, including old frontend and write intent, is copied into `source_transition.original_checkpoint`; old artifacts are never rewritten.

The opt-in `source_transition=true` workflow input is accepted only with mode `prepare`, the exact old resume run and no review token. It verifies the replacement release against the new source through the existing release validator. `execution_authorized=false` blocks every AWS write, even an unexpected creation attempt. Live checks require the exact existing `REVIEW_IN_PROGRESS` stack, matching role/change-set tags and IDs, empty resources, unchanged template and exact Add-only `EdgeAcl` inventory; the existing operator produces the edge review token. Success records `source_transition.reconciled=true`, old evidence, new release and current source in a new receipt. Missing/deployed/foreign resources stop; no retag/delete/recreation occurs. A failed transition is not usable by ordinary resume. Preserve all failure artifacts and investigate; do not treat the new local state as execution authority.

After successful reconciliation, subsequent phases use **the new transition run** as the resume input, `source_transition=false`, the same operation ID and replacement release. Normal exact-source/exact-release checks apply. Never pass the old run directly to new-main ordinary resume. No AWS operation in this procedure has been executed by this repair task.

### Next owner actions and prepared commands

1. Review PR #19's final code, transition boundary and complete final-SHA frontend/backend results, then YS alone decides whether to merge. Do not merge a red or pending candidate. Authenticate the merge and freeze its exact main SHA before release; if main advances, stop and report it.
2. Inspect the shared AWS workflow queue; do not approve an unrelated image publication to unblock it. Prefer an existing successful frontend release at the exact merged SHA. Otherwise the authorized GitHub-only release mode runs full CI/build/PWA with no AWS credentials or image rebuild. With the exact merged main verified, the command is:

```bash
gh workflow run aws-test-hosting.yml --repo LimYouSheng/FitfinityReact --ref main -f mode=release
```

Leave every other input blank/default. Authenticate the resulting run/attempt/source/artifact ID, archive checksum, API-mode configuration (`/`, same-origin API), manifest/build/PWA evidence and accepted-backend compatibility. Authenticate original runtime run 37721383277/1/artifact 11528371887 using its canonical checksum; no proof rerun or backend rebuild.

3. Before dispatching any hosting phase, verify current permissions/identity, exact owner-merged approval, complete fresh scan findings, >=102 actual unreserved concurrency, quota status separately and existing AWS resources. Recorded scan freshness expires **9 October 23:29:27 Singapore**; TEST approval expires **11 October 20:41:44 Singapore**. These are hard stops, not renewal permissions. No authorized coding-environment AWS connection exists; use the established guarded CloudShell readbacks or protected operator connection, keeping credentials outside coding work.
4. Obtain explicit approval for one read-only source-transition reconciliation after presenting the frozen main/release and exact old stack/change-set IDs. Set `RELEASE_RUN` to the verified replacement run, recheck main, and dispatch:

```bash
gh workflow run aws-test-hosting.yml --repo LimYouSheng/FitfinityReact --ref main -f mode=prepare -f source_transition=true -f operation_id=769df115e6ea4f478426f75c8a283a32 -f resume_run=37889740465 -f release_run="$RELEASE_RUN"
```

This mode makes AWS reads only and creates a new GitHub evidence artifact; it does not create AWS resources. Preserve its exact run/artifact/checksum and successful receipt. Review the proposed Add `EdgeAcl` WAFv2 WebACL, ownership/template evidence and review token before seeking execution approval. A failed or uncertain readback is a blocker, not permission to replay the old operation.
5. After explicit edge-execution approval, use the verified transition run as `RESUME_RUN`, its edge token as `REVIEW_TOKEN`, and the same release. The prepared command is:

```bash
gh workflow run aws-test-hosting.yml --repo LimYouSheng/FitfinityReact --ref main -f mode=execute -f operation_id=769df115e6ea4f478426f75c8a283a32 -f resume_run="$RESUME_RUN" -f release_run="$RELEASE_RUN" -f review_token="$REVIEW_TOKEN"
```

Keep source transition default false. This is **not authorized now**. Execution creates the reviewed edge WAF resources. Subsequent app preparation and execution require separate concrete change-set review for existing architecture: private S3/CloudFront, regional API Gateway/WAF, exact Lambda image/alias and bounded application IAM. Preserve RDS, secrets, Cognito and Owner. Persist and reconcile each intent/response; resume only from the latest reviewed evidence at the same source. Failed public smoke is not acceptance; rollback is separately authorized and scoped to exact owned resources, retaining the frontend bucket and existing database/identity resources.
6. Record public HTTPS frontend/API verification, then YS's Owner password/MFA and authenticated-application checks. Verify reload/refresh, expiry, sign-out and denied signed-out history access. Record desktop/Samsung/iPad results separately from CI. The North Star remains incomplete until these checks and final release/operational receipts are recorded.

The sections below are historical checkpoints, superseded where the current incident evidence above differs.

**Current evidence checkpoint: 9 October 2026 (Singapore).** IAM hosting authority is verified; the refreshed image scan requires exact re-review, and the draft correction would require a new same-source frontend release after merge. Exact-image private-runtime proof and owned cleanup are accepted; first persistent TEST hosting automation is prepared, with live deployment/sign-in/recovery still pending. Recorded capacity is 1000 total/unreserved. Historical sections retain their original checkpoints; current acceptance and remaining prerequisites are reconciled below.

## Next TEST hosting task — release review package, 9 October 2026

The owner redirected the stale PR #12 request to the open draft PR #18. Entry checkout, remote branch and PR head all matched `33075090a1fa601447b9b830d79e8426c4ff50c4` on `feat/aws-test-scan-review-2026-10-09`; the tree was clean and main `28dec686f24ff18f6f99ec183ffd82375f4dec99` was an ancestor. PR #12 is already merged/closed. This continuation changes documentation only on PR #18, which remains unmerged. Its new final-SHA CI results belong in the PR, not a self-recording commit.

### Quota access and source/evidence inventory

The current managed environment reports current readiness observations but **no configured outbound identities, secret bindings or runtime variables**. No already authorized AWS operator connection is available. No AWS call was attempted, and current request status and total/unreserved concurrency remain **unverified**. Use the three-call [CloudShell preflight](#quota-history-and-current-read-only-cloudshell-preflight) below: STS, the exact existing quota request and Lambda account settings, all in account `418638389566` / `ap-southeast-1`. Preserve its timestamped output; a historical 1000/1000 or CASE_OPENED is not a live result. Require **at least 102 unreserved before reserving 2**, regardless of request status. No quota resubmission or identity setup is part of this task.

All canonical hosting/runtime operators, templates, workflow and regression owners are present. All **57 retained historical hosting source entries** were rehashed against `hosting-source.json`; they match. The old Mac operator remains data only and must not be resumed. The current backend compatibility check passes against original image source `33d124fcd59ffd3f9cb30d645660bdad99a21278`, contract SHA-256 `c7806c37e0f726733a66820cfbf33197cfc2a583d5acabc58d2030ccfb97bd5f`.

The retained release ZIP for run 37743179778 rehashes to `530ae9efe1a49d88ae3408a7b104c573883a1892121cc5c63f731243bc290b51`; authenticated metadata still reports artifact 11536680863 unexpired and that run successful at `28dec686…`. It is historical release evidence, **not a release for this draft or its eventual merge**. Runtime artifact 11528371887 remains unexpired in authenticated metadata with its original checksum/source below. The local `/workspace/work/hosting-prep/runtime.zip` is a **zero-byte download placeholder**, not verified evidence; extracted receipts remain present. Preserve it, but do not consume or repackage it as the authenticated archive. The later operator must download and verify the exact original runtime artifact; if unavailable, recover the original uploaded ZIP and verify its pin rather than rerun the proof. This task does not reassert a new runtime execution.

### Exact bundle and execution gates

| Required input/gate | Review requirement for the next separately authorized task |
| --- | --- |
| Operator/release source | Owner merges the final reviewed PR #18, then record the resulting full main SHA and complete main CI. Recheck live main before each phase; stop on advancement. Draft-head CI does not authorize deployment. |
| Immutable frontend | Separately authorize `aws-test-hosting.yml` mode `release` on that exact main, other inputs blank; inspect shared AWS queue without approving unrelated image jobs. Require complete frontend/backend CI, release run/attempt/artifact ID/ZIP digest, `release.json`, source inventory and dependency lock, API mode, base `/`, empty API base URL (same origin), build log and PWA evidence. No local build substitutes for this artifact. Replacement artifact identifiers are pending, not invented. |
| Backend image | Keep `sha256:861837230551824fdf37f868def500ca14abdbe489583f60ddacee932451eb5a`, original source `33d124fcd59ffd3f9cb30d645660bdad99a21278`, build 37584327992/attempt 1/artifact 11467134068. Recheck every shipped app/migration/dependency file against the image contract; no rebuild or provenance reassignment. |
| Current security acceptance | Authenticate the actual owner-merged approval and exact record. Evaluate complete current findings and scan timestamp; recorded scan reaches 24 hours on **9 October 23:29:27 Singapore**. Read-only evaluation does not refresh it. If stale, stop for separate scan authorization; do not silently request one. Result must be `accepted_with_test_exception`, expiry **11 October 20:41:44 Singapore**, unchanged. Historical acceptance and runtime proof do not confer scan freshness. |
| Private runtime | Authenticate the existing exact-image run 37721383277/attempt 1/artifact 11528371887 and pinned ZIP, receipt/state and cleanup; keep its original operator source. No runtime rerun is required or authorized. |
| Authority and environment | Reconcile the already provisioned IAM stack/template `db07e3acdb29e4bae04f483122fc7e4a8c56c76640f5e42e72f4b6c169e180ba`, hosting OIDC role, CloudFormation service role and app boundary. Preserve `aws-test` main-only protection/reviewer and `AWS_HOSTING_ROLE_ARN`. Recheck exact permissions/readback in the later authorized operation; no provisioning replay or runtime-role expansion. |
| AWS readiness | Obtain current capacity >=102 unreserved, retained network/RDS/secret/Cognito metadata and existing Lambda ECR pull-policy coverage for `fitfinity-test-staff-api`. This task authorizes only the three quota-preflight reads; remaining live reads belong to later execution scope. |
| Change sets and recovery | Preserve one operation ID, exact release/operator SHA and latest completed evidence run. Review edge then app CREATE change sets separately with exact template/resource inventory/review tokens. Persist intents before writes; reconcile response loss/partial uploads without replaying uncertain writes. Failed public smoke cannot become acceptance. Rollback requires separate authorization and exact owned resources, retaining the frontend bucket and existing database/secrets/Cognito/Owner. |

### Smallest implementation scope

**No additional hosting implementation is currently identified as necessary for the first release.** PR #17 already supplied `hosting_operator.py`, `hosting_design.py`, `hosting_frontend.py`, `hosting_binding.py`, the dedicated authority template and protected workflow. PR #18 repairs the legitimate approval transition while preserving historical evidence and merged-owner enforcement. Reuse these owners; do not import the older Mac implementations or broaden the temporary runtime role.

The next task is a bounded release/evidence operation after owner review, not a new deployer: confirm merged source and CI; obtain the replacement API artifact; reconcile permissions/capacity, fresh exact scan acceptance and retained runtime proof; then present the concrete edge change set for separate execution approval. If these gates expose a reproducible implementation defect, scope a focused fix in the existing owner with its failure regression and full final-SHA CI before any write. Subsequent-release updates and populated-database restore remain outside this first-release scope. Live hosting, password/MFA/sign-in/refresh/sign-out and recovery acceptance remain pending.

## Exact scan re-review pending — 9 October 2026 (Singapore)

[Draft PR #18](https://github.com/LimYouSheng/FitfinityReact/pull/18) proposes this approval correction; it is not current image acceptance or deployment authority. The owner authorized preparation of the review after the bounded scan operation stopped on changed findings. The proposed policy retains approval ID `FITFINITY-TEST-2026-10-07-86183723`, exact image/provenance and expiry **11 October 2026, 20:41:44 Singapore**. Its timestamp is the proposal timestamp; the evaluator additionally requires LimYouSheng's actual merge of the referenced PR and exact equality with that merged record. The earlier PR #11 two-finding approval remains historical evidence; no historical receipt is rewritten. No evaluator, trust, permission, workflow or freshness rule is relaxed.

### Verified operational evidence

- Reviewed main remains `28dec686f24ff18f6f99ec183ffd82375f4dec99` (PR #17). Immutable release run **37743179778**, attempt 1, artifact **11536680863**, ZIP SHA-256 **`530ae9efe1a49d88ae3408a7b104c573883a1892121cc5c63f731243bc290b51`** remains available. No release build or completed runtime proof was repeated.
- CloudShell caller `arn:aws:iam::418638389566:user/fitfinity-deployer` was explicitly designated by the owner. Corrected v2 helper SHA-256 **`0a63734df90bdee6ba20d7b7362f22354b5f08df8af0dbbf57ed03a3bc027208`** uses this exact user's GetUser/STS identity and principal-policy simulation; CloudFormation actions are simulated against the stack resource. Older helper copies and failed simulation evidence remain retained, not replayed.
- IAM stack **`arn:aws:cloudformation:ap-southeast-1:418638389566:stack/fitfinity-test-github-hosting/b2cf46c0-c329-11f1-8df2-02fff9bcfa4b`** reached CREATE_COMPLETE. Change set **`arn:aws:cloudformation:ap-southeast-1:418638389566:changeSet/hosting-authority-28dec686-20261008/03ea5e3d-af77-42f4-972e-668b29e37f84`** had exactly three Add resources: the hosting role, CloudFormation service role and API boundary. All 41 recorded responses, exact template **`db07e3acdb29e4bae04f483122fc7e4a8c56c76640f5e42e72f4b6c169e180ba`**, trust, inline policies, boundary and attachments were independently reconciled. Success receipt: **8 October 23:06:40 Singapore**.
- IAM evidence ZIP SHA-256 **`79062cd0d11fb74548504043137c74c19c75faa1aea0ede1814640c807866a32`**; launch-check ZIP **`5e108922117df96b29ec3bb4663289184b525646d242c627c8bc7edb607f29a3`**. These are owner-uploaded CloudShell evidence, not GitHub workflow artifacts.
- Owner UI/copy readback confirms environment `aws-test` variable `AWS_HOSTING_ROLE_ARN=arn:aws:iam::418638389566:role/fitfinity-test-github-hosting`; screenshot shows no repository variable of that name. Integration variable APIs returned 403, so no independent API value-readback is claimed. Required reviewer, main-only deployment branch and immutable OIDC subject were separately read back unchanged. Automatic image triggering remains enabled.
- Exactly one recorded StartImageScan request was accepted at **8 October 23:29:26 Singapore** for the existing `sha256:861837230551824fdf37f868def500ca14abdbe489583f60ddacee932451eb5a` image. The fresh scan completed at **23:29:27**, with one complete findings page, no next token, and count HIGH=1. Manifest/config digest checks and the complete findings inventory passed. The remaining finding is unchanged in every recorded field: **CVE-2026-85091 / zlib / 1.3.dfsg+really1.3.1-1 / HIGH**. **CVE-2026-95619 / gcc-14 / 14.2.0-19** is no longer reported; do not infer a rebuilt or patched image.
- Scan ZIP SHA-256 **`2c123ef41f6f174d63e86276ff4030332d9b129e2c56bad5c30ce2d835163ed2`**; scan-launch ZIP **`b570ce3159c432b5f581bb0d77bc81b1beb2b08fb730dfdcf865e42c7b31d96b`**. The helper deliberately returned failure with `Findings changed: retain evidence and obtain review; do not dispatch acceptance`. Its STOP and intents are historical evidence, not a request to retry. Scan freshness ends **9 October 23:29:27 Singapore**; read-only evaluation does not refresh it. Another refresh is not authorized by this correction.

### Current review and historical acceptance bindings

The original two-finding approval is retained byte-for-byte in [private-runtime-accepted-approval.json](../backend/infrastructure/private-runtime-accepted-approval.json), SHA-256 `054c6f32f5ba8541d4c389da8fdabc85f6e9c0720a8f53924044da7531c42991`. Historical acceptance run 37613240855/artifact 11480831590 remains pinned to ZIP `34133cf9939ed03e4b35f01b05bc698c97308f273fbf0361e8e4f69d0ff35e01` and that original approval. The receipt is never compared to or rewritten as the new finding review.

Current operations read `image-test-approvals.json`, retain the same image/provenance/expiry, and require `ExistingImage.reviewed_approval` to authenticate LimYouSheng's merged PR, ancestry and exact merged record before collecting operational evidence. Every later mutation boundary still checks the collected current approval against local policy and the valid time window; complete fresh scan acceptance remains separate. The local reader and offline plan confer no merged-review authority. Historical runtime artifact pins and backend compatibility checks are unchanged. Eight transition regressions cover separate old/current bindings, owner review, tampering and time/scope boundaries.

### Source binding and next decision

**Do not merge this draft merely to resume the old hosting command.** Hosting authenticates the release run's source SHA and frontend manifest against the current operator/main SHA. Merging even this policy/documentation correction advances main, so release run **37743179778 cannot be consumed from the new main**. No source guard is bypassed, artifact relabeled, or local build substituted. A replacement GitHub-only frontend release from a separately reviewed new main would require separate authorization. The backend image is not rebuilt; its original source `33d124fcd59ffd3f9cb30d645660bdad99a21278`, build run 37584327992/attempt 1, candidate artifact 11467134068 and completed runtime proof remain unchanged.

After owner review/merge and explicit reconciliation of the new main/release plan, recheck scan freshness/exception expiry and the shared AWS queue before any authorized authenticated image acceptance. The evaluator must return `accepted_with_test_exception`, not a clean scan. Then revalidate runtime evidence, backend compatibility, environment metadata, ECR pull policy and Lambda capacity before a separately gated first hosting prepare. **No new acceptance run, hosting operation ID, edge change set or live deployment exists at this checkpoint.** Hosting execution/rollback remain unauthorized. Do not rerun the CloudShell IAM or scan helpers, erase evidence, widen permissions, approve unrelated image jobs or extend the exception.

## AWS-PRIVATE-RUNTIME-01 completed — 8 October 2026 (Singapore)

**Private-runtime proof and owned cleanup are accepted for the exact image below. Persistent application hosting, live user authentication and deployment/database recovery acceptance remain pending.** This reconciliation reads retained evidence; it performs no AWS operation and does not rerun the proof.

### Authenticated source and artifact record

- Reviewed operator/main: `087f744884f7ed0d3374aa8e4e2ba1e9ddbf3932`, PR #15 merge; authenticated remote main matched this checkpoint at reconciliation. Its feature `2d5e3dad28e3e5a17725b96f33916e8c4a256474` passed both required jobs in [run 37701169959](https://github.com/LimYouSheng/FitfinityReact/actions/runs/37701169959).
- [Runtime run 37721383277](https://github.com/LimYouSheng/FitfinityReact/actions/runs/37721383277), attempt **1**, used that operator SHA. Authenticated GitHub results: frontend job `113129576426`, backend `113129576724`, runtime `113140192276`, all successful. The diagnostic confirms `mode=run`, authentication/account/operator success.
- Runtime artifact `fitfinity-private-runtime-aa2b2e439c3943b3b425de90302833ab-37721383277-1`, ID **11528371887**, ZIP SHA-256 **`5d11866916b82ccfec8e33700465427606394d59e8cfa1d12aac2fc1a58f8296`**, 180733 bytes.
- Diagnostic artifact `fitfinity-runtime-diagnostic-37721383277-1`, ID **11528282139**, ZIP SHA-256 **`e8b064c823d5a95d387807108bb8277a87c34f29499c20e4d75ca4f7573d5b55`**, 285 bytes.
- Both user-uploaded ZIP byte counts/checksums independently match the authenticated GitHub artifact metadata and supplied expected hashes. Direct storage download returned Forbidden; that did not prevent verifying the uploaded bytes. Raw ZIPs, requests, responses, logs, receipt and state remain outside Git under `/workspace/work/hosting-prep/` and uploaded attachments. This document contains only bounded evidence references.
- Operation **`aa2b2e439c3943b3b425de90302833ab`**, operator revision `2026-10-07-private-runtime-1`; account `418638389566`, region `ap-southeast-1`, runtime-role session `fitfinity-runtime-37721383277-1`.
- Backend image **`sha256:861837230551824fdf37f868def500ca14abdbe489583f60ddacee932451eb5a`**, original image source **`33d124fcd59ffd3f9cb30d645660bdad99a21278`**. Original build `37584327992` / attempt 1 / artifact `11467134068` remains the build provenance. The operator/hosting/frontend commit must never replace this original image source.
- Reviewed template SHA-256 `4914d7b7709b6ce99c1f9623eb3b8f370d312888f8ba424e943d8d5e2e8611c2`; probe SHA-256 `bcd249e01cb8070aa14d5c1553d819f7a4e14389b0f06a89d9a4eccb03c413fa`. Both were independently recomputed from the reviewed canonical operator and compared with the saved template, receipt and state.

### Verified responses and cleanup

Receipt checkpoint equals saved state exactly. All four saved request payload hashes, nonce/action bindings, HTTP adapter bodies, Lambda StatusCode 200 without FunctionError, and persisted invocation results match. The existing canonical `validate_result` checks passed again offline against all four responses; no probe code or historical operator was executed by this evidence review.

| Evidence | Verified result |
| --- | --- |
| `fitfinity-test-runtime-a`, subnet `subnet-0a6ea67e00f370997` | Preflight and current-runtime responses passed |
| `fitfinity-test-runtime-b`, subnet `subnet-0fcdf32ab544f1207` | Preflight and current-runtime responses passed |
| Image contents / execution identity | 54 shipped source files and 33 locked dependencies verified in each response; original image revision/digest and non-root identity match |
| FastAPI in both subnets | Actual lifespan startup/shutdown; liveness 200, readiness 200, untrusted Host 400 |
| Database in both subnets | `fitfinity_app`, database `fitfinity`, TLSv1.3, `sslmode=verify-full`, PostgreSQL 17.11; read-only transaction and application health SELECTs; target revision `20260924_0006` |
| Managed auth and Cognito/JWKS | Exact managed auth-secret version, encryption/settings verified, 18 Cognito configuration checks, JWKS reachable with two keys in each runtime response |
| Capacity at proof | 1000 total / 1000 unreserved; this is recorded capacity, not a perpetual guarantee. Do not resubmit the existing quota request |
| Cloud write inventory | One temporary stack create, four synchronous Lambda invocations, one owned stack delete; no bootstrap, Owner creation or public release |
| Cleanup | Saved stack reached DELETE_COMPLETE; both function and execution-role reads reported absent; operator checked both exact log-group names absent. Delete intent/response and `temporary_cleanup_complete=true` persist |
| Final receipt | `accepted=true`, `aws_runtime_verified=true`, `temporary_cleanup_complete=true`; `application_deployed=false`, `live_authentication_accepted=false`, `owner_created=false` |

Proof collection began **11:57:29 Singapore** and completed **12:23:04.884777 Singapore**, 8 October 2026. Cleanup took the recorded wait until the owned stack and its resources were absent; do not shorten timeouts or infer a failure from that interval. The last persisted write is the acknowledged delete, not an unresolved action: `pending_write.response_received=true`, `delete_response_received=true`, `complete=true`.

Strict scan policy remains false: the exact image was accepted under TEST exception `FITFINITY-TEST-2026-10-07-86183723` for its two reviewed High findings. Expiry remains **11 October 2026, 20:41:44 Singapore**. Future hosting must recheck complete scan freshness and approval validity. The recorded 7 October 15:44:43 Singapore scan reaches 24 hours on **8 October 15:44:43 Singapore**; completed runtime evidence neither refreshes it nor extends/transfers the exception.

### Executed automation sequence and recovery contract

1. PR #15 corrected the exact immutable-ID trust subject and supported account-output guard. The earlier failed authentication run **37653771533** remains failed, with no collector execution/resources. The owner-provided provisioning/OIDC readbacks and the prepared trust-update procedure remain in the history below. Successful later authentication verifies the repair operationally; this task does not assert a separately inspected CloudFormation change-set execution receipt.
2. [Collection run 37714088812](https://github.com/LimYouSheng/FitfinityReact/actions/runs/37714088812) passed at the same operator SHA and operation ID. Uploaded receipt/state/log were checked: seven metadata checks passed, checkpoint matched, no cloud writes; `metadata_verified_runtime_pending`, runtime/cleanup/application/live-auth flags false. Its separate diagnostic confirms `mode=collect`. Collection was not application deployment.
3. Runtime run **37721383277**, attempt 1, selected `run` on `main`, same operation ID, no resume run. The protected workflow first passed complete frontend/backend CI, obtained runtime OIDC credentials, checked account output, then invoked the canonical operator. The following are normalized representations of the executed workflow entry points, not claims that the owner typed CLI dispatch commands:

```bash
python3 backend/infrastructure/deploy.py private-runtime --mode collect \
  --operation-id aa2b2e439c3943b3b425de90302833ab \
  --directory "$RUNNER_TEMP/private-runtime"
# Separate later run, fresh runner/evidence directory:
python3 backend/infrastructure/deploy.py private-runtime --mode run \
  --operation-id aa2b2e439c3943b3b425de90302833ab \
  --directory "$RUNNER_TEMP/private-runtime"
```

4. Runtime verified authenticated original candidate/approval evidence, exact reviewed main/source, account/capacity, fresh image scan and retained network/RDS/Cognito/secret metadata; then verified existing Lambda ECR pull policy. It persisted create intent before creating the exact tagged six-resource stack, reconciled template/physical identities and invoked `preflight` in both subnets before `current-runtime` in both. Invocation arguments were exact function name, `RequestResponse`, private `fileb://` payload, `raw-in-base64-out`, and a unique response path; the canonical owner validates transport and function result separately.
5. After proof, it rechecked retained secret metadata, persisted delete intent and deleted only the owned stack; exact-name absence checks completed before final acceptance. Requests/results and diagnostics were uploaded separately with strict artifact requirements.

For an interrupted future operation, preserve the operation ID and previous completed run/artifact. The existing `--resume-run` path authenticates the exact workflow/run/attempt/artifact/checksum and operator commit before restoring state; uncertain writes are reconciled against owned resources, never blindly replayed. Cleanup requires a recorded owned create intent and matching template/tags/physical inventory. Changed operator SHA, unknown resources, missing artifact, drift or unverifiable invocation results stop for review. These recovery contracts are prepared/tested behavior, **not a claim that an interrupted deployment or database restore was exercised in this successful run**. No rerun/cleanup of this completed operation is needed.

## AWS-TEST-HOSTING-01 — canonical first-release preparation, 8 October 2026

**Hosting automation is prepared; persistent deployment, actual sign-in and live recovery acceptance are pending.** The missing-source blocker from PR #16 is resolved. PR #16 merged as `e6b4a13b003ade5e7ee49032d5ca3fe95b1d28a9`, retaining feature `a4682479f09e36edc63af804bee4057539f6b9dc`. Its [main run 37732930429](https://github.com/LimYouSheng/FitfinityReact/actions/runs/37732930429) passed both required verification jobs and build/Pages publication. Its image job is waiting for approval; this task did not approve it or rerun the workflow.

### Recovered source and explicit pin reconciliation

The supplied `Fitfinity_AWS_Test_Login_2026-10-06.sh` passed SHA-256 **`1acfe7808c1781470224812c8eceede96c90cc4466c499e096961bae68784af0`**. Its decoded payload passed **`a65cd0069c69423822b2a4cd0048b9654894e57f0b7cc190914fd1061a664d30`**, safe-path checks, the exact **57-entry embedded manifest**, and revision **`2026-10-06-test-login-1`**. The historical shell/entry point was never executed. Its 58 decoded files (manifest included), original pins, receipts, failed attempts and test logs remain outside Git at `/workspace/work/hosting-impl/recovered/`. [hosting-source.json](../backend/infrastructure/hosting-source.json) retains only immutable source hashes; historical 152 composed/25 CLI checks are provenance, not new acceptance.

The historical owner pinned frontend/main `d2e8a4b7e44c1554b1f31b5337b87014e6446fdf` and image `sha256:353907f09c208b35fd5160266e4f92da39e3db4e3a17e61236fdcd430ae15dc1`. These remain historical. The adaptation consumes a **fresh release at the exact reviewed operator main SHA**, verifies every tracked source/index blob, builds API mode with same-origin `/` configuration and runs the canonical PWA verifier. It separately pins the accepted `86183723…` image to original `33d124f…` image source and authenticates runtime run **37721383277** / artifact **11528371887** / exact ZIP checksum above. Every shipped backend application/migration/dependency file must still match the accepted image contract. A later incompatible application change fails closed; changing a documentation or operator SHA cannot relabel the image.

### Canonical owners, permissions and artifact flow

| Owner | Implemented responsibility |
| --- | --- |
| [hosting_operator.py](../backend/infrastructure/hosting_operator.py), via `deploy.py hosting` | `plan`, `prepare`, `execute`, `verify`, `rollback`; exact owned change sets, durable intents before writes, readback, conditional uploads, public smoke and first-release teardown |
| [hosting_design.py](../backend/infrastructure/hosting_design.py) | Recovered 20-resource Singapore app and one-resource edge-WAF templates; private versioned retained S3, CloudFront OAC, uncached API routes, pinned Lambda/version/alias, two-concurrency cap, two WAF ACLs and alarm |
| [hosting_frontend.py](../backend/infrastructure/hosting_frontend.py) | Build once in an isolated Git archive using existing Node 24/dependencies and canonical API/PWA scripts. Export `artifact/frontend/*` plus `release.json`: source inventory/hash, exact source SHA, configuration, lock/Node evidence, PWA result, backend compatibility, file hashes/sizes/MIME/cache settings |
| [hosting_binding.py](../backend/infrastructure/hosting_binding.py) | Authenticate GitHub repository/main/manual workflow/source/run/attempt/artifact metadata and ZIP checksum; reject expired/ambiguous/unsafe inputs; recover only the same operation and operator revision. Reuse canonical image approval, fresh scan, metadata and ECR-policy checks |
| [test-github-hosting-role.json](../backend/infrastructure/test-github-hosting-role.json) | **Proposed, unprovisioned** `fitfinity-test-github-hosting`, separate `fitfinity-test-hosting-cloudformation` service role and `fitfinity-test-hosting-api-boundary`. Temporary-runtime authority is unchanged |
| [aws-test-hosting.yml](../.github/workflows/aws-test-hosting.yml) | Manual main-only workflow with complete frontend/backend prerequisites, protected `aws-test` hosting job, exact hosting-role/account guard, serialized AWS operations, strict release/state uploads and separate always-retained diagnostics |

The operator role can read the retained metadata, inspect owned hosting resources, create/execute/delete only the two named hosting stacks/change sets, pass only the dedicated CloudFormation role and conditionally upload only the owned frontend bucket's `releases/*` keys. It cannot read secret values, bootstrap users, publish/scan backend images or invoke the temporary runtime probes. The CloudFormation role creates the first-release resources; IAM creation is restricted to exact `fitfinity-test-hosting-api` with the exact boundary, and PassRole is restricted to Lambda. The boundary equals the generated application policy: exact app/auth secrets at AWSCURRENT, function logs and VPC ENI permissions with the existing function-origin deny.

Generated CloudFront/API IDs require account/region-scoped resource patterns; CloudFront distribution/policy/OAC creation and selected read/list actions require `Resource: "*"`; distribution creation also requires exact Application/Environment/Purpose request tags. Actions, resource-level support and condition keys were checked against the [official public AWS service authorization catalog](https://servicereference.us-east-1.amazonaws.com/v1/cloudfront/cloudfront.json), covering all 16 service namespaces in the proposed policy. This is documentation validation, not a live policy simulation. These permissions are isolated in the service role where applicable, not added to the temporary runtime role. Review the complete proposed policy before provisioning. Hosting policy correctness is tested offline; actual IAM provisioning and live permission acceptance remain separate. Existing ECR Lambda pull policy must already cover `fitfinity-test-staff-api`; the operator never changes it.

Application resources remain in **ap-southeast-1**; CloudFront WAF control-plane resources remain in **us-east-1**. Database, secrets, Cognito pool and existing Owner are referenced, never created or modified. No bootstrap replay, invitation resend, migration or account-management operation is part of this owner.

### Implemented commands and future reviewed execution order

The offline command below writes a plan/receipt and edge template outside the checkout; it requires no AWS identity. It was exercised during implementation. The build entry point is also local and has no AWS authority; use a clean exact checkout and a new output directory:

```bash
python3 backend/infrastructure/deploy.py hosting --mode plan \
  --operation-id 11111111111111111111111111111111 \
  --directory /tmp/fitfinity-hosting-plan-NEW
python3 backend/infrastructure/hosting_frontend.py \
  --revision "$(git rev-parse HEAD)" --directory /tmp/fitfinity-hosting-release-NEW
```

The local artifact is build evidence only. Live hosting accepts an authenticated **successful manual release-mode Actions artifact** from the same reviewed main SHA, after complete frontend/backend CI. It does not accept arbitrary local ZIPs or rebuild frontend bytes during deployment.

The following dispatch commands are **prepared future procedures, not executed in this task or authorized by this document**. Before use: YS reviews/merges the PR, separately provisions/reviews the proposed dedicated hosting authority, configures `AWS_HOSTING_ROLE_ARN=arn:aws:iam::418638389566:role/fitfinity-test-github-hosting`, and confirms protected `aws-test` main-only deployment and required-reviewer settings. Confirm exact reviewed main, unchanged backend compatibility, artifact access, capacity and ECR pull policy. Every non-rollback live operation rechecks existing metadata, complete scan freshness and exact unexpired TEST approval. No scan request, quota request or approval extension is automated here.

```bash
# 1. Build immutable frontend release on the reviewed main SHA; no AWS credentials.
gh workflow run aws-test-hosting.yml --repo LimYouSheng/FitfinityReact \
  --ref main -f mode=release
# Inspect its successful full CI, release.json, build log and artifact SHA-256.
release_run=REPLACE_WITH_SUCCESSFUL_RELEASE_RUN_ID
operation_id="$(python3 -c 'import uuid; print(uuid.uuid4().hex)')"

# 2. Prepare only the edge CREATE change set. No change-set execution.
gh workflow run aws-test-hosting.yml --repo LimYouSheng/FitfinityReact \
  --ref main -f mode=prepare -f operation_id="$operation_id" -f release_run="$release_run"

# 3. Download this completed run; inspect hosting/state.json, edge-template.json,
# reviewed_changes, change-set/stack IDs, template hash and exact review_token.
prepared_run=REPLACE_WITH_COMPLETED_PREPARE_RUN_ID
gh run download "$prepared_run" --repo LimYouSheng/FitfinityReact --dir hosting-evidence
review_token=REPLACE_WITH_EXACT_REVIEW_TOKEN
# Only after explicit review, execute that exact edge change set.
gh workflow run aws-test-hosting.yml --repo LimYouSheng/FitfinityReact \
  --ref main -f mode=execute -f operation_id="$operation_id" \
  -f release_run="$release_run" -f resume_run="$prepared_run" -f review_token="$review_token"

# 4. Use the completed edge-execute run to prepare the Singapore app change set.
edge_run=REPLACE_WITH_COMPLETED_EDGE_EXECUTE_RUN_ID
gh workflow run aws-test-hosting.yml --repo LimYouSheng/FitfinityReact \
  --ref main -f mode=prepare -f operation_id="$operation_id" \
  -f release_run="$release_run" -f resume_run="$edge_run"
# Review the new app template/changes and its NEW review_token. Repeat step 3
# with this app-prepare run/token. Execution uploads the verified release and
# checks live configuration plus public frontend/API smoke before acceptance.
```

Each review token binds operation ID, stack ID, change-set ID and template hash. The owner accepts only the exact declared Add-only resource inventory, never Update/Import/replacement. Edge execution stops before preparing the app. App preparation stops before execution. The reviewer can inspect concrete changes between steps. API startup/public readiness may use the existing application read-only health SELECT; no database bootstrap is called. Success reports application deployment separately from human authentication, which remains false.

### Recovery and scoped first-release rollback

Use the **latest completed hosting run**, including a failed run with retained state, the same operation ID, release run, operator commit and current phase's review token. Artifact identity/checksum/source validation runs before state is adopted. A different release, operator SHA, image or operation fails closed. No automatic migration of recovery state across commits is provided.

- Lost create response: reconcile the exact tagged owned stack/change set and template; never recreate a missing stack with a prior intent.
- Lost execute response: resume an in-progress/completed owned stack. If execution is still AVAILABLE after an uncertain request, stop for receipt/provider review instead of blindly replaying it.
- Partial or response-lost upload: HEAD each immutable key, verify checksum/length/MIME/cache/encryption, skip matching objects and conditionally create missing keys with `If-None-Match: *`. A foreign or different object stops; it is never overwritten.
- Failed configuration/public smoke: preserve state and the failed receipt; do not mark deployment accepted. Resume `execute` with the app token after diagnosing the failure, or separately authorize rollback.
- `verify` rechecks a completed deployment and public bytes/API behavior. It does not certify actual password setup, MFA, sign-in, refresh or sign-out.

```bash
latest_run=REPLACE_WITH_COMPLETED_HOSTING_RUN_ID
gh workflow run aws-test-hosting.yml --repo LimYouSheng/FitfinityReact \
  --ref main -f mode=verify -f operation_id="$operation_id" \
  -f release_run="$release_run" -f resume_run="$latest_run"
# Separately reviewed first-release rollback only:
gh workflow run aws-test-hosting.yml --repo LimYouSheng/FitfinityReact \
  --ref main -f mode=rollback -f operation_id="$operation_id" -f resume_run="$latest_run"
```

Rollback authenticates owned state and hosting identity, checks stack tags/service role/template/resource identities, and removes the **app stack then edge stack**. Delete response loss is reconciled without blind replay. The frontend bucket and uploaded versions remain retained; database, secrets, Cognito and Owner remain untouched. Rollback deliberately does not require a still-current image approval or a fresh frontend download. It is first-release teardown, not a populated-database restore or a subsequent-release version switch. Any unowned/drifted resource or uncertain non-progressing delete stops for review.

Operation state and partial evidence use `fitfinity-hosting-<operation>-<run>-<attempt>`; diagnostics are separate. Release bytes use `fitfinity-hosting-release-<run>-<attempt>`, and build logs use `fitfinity-hosting-build-<run>-<attempt>`. Preserve failed artifacts. Protected environment approval is required for live phases; no script is an authorization to dispatch them.

The TEST exception still expires **11 October 2026, 20:41:44 Singapore**. Completed runtime proof neither refreshes scans nor extends this expiry. The registry's general `deploy` remains refused and `automatic_release_ready=false`; this separate manual first-release owner does not establish full release, live authentication or recovery acceptance.


## AWS-IMAGE-ACCEPT-01 — existing candidate acceptance, 7 October 2026

Implementation was merged in [PR #10](https://github.com/LimYouSheng/FitfinityReact/pull/10) as `33d124fcd59ffd3f9cb30d645660bdad99a21278`; both final feature CI jobs passed in [run 37580783214](https://github.com/LimYouSheng/FitfinityReact/actions/runs/37580783214). Live evaluation was subsequently authorized separately and passed for the exact candidate below; it was not executed by the implementation or documentation tasks. This adds a separate security evaluation, not deployment or a replacement successful result for an old failed workflow. `deploy.py deploy` still refuses incomplete full deployment. Existing build-and-scan remains strict and unchanged for candidates without an applicable reviewed approval.

### Current accepted TEST candidate — 86183723

At **7 October 2026, 16:12:01 Singapore**, authenticated GitHub evidence for [main run 37584327992](https://github.com/LimYouSheng/FitfinityReact/actions/runs/37584327992), attempt `1`, was independently checked. Frontend/backend/build/Pages passed; `image / image` and the overall run failed strict policy. This failed run remains failed.

- Artifact `fitfinity-image-candidate-37584327992-1`, ID `11467134068`, was unexpired and bound to this main run. Downloaded ZIP SHA256 exactly matches metadata and the requested `73133f313b7a7c818c96ac516e5c9bcf5b85a824e6307e27056a59a44ed619ef`.
- Original source revision `33d124fcd59ffd3f9cb30d645660bdad99a21278`; all **160** backend Git objects match the receipt manifest; source SHA256 `551d454da9fa66fffec60a9fd1a39e083c117e02e392537acc3ed1e458986b97`.
- Exact TEST identity: account `418638389566`, region `ap-southeast-1`, repository `fitfinity-test-api`, environment `test`; digest `sha256:861837230551824fdf37f868def500ca14abdbe489583f60ddacee932451eb5a`; config digest `sha256:e69dfb02ab32409dc63741bdf49e6eade287d19e250953eb69c952b5ebbaf1a1`. Receipt records build/publication complete, `candidate_ready=false`, `scan_policy_passed=false`.
- Recorded scan COMPLETE at **7 October 2026, 15:44:43 Singapore** (`2026-10-07T07:44:43Z`), **27 minutes 18 seconds old at review**: one complete page, matching HIGH count 2, no continuation token. This is dated artifact evidence, not a fresh live ECR scan; no claim that either vulnerability is fixed, unexploitable or lacks a fix.

| Severity | Finding | Package | Exact version |
| --- | --- | --- | --- |
| HIGH | CVE-2026-85091 | zlib | `1.3.dfsg+really1.3.1-1` |
| HIGH | CVE-2026-95619 | gcc-14 | `14.2.0-19` |

[PR #11](https://github.com/LimYouSheng/FitfinityReact/pull/11) was merged by `LimYouSheng` as `c66acf9032b9bf7b9b71fcf118f375e8bb6e9fd1`, from final feature `1689f84970eee2608ff526a34597e30592f6538e`. Final [PR CI 37598689305](https://github.com/LimYouSheng/FitfinityReact/actions/runs/37598689305) passed both required jobs. Approval `FITFINITY-TEST-2026-10-07-86183723` is now reviewed and merged, with unchanged `approved_at=2026-10-07T16:12:01+08:00` and expiry `2026-10-11T20:41:44+08:00`. The limited TEST exception permits controlled development/deployment validation while these two findings remain open; production is excluded. It does not authorize deployment or establish runtime acceptance.

The evaluator verified the merged exact dedicated approval. Wrong digest, changed/disappeared findings, expired/revoked entries or unmerged/unauthorized review remain blocked. This is not renewal or transfer of the historical `353907f…` exception.

The completed **Evaluate an existing TEST image without publication** run used these original candidate identifiers, not the frontend repair or policy merge as image provenance:

```text
Branch: main
digest: sha256:861837230551824fdf37f868def500ca14abdbe489583f60ddacee932451eb5a
build_run: 37584327992
build_attempt: 1
artifact_id: 11467134068
approval_id: FITFINITY-TEST-2026-10-07-86183723
```

#### Verified live acceptance receipt

- [Run 37613240855](https://github.com/LimYouSheng/FitfinityReact/actions/runs/37613240855), attempt `1`, completed successfully at policy revision `c66acf9032b9bf7b9b71fcf118f375e8bb6e9fd1`.
- Authenticated artifact `fitfinity-image-acceptance-37613240855-1`, ID `11480831590`; downloaded ZIP SHA256 **`34133cf9939ed03e4b35f01b05bc698c97308f273fbf0361e8e4f69d0ff35e01`** matches both GitHub metadata and the supplied checkpoint. ZIP contains `fitfinity-image-acceptance.json` and `.log`; receipt fields and all 160 policy-revision source hashes were independently checked against exact main.
- Created `2026-10-07T11:54:33.956262+00:00` (**7 October 2026, 19:54:33.956262 Singapore**); account `418638389566`, region `ap-southeast-1`, assumed role `fitfinity-test-github-image`, session `fitfinity-image-accept-37613240855-1`.
- `result=accepted_with_test_exception`, `image_security_accepted=true`, **`scan_policy_passed=false`**. COMPLETE scan evidence retains exactly the two HIGH findings above. `application_deployed=false`, `live_authentication_accepted=false`, `cloud_write_attempts=[]`.
- Exact image remains `sha256:861837230551824fdf37f868def500ca14abdbe489583f60ddacee932451eb5a`. Original source `33d124fcd59ffd3f9cb30d645660bdad99a21278`, build `37584327992`, attempt `1`, artifact `11467134068` and its checksum remain unchanged. Approval is `FITFINITY-TEST-2026-10-07-86183723`, referenced to PR #11, expiring **11 October 2026, 20:41:44 Singapore**. No extension or transfer.

Separately, [post-merge run 37612539030](https://github.com/LimYouSheng/FitfinityReact/actions/runs/37612539030) passed frontend/backend/build/Pages but failed `image / image`. Its completed image log says `Image blocked: critical, high or unclassified findings; no automatic exception`. This strict build result remains failed and is not replaced by the acceptance receipt. Do not switch the approval to that run's new image. This documentation task made no AWS calls, dispatch or scan request; it verified retained authenticated evidence.

### Historical candidate review — ca6545a, no approval granted

Reviewed retained GitHub artifact at **7 October 2026, 14:10:50 Singapore** (06:10:50 UTC): [main run 37570932661](https://github.com/LimYouSheng/FitfinityReact/actions/runs/37570932661), artifact `fitfinity-image-candidate-37570932661-1`, ID `11462505272`. Main frontend/backend/build/Pages passed; `image / image` failed strict policy and remains failed.

- Source/build revision: `40e8bb36868958e56813e2daa27c6ff074b9aced`; source manifest SHA256 `8cf5b01850fa77f4df3ef434a09d9c2fed6ef47394beef46223fd376ecaa7f5a`. All 157 backend inputs independently match that Git revision.
- Candidate: `sha256:ca6545a53aecb57b7120da79ff20a23d49b4b549aa57704ac54c8ac73f979b6a`, repository `418638389566.dkr.ecr.ap-southeast-1.amazonaws.com/fitfinity-test-api`; config digest `sha256:be6566b8e44dc9e6989a9e171f58e4bc3b30ea625a7808ce90295247dd86dfe0`.
- Downloaded artifact ZIP SHA256: `b9d0bd32ab6eaf65721ffd2e8a636e378f7bbc265b8e5b62c2de831ee62832f9`. Original run/attempt: `37570932661` / `1`. The receipt records a completed runtime build and publication, but `candidate_ready=false`, `scan_policy_passed=false`.
- Recorded scan: COMPLETE at `2026-10-07T05:04:06Z` (13:04:06 Singapore), **1 hour 6 minutes 44 seconds old at review**. The single complete page has matching counts, exactly two High findings and no continuation token. This is dated artifact evidence, **not a fresh live scan**. A later evaluation must read current ECR evidence and enforce its own 24-hour window.

| Severity | Finding | Package | Version |
| --- | --- | --- | --- |
| HIGH | CVE-2026-85091 | zlib | `1.3.dfsg+really1.3.1-1` |
| HIGH | CVE-2026-95619 | gcc-14 | `14.2.0-19` |

Neither finding nor this digest is approved here. Remaining requirements: explicit YS risk review with reason, approval time/expiry and exact provenance/finding scope, a reviewed main policy commit, then a separately authorized main Actions evaluation using fresh complete ECR evidence. A disappeared finding requires new exact review; it is not evidence that a package was fixed.

The historical exception `FITFINITY-TEST-2026-10-04-UNFIXED` and review `FITFINITY-TEST-2026-10-05-SCAN-REVIEW` apply only to `sha256:353907f09c208b35fd5160266e4f92da39e3db4e3a17e61236fdcd430ae15dc1`, expiring **11 October 2026, 20:41:44 Singapore**. They are not transferred, extended or reconstructed into this new format. Missing historical approval details are not inferred. Historical operators retain their original scope and receipts below.

### Canonical approval format and authority

[image-test-approvals.json](../backend/infrastructure/image-test-approvals.json) is the sole policy file: version `1`, list `approvals`. It contains the **YS-merged PR #11 approval**, verified by the live acceptance receipt above. An Actions input selects only an existing approval ID; no JSON receipt or workflow text can approve itself. Each entry requires:

- `id`, `status` (`approved` or `revoked`), `approval_reference` (the exact repository PR URL), `approver` (`LimYouSheng`), nonempty `reason`, timezone-qualified `approved_at` and `expires_at`.
- Exact `account`, `region`, `repository`, `environment` (`test` only), `image_digest`.
- `findings`: an exact, duplicate-free list of objects with only `cve`, `package`, `version`, `severity` (`HIGH`). No wildcard, severity-wide waiver, new finding or changed/disappeared identity is accepted. Critical and unclassified findings are always blocked.
- `provenance`: exact `source_revision`, `source_sha256`, integer `run_id`, `run_attempt`, `artifact_id`, and `artifact_sha256` (plain SHA256 hex of the trusted ZIP).

Approval publication is an explicit risk decision: prepare a dedicated review PR with the exact entry, set `approval_reference` to that PR, and have **YS review and merge it**. The evaluator reads GitHub's merged PR record, requires `merged_by=LimYouSheng`, main in this repository, an ancestor merge commit, and the identical entry in that user-merged policy snapshot. Current main must still contain the identical active entry. Revoking/removing/changing it fails closed; a new authorization requires another explicit user-reviewed policy change. Do not backfill an approval on YS's behalf or automatically renew it. PR #10 introduced an empty policy; PR #11 subsequently supplied the separate exact entry and was merged by YS.

The original candidate is downloaded directly from GitHub's authenticated artifact API, not accepted from a caller-supplied JSON file. The evaluator verifies repository/main/event/workflow/run attempt, both successful required build-source CI jobs, the image job, immutable artifact identity and checksum, original Git source manifest and the live ECR manifest/config digest. Approval-policy revision is recorded separately from original source/build revision. An approval-only commit therefore does not rebuild or select another image.

### Command and Actions usage after review/merge

Use the manual **Evaluate an existing TEST image without publication** workflow, [aws-image-accept.yml](../.github/workflows/aws-image-accept.yml), on **main**. Supply `digest`, `build_run`, `build_attempt`, `artifact_id`, and optionally an existing reviewed `approval_id`. Empty approval ID means strict policy, which blocks this current High-bearing candidate. The workflow runs full verification, uses the existing protected `aws-test` environment/exact image role with a **read-only session policy**, and retains `fitfinity-image-acceptance-<run>-<attempt>` including failures. No IAM/protection configuration is changed by this implementation.

The equivalent Actions-only command is:

```bash
python3 backend/infrastructure/deploy.py image-accept --actions \
  --digest "$IMAGE_DIGEST" --build-run "$BUILD_RUN" \
  --build-attempt "$BUILD_ATTEMPT" --artifact-id "$ARTIFACT_ID" \
  --approval-id "$APPROVAL_ID" --receipt "$RUNNER_TEMP/fitfinity-image-acceptance.json"
```

The command requires the clean exact main policy checkout and temporary Actions credentials; it is not a local-profile bypass. `gh` uses the workflow's read-only `GH_TOKEN` for this repository's run/artifact/PR reads. Existing-candidate AWS calls are limited to identity/repository/ownership/scanning configuration, manifest and scan reads. It never builds, logs into ECR, publishes, deploys or starts a scan. Missing/in-progress/stale scan evidence is a prerequisite failure; arrange a scan only through a separately authorized operation, then evaluate again.

Results are `strict_policy_passed`, `accepted_with_test_exception`, or `blocked`. Exception acceptance retains `scan_policy_passed=false`, complete scan pages/findings, exact approval and provenance; it sets only `image_security_accepted=true`. Application deployment and live authentication remain false. The old failed run is immutable history; this path creates a separate receipt for the reviewed digest. No live command occurred during implementation; the later independently authorized acceptance is recorded above.

## Purpose and evidence rules

Record the final working procedure while each result is fresh, then use it to implement client deployment automation. Keep this as the single AWS operations reference. The [Journey](FITFINITY_JOURNEY.md) remains the chronology and [Rules and Architecture](FITFINITY_RULES_AND_ARCHITECTURE.md) remains the implementation contract.

- **Native success:** a user-run receipt verifies the stated outcome. It does not verify unrelated stages.
- **User-reported success:** the Journey records the user's result, without a recovered detailed transcript.
- **Corrected implementation:** the final operator/source is retained with successful phase evidence. This does not mean every optional recovery branch executed.
- **Offline validation:** tests or CLI parsing/serialization passed, without establishing AWS success.
- **Pending:** implemented or planned, but the required live result has not passed.

The early receipts often contain phase results and write names, not every full argument vector. This document preserves their exact receipt identities, final operator hashes, canonical source owners and working call families. It does **not** invent missing shell history. Initial manual AWS account/IAM-user creation has no recovered successful command transcript. The initial ECR uploader filename was later reused for a different pinned image, so the currently retained file must not be misidentified as the original September 22 bytes. SDK calls inside a Lambda and actions performed internally by CloudFormation are owned by their source/templates, rather than presented as manually executed CLI commands.

**Do not replay the following history as a shell script.** Initial provisioning, one-time Owner creation, normal release and recovery are different operations. Existing guarded operators enforce those boundaries.

## AWS-HOSTING-PREFLIGHT-01 — current implementation and release prerequisites

This is a documentation/read-only preflight from exact main `c66acf9032b9bf7b9b71fcf118f375e8bb6e9fd1`, not hosting authorization.

| Owner / evidence | Implemented or historically accepted | Current limit |
| --- | --- | --- |
| [deployment-test.json](../backend/infrastructure/deployment-test.json) | September 25 registry of explicit bootstrap/review/probe/release/recovery stages | `accepted` flags describe recorded native history, not a live query. Owner/OIDC/image/runtime blockers are reconciled at the 8 October checkpoint; full release remains refused |
| [deploy.py](../backend/infrastructure/deploy.py) | Stage dispatch, metadata verification, image candidate and exact-image acceptance | `status` explicitly returns `automatic_release_ready=false`; `deploy` refuses full release. Metadata verification is not private runtime or hosting proof |
| [test-image-runtime.py](../backend/infrastructure/test-image-runtime.py) | Earlier image inspection owner | Still pins historical `efa53edd…`; it cannot establish runtime acceptance for `86183723…` |
| Dated October runtime operator/receipt | `Fitfinity_AWS_Current_Runtime_2026-10-04.1gdnm7o1.json` records private startup/health/shutdown, DB TLS, Cognito and cleanup in both subnets for `353907f…` | No private-runtime receipt found for newly accepted `86183723…`; image security acceptance is not runtime proof |
| Dated October hosting operator | `Fitfinity_AWS_Test_Login_2026-10-06.sh`, revision `2026-10-06-test-login-1`; 152 offline/25 CLI serialization checks and a native quota stop before writes | Retained external operator is not a merged repository hosting entry point. Its old source/image/frontend pins must not be bypassed or blindly resumed |
| GitHub image/verification roles | Checked-in `test-github-image-role.json` and `test-github-verification-role.json` implement their separate limited purposes | Neither policy grants `servicequotas:GetRequestedServiceQuotaChange` or `lambda:GetAccountSettings`; do not assume access or broaden IAM/workflows |

No authorized AWS operator connection is available in this coding session: current environment status exposes no outbound identities/secrets, and no operator connector is available. Credentials remain outside the coding environment. The historical preflight did not verify live quota/capacity. The authenticated October 8 runtime receipt now records total/unreserved 1000/1000; request approval remains distinct. Future execution rechecks actual capacity without resubmitting the request.

### Next concrete task: review the TEST release bundle and runtime/hosting operator

Before any separately authorized hosting execution, prepare and review one immutable bundle with:

1. **Reviewed source:** explicitly select an accepted clean full commit for the hosting operator/templates and frontend, with successful final frontend/backend CI. This preflight starts at `c66acf9…`; its eventual documentation merge must be adopted explicitly if used. Keep the image's original `33d124f…` build provenance separate and verify compatibility; never relabel it with a documentation/repair SHA.
2. **Frontend artifact:** identify its source, API-mode configuration, exact intended CloudFront origin/API contract, build/PWA receipt, file manifest and checksum. Historical manifest `b63c6c3f7eb59128a52bfcf6368301e7e3d9637a6edbd34d8ba5644b04fde70c` and saved 40-file native bundle belong to the older `d2e8a4b…` release. Main Pages success is demo hosting evidence, not this AWS API-mode artifact. No new hosting frontend artifact was built or verified here.
3. **Image and private runtime:** retain the exact accepted `86183723…` digest, original candidate artifact and live acceptance receipt. Recheck approval validity/freshness under separately authorized operations at execution time. The October 8 authenticated runtime evidence above supplies digest-bound startup/health/shutdown, database TLS/permissions, Cognito/JWKS and cleanup in both subnets; bind it to the hosting release without relabelling image source. Historical `353907f…` success alone is insufficient.
4. **Capacity and permissions:** retain recorded 1000/1000 runtime capacity and recheck it at future execution, distinguishing request status from applied capacity; first CREATE requires at least 102 unreserved before reserving 2. Review an explicitly authorized operator identity and exact required CloudFormation/S3/CloudFront/API Gateway/WAF/Lambda/IAM operations, with application resources in Singapore and edge WAF in `us-east-1`. Existing image/verification roles do not authorize hosting. Do not change IAM or replay bootstrap to compensate.
5. **Recovery and acceptance:** review ownership/Add-only change sets, reconciliation of interrupted writes, immutable uploads, protected database/retained bucket handling, application rollback and populated-data migration/restore plan before rollout. Temporary cleanup is not a restore rehearsal. Preserve the existing Owner; do not recreate or resend invitations. Public HTTPS/API bytes, first login/password setup/MFA, `/me`, refresh/sign-out and recovery still require separate live acceptance.

The immediate next action is to review the canonical hosting adaptation and prepare the authenticated release artifact described in AWS-TEST-HOSTING-01 above. Missing prerequisites block hosting execution. This task does not authorize those future AWS operations, dispatch, image rebuild, scan request or deployment.

## Historical deployment position — 6 October 2026

| Item | Accepted value / status |
| --- | --- |
| TEST account | `418638389566` |
| Application region / CLI profile | `ap-southeast-1` / `fitfinity-test` |
| Operator identity | `arn:aws:iam::418638389566:user/fitfinity-deployer` |
| Repository / accepted deployment commit | `LimYouSheng/FitfinityReact` / `d2e8a4b7e44c1554b1f31b5337b87014e6446fdf` |
| Historical accepted image | `sha256:353907f09c208b35fd5160266e4f92da39e3db4e3a17e61236fdcd430ae15dc1` |
| ECR repository | `418638389566.dkr.ecr.ap-southeast-1.amazonaws.com/fitfinity-test-api` |
| Image runtime | Accepted in both private subnets, with temporary cleanup complete |
| First Owner | Created and linked, independently verified, temporary cleanup complete |
| Frontend | Native API-mode build and PWA checks passed; 40 files, 516 source files verified |
| Frontend manifest | `b63c6c3f7eb59128a52bfcf6368301e7e3d9637a6edbd34d8ba5644b04fde70c` |
| First hosting deployment | Stopped before cloud writes on Lambda concurrency |
| Public URL / live login | Not yet accepted |
| Domain choice | AWS-generated CloudFront HTTPS address; client DNS not required for TEST |
| Full deployment automation | Not accepted; implement after complete release and recovery acceptance |

Latest deployment receipt: `Fitfinity_AWS_Test_Login_2026-10-06.9ai7qy3v.json`. Its cloud-write list is empty. Preserve its saved frontend/state; reuse requires an explicitly reviewed compatible release baseline, not automatic adoption by the new digest.

## Successful sequence since AWS work began

| Date (Singapore) | Stage | Final working owner / entry point | Accepted result |
| --- | --- | --- | --- |
| 22 Sep | Login and account preflight | `aws login --profile fitfinity-test`; `test-preflight.py` | Correct non-root identity and account/profile established |
| 22 Sep | Initial ECR publication | `test-image-publish.py`; `Fitfinity_AWS_Test_Image_2026-09-22.sh` | User-reported `UPLOAD PASSED`; remote image/configuration verified |
| 22 Sep | Foundation plan and execution/recovery | `test-foundation-plan.py`, `test-foundation-execute.py` | Private encrypted PostgreSQL, isolated network, forced TLS and protections verified |
| 22 Sep | Cognito | `test-cognito-execute.py` | Preserved Essentials pool and corrected confidential client verified |
| 22 Sep | Egress discovery and execution/recovery | `test-egress-preflight.py`, `test-egress-execute.py` | NAT configuration and host verification passed |
| 24 Sep | Private egress proof | `test-private-egress.py` | Both private subnets reached HTTPS/JWKS through the expected NAT IP; probe cleaned up |
| 25 Sep | Restricted database credentials/roles | `test-db-access.py` | Administrator/migrator/application TLS and role permissions verified; temporary resources removed |
| 25 Sep | Initial schema | `test-db-migrations.py` | Six migrations through `20260924_0006`, commit and independent runtime permissions verified; cleanup complete |
| 25 Sep | Authentication secret | `test-auth-secrets.py` | Secret initialized, managed runtime/crypto/Cognito/database proof passed; cleanup complete |
| 25 Sep | Canonical infrastructure consolidation | `deploy.py`, `deployment-test.json` | Earlier operators brought under one repository registry; full-release command remains blocked |
| 1 Oct | GitHub/AWS setup | `Fitfinity_AWS_GitHub_Setup_2026-10-01.sh` | OIDC provider, separate image/verify roles and GitHub configuration read back successfully |
| 3–4 Oct | Current image build/publication/review | `release_image.py`, `aws-image.yml`, current-image operator | Current immutable image published; strict scan failed; scoped TEST exception and local runtime accepted |
| 5 Oct | Current-image AWS runtime | `Fitfinity_AWS_Current_Runtime_2026-10-04.sh` | Actual startup/health/shutdown, database TLS and Cognito connectivity in both subnets; cleanup complete |
| 6 Oct, 00:00 | First TEST Owner | `Fitfinity_AWS_First_Owner_2026-10-05.sh` | Selected identity and first Owner database link verified; no invitation sent |
| 6 Oct, 04:24 | First login frontend build/preflight | `Fitfinity_AWS_Test_Login_2026-10-06.sh` | Build passed; hosting stopped safely on account quota |
| 6 Oct, 04:37–04:41 | Quota request and readback | Service Quotas request/status calls below | Request submitted; `CASE_OPENED`; capacity still 10 |

Repository operator paths above are under `backend/infrastructure/`. Dated standalone operators are retained delivery artifacts; the October runtime/Owner/hosting implementations are not claimed to have been merged into that directory by this documentation change.

### Existing registry: reuse it

The current [deployment registry](../backend/infrastructure/deployment-test.json) and [dispatcher](../backend/infrastructure/deploy.py) already separate review, bootstrap, probe, release and recovery. The September acceptance flags are historical; some `release_blockers` text predates the October receipts. Update those fields with implementation/evidence changes, not by making this document bypass them.

This command displays registry status without provisioning:

```bash
python3 backend/infrastructure/deploy.py status
```

`deploy.py deploy` deliberately refuses an incomplete release. Keep that refusal until rollout, populated-data migration and recovery are implemented and accepted. Historical bootstrap scripts retain their original image/exception limits. Do not repin or alter time to make an old operator run again.

## Final working call patterns and prerequisites

### 1. CLI identity and command environment

Use explicit account/profile/region and JSON output. Current guarded collectors use these conventions:

```bash
export AWS_MAX_ATTEMPTS=2
export AWS_IGNORE_CONFIGURED_ENDPOINT_URLS=true

fitfinity_aws=(aws
  --profile fitfinity-test
  --region ap-southeast-1
  --output json
  --no-cli-pager
  --no-cli-auto-prompt
  --cli-error-format legacy
  --cli-connect-timeout 10
  --cli-read-timeout 30
)

"${fitfinity_aws[@]}" sts get-caller-identity
```

When login expires, the user runs `aws login --profile fitfinity-test`, then repeats STS. Do not retain an expiring browser authorization URL as a reusable login command. Do not use root credentials or silently choose the default profile.

Current guarded writes use `AWS_MAX_ATTEMPTS=1` and persisted write intent. Runtime invocation has its own reviewed 180-second read timeout. Preserve each owner's existing bounds; do not apply one timeout indiscriminately. No endpoint/TLS bypass or `--debug` logging. Cognito secret-bearing reads require the existing safe projection.

### 2. ECR image publication and scanning

The Journey records the initial uploader's working path as account/repository/image preflight → explicit account confirmation → repository creation if allowed → temporary Docker registry login → push → remote manifest/configuration verification. The retained later uploader and consolidated `test-image-publish.py` instead require the repository to exist and pin the later September 24 image. Preserve this version distinction. Docker uploads perform registry operations; a CLI `put-image` call is not a substitute for that complete path.

- CLI families: `ecr describe-repositories`, `get-login-password`, `batch-get-image`, `describe-image-scan-findings`; scan requests use `start-image-scan` only under the owning scan policy. Initial repository creation is recorded in the Journey's accepted upload history, but its original full CLI argument transcript was not recovered. Do not treat `create-repository` as a current release step.
- Initial accepted digest: `sha256:23895c4d53eb8f342cc25c121c0cc06a5246b97c76a3dbe0cdd893820865dc87`. This is historical, not the current deployment image.
- Current build owner: [release_image.py](../backend/infrastructure/release_image.py), invoked through `deploy.py image-candidate --actions --receipt <new-file>` by the reviewed GitHub workflow. It binds the merged commit, source manifest, unique tag, image digest and scan evidence.
- Current image workflow: run `37200182841`, attempt 1, for accepted commit `d2e8a4…`. Build/publication succeeded; strict security scan did not pass. ECR presence, local runtime and AWS runtime are separate acceptance steps.
- Do not change the old publisher's digest to publish new images. Keep temporary registry credentials outside source/receipts and remove them after use.

### 3. Foundation and RDS

Use the canonical `test-foundation.json` through the planner/executor. The planner creates and reviews a CREATE change set. The executor performs the reviewed execution or exact failed-stack recovery, then verifies resources.

- Calls include `cloudformation validate-template`, `create-change-set`, `describe-change-set`, `execute-change-set`, `describe-stacks`, `get-template`, `list-stack-resources` and `describe-stack-events`.
- The accepted recovery used `update-stack` with the corrected template and preserved stack identity, then `set-stack-policy` and `update-termination-protection` as required by the owner.
- Readback includes `rds describe-db-instances`, `describe-db-parameters`, safe secret metadata, and account/price checks.
- Correct TEST retention: **1 day**. The attempted 14-day value failed on this Free-plan account. This does not establish the provider's maximum or change the production 14-day target.
- Correct RDS JSON key: **`VpcSecurityGroups`**.
- Keep private/encrypted RDS, `rds.force_ssl=1`, deletion protection, stack termination protection, and the database replacement/deletion-denying policy.

Accepted receipt: `Fitfinity_AWS_Foundation_Execution_9n_nxqjg.json`. Do not run its planner again to duplicate the foundation.

### 4. Cognito

The corrected template/owner create or recover the pool/client and verify the exact configuration:

- `cloudformation validate-template`, `create-stack` or exact `update-stack` recovery, stack reads, `get-stack-policy`, `set-stack-policy` and termination protection.
- `cognito-idp describe-user-pool`, `list-user-pool-clients`, projected `describe-user-pool-client`, `get-user-pool-mfa-config`.
- Accepted tier: **ESSENTIALS**, required by the configured refresh-token rotation.
- Accepted client write attributes: **`email`, `name`**. Required email prevented the earlier `name`-only configuration. Require verification before an email change becomes effective; do not grant `email_verified` write access.
- Retain TOTP-only required MFA, invitation-only signup, token revocation/rotation and bounded token/challenge lifetimes.

Accepted receipt: `Fitfinity_AWS_Cognito_Execution_c3hufxxq.json`. This proves configuration, not human sign-in/MFA/recovery.

### 5. NAT and private egress

The discovery owner checks existing topology, offerings/AMI and pricing. The execution owner provisions or performs only its exact recorded recovery, then checks both AWS configuration and host state using SSM.

- Inventory: EC2 describe subnets, routes, gateways, instances, interfaces, groups, ACLs, images, instance offerings/types and volumes, as scoped by the owner.
- **`ec2 describe-nat-gateways` uses `--filter`**. The earlier plural `--filters` failed CLI parsing. Do not generalize that singular option to other EC2 describe commands.
- Template correction: remove unsupported **`Throughput`** from the instance block-device EBS mapping. Retain encrypted gp3/IOPS and verify actual volume throughput separately.
- Host proof: `ssm describe-instance-information`, `send-command`, `get-command-invocation`; `send-command` is a write and must retain its exact reviewed command payload.
- Private proof: temporary CloudFormation/Lambda probe in both app subnets, exact code/config readback, invocation result validation, then owned stack deletion.

Accepted NAT receipt: `Fitfinity_AWS_Egress_Execution_c87so5c2.json`. Independent connectivity/cleanup receipt: `Fitfinity_AWS_Private_Egress_Probe_9vu1hx5f.json`. NAT configuration alone was not the connectivity proof.

### 6. Restricted database access

`test-db-access.py` owns the retained credential containers, private temporary loader/functions, role initialization and independent permission proofs. Secret values stay inside AWS.

- CloudFormation validate/create or exact update/recovery, exact stack/resource/template reads, termination protection and owned cleanup.
- `secretsmanager describe-secret`, `get-resource-policy` inspect metadata. The private initializer owns secret retrieval/initialization under its scoped IAM.
- `lambda get-function`, IAM policy readback and absence checks precede `lambda invoke`; function response payload and action/nonce must be verified, not just CLI exit code.
- Final success receipt records one update, four invocations and one deletion. It verifies restricted-role setup, `verify-full` TLSv1.3, denied application DDL/escalation and temporary cleanup.
- Keep the corrected private source loader, numeric Lambda runtime identity checks, client lifecycle and RDS TLS verification. Do not return to the oversized environment-source approach or assume a particular textual Lambda username.

Accepted revision: `2026-09-25-rds-tls-verification`. Receipt: `Fitfinity_AWS_Database_Access_vle0p7n_.json` (the `(1)` upload contains the same accepted record).

### 7. Initial migrations

`test-db-migrations.py` uses the migration credential in a private function, then a separate application-credential proof. It applies six Alembic revisions through **`20260924_0006`** in the reviewed transaction, verifies the schema/grants/marker and distinguishes uncertain commit from confirmed commit followed by failed verification.

- Accepted schema: 44 tables, 24 functions, 113 triggers and 11 assessment definitions.
- Native receipt records temporary stack creation, four invocations and deletion; `migrations_applied`, `runtime_access_verified` and cleanup are true.
- DML/trigger verification is rolled back. No business records or Owner are created by this stage.
- This initial empty-schema runner is **not** an accepted populated-database upgrade/rollback solution.

Accepted receipt: `Fitfinity_AWS_Database_Migrations_s9zsj0qk.json`. The preceding subnet-query stop had no writes; its underlying CLI error was not established. Do not invent a correction or retry accepted migrations.

### 8. Authentication secret

`test-auth-secrets.py` creates a retained protected secret container and temporary private initialization/proof functions. The initializer obtains the accepted confidential client secret inside AWS and generates the encryption key. Its deterministic version token supports reconciliation after lost responses.

- CloudFormation creates the retained and temporary stacks; Lambda configuration/IAM readback precedes initialization/proof invocations.
- Metadata-only local reads use `describe-secret`/resource policy and projected Cognito reads. `GetSecretValue`/`PutSecretValue` occur only through the scoped private implementation, not a terminal command that prints credentials.
- The independent runtime function cannot write the secret. It validates the managed loader, 18 Cognito configuration checks, encryption round trip and READ ONLY database access.
- Existing versions, drift and unknown initialization outcomes stop for review; do not rotate/replace a key merely to obtain a successful rerun.

Accepted receipt: `Fitfinity_AWS_Auth_Secret_5ko3lsp2.json`. Secret/runtime/cleanup flags all passed. Temporary bootstrap origins are not the final portal origin.

### 9. GitHub OIDC and image pipeline

The final GitHub setup revision is `2026-10-01-variable-pagination`. The receipt `Fitfinity_AWS_GitHub_Setup_2026-10-01.2gmeXz.json` verifies nine accepted AWS/GitHub writes and readback with source unchanged.

- AWS: `iam create-open-id-connect-provider` when absent, `get-open-id-connect-provider`, scoped role stack creation, role/policy and stack readback.
- Provider: `token.actions.githubusercontent.com`; audience: `sts.amazonaws.com`.
- Recorded subject: `repo:LimYouSheng@141623519/FitfinityReact@1353173586:environment:aws-test`.
- Separate roles: `fitfinity-test-github-image` and `fitfinity-test-github-verify`. Image publication permissions do not authorize application deployment or secret access.
- GitHub companion operations create/reconcile the environment, main branch policy, protection and variables. Fully paginate variable discovery; do not replay those writes from a list of operation names.
- Setup's `oidc_assumption_tested=false` and `image_publication_enabled=false` describe that setup checkpoint. Later actual image build/publication evidence is separate and must not be retroactively attributed to setup.
- Required workflow remains feature → PR → complete CI → green required checks → merge → verify merged commit → build/deploy that commit. No force push or direct-main bypass.

### 10. Historical October 4 runtime and first Owner

The accepted October operators reuse the existing foundation and canonical application bootstrap. Their source is retained in the dated deliveries, rather than treated as already merged repository code.

- Runtime: exact-image private temporary stack → Lambda/IAM/network/secret-policy readback → controlled invocations in both subnets → actual FastAPI startup/health/shutdown and database/Cognito proofs → owned cleanup.
- Runtime receipt: `Fitfinity_AWS_Current_Runtime_2026-10-04.1gdnm7o1.json`; 54 shipped source files, 33 dependencies and 18 Cognito checks passed; temporary cleanup complete.
- Owner: existing-user lookup, explicit selected identity and hidden password prompts, guarded one-time `admin-create-user`, canonical database Owner link, independent identity/link verification, owned temporary cleanup.
- Working Cognito command constructor uses `--user-pool-id`, `--username`, `--user-attributes`, `--message-action SUPPRESS`, `--no-force-alias-creation` and **`--temporary-password file:///dev/stdin`**. Only the password travels through stdin; never log it or place it in argv/a local file. Use the owning implementation, not a shell pipeline containing a literal password.
- Owner receipt: `Fitfinity_AWS_First_Owner_2026-10-05.7m4s9dmk.json`; accepted revision `2026-10-05-first-owner-4`; link verified and cleanup complete. No invitation sent.
- Actual password setup, MFA, authenticated `/me`, refresh/reload, sign-out, password change and recovery remain user-owned acceptance.

### 11. First hosting: prepared, native completion pending

The TEST operator revision `2026-10-06-test-login-1` has 152 offline regressions and 25 real CLI localhost serialization checks. These are not cloud deployment proof.

Its reviewed path is edge WAF CREATE change set in `us-east-1` → application CREATE change set in Singapore → exact Add-only review → execution/readback → immutable conditional S3 uploads → configuration/public-byte/API smoke checks. The normal Lambda uses the accepted image, 512 MiB, 25 seconds and reserved concurrency **2**.

Future hosting calls include CloudFormation change-set operations, conditional `s3api put-object`/checksum `head-object`, CloudFront/S3/API Gateway/WAF/Lambda/IAM readbacks and scoped cleanup. They have not all been exercised by the quota-blocked native run. Do not place them in a list labelled fully successful deployment calls yet.

CloudFront supplies the AWS HTTPS hostname. API routes share that origin, API caching is disabled, and the application trusts that exact origin. The regional API and edge are WAF protected. Cleanup retains the private versioned frontend bucket; it is not a database restore rehearsal.

## Quota history and current read-only CloudShell preflight

| Field | Last observed value |
| --- | --- |
| Lambda total / unreserved concurrency | Historical hosting stop: `10` / `10`; authenticated 8 October runtime: `1000` / `1000` |
| Quota | `lambda` / `L-B99A9384` |
| First-release unreserved gate | At least `102`: reserve 2 while retaining AWS's 100 unreserved minimum |
| Rejected request | `DesiredValue=102`, `IllegalArgumentException`: must exceed default `1000.0` |
| Submitted request | `DesiredValue=1001`, initially `PENDING` |
| Request ID | `e57c2d28661842e593dc7f6543c0087eF7Cev008` |
| Historical status / support case (6 October) | `CASE_OPENED` / `179123267300687` |

The **102 capacity gate** and **1001 requested regional quota** serve different purposes. Fitfinity's function remains capped at 2. A case or an approval status alone is not applied capacity. Do not resubmit this request.

Run in an already authorized **AWS CloudShell** session for the TEST account. No local profile or exported credentials are required. The STS account guard stops before either quota read on an account mismatch. Capture request status separately from actual applied capacity; no output has been obtained in this task:

```bash
bash <<'SH'
set -euo pipefail
export AWS_MAX_ATTEMPTS=2
export AWS_IGNORE_CONFIGURED_ENDPOINT_URLS=true
fitfinity_aws=(aws
  --region ap-southeast-1
  --output json
  --no-cli-pager
  --no-cli-auto-prompt
  --cli-connect-timeout 10
  --cli-read-timeout 30
)
fitfinity_account="$("${fitfinity_aws[@]}" sts get-caller-identity --query Account --output text)"
if [ "$fitfinity_account" != 418638389566 ]; then
  printf 'STOP: expected TEST account 418638389566; got %s\n' "$fitfinity_account" >&2
  exit 1
fi
date -u +'Read time: %Y-%m-%dT%H:%M:%SZ'
printf 'Verified account %s; region ap-southeast-1\n' "$fitfinity_account"
"${fitfinity_aws[@]}" service-quotas get-requested-service-quota-change \
  --request-id e57c2d28661842e593dc7f6543c0087eF7Cev008 \
  --query 'RequestedQuota.{RequestId:Id,Service:ServiceCode,Quota:QuotaCode,Status:Status,Requested:DesiredValue,CaseId:CaseId}'
"${fitfinity_aws[@]}" lambda get-account-settings \
  --query 'AccountLimit.{Total:ConcurrentExecutions,Unreserved:UnreservedConcurrentExecutions}'
SH
```

Historical successful submission: `service-quotas request-service-quota-increase --service-code lambda --quota-code L-B99A9384 --desired-value 1001`, with the explicit TEST options and `AWS_MAX_ATTEMPTS=1`. This records request submission, not approval; do not execute it again for this case.

**Historical invocation only — not a current resume instruction.** `Unreserved >=102` is necessary, not sufficient. The older operator below pins a different source/image/frontend release; complete the reviewed release-bundle prerequisites above before any separately authorized invocation:

```bash
bash "$HOME/Downloads/Fitfinity_AWS_Test_Login_2026-10-06.sh" --run "$HOME/Desktop/FitfinityReact"
```

Operator SHA256: `1acfe7808c1781470224812c8eceede96c90cc4466c499e096961bae68784af0`.

Preserve `~/Library/Logs/Fitfinity/Fitfinity_AWS_Test_Login_2026-10-06/<accepted-main>/state.json` and its frontend directory. For any later authorized compatible run, preserve its resulting JSON whether it completes or stops. The operator requires the exact clean accepted commit and full tree. A documentation merge also changes that baseline: do not merge this documentation change into the active release or loosen its guard just to proceed. The later release must explicitly adopt its reviewed source baseline.

For a new client, discover applied/default quotas and existing request history early. `get-aws-default-service-quota` and `list-requested-service-quota-change-history-by-quota` are documented discovery operations, not new calls executed for this record. Calculate the required increase for that account; do not blindly reuse 1001. For subsequent updates, account for existing function reservations rather than applying the first-CREATE 102 test unconditionally.

## Corrections to preserve, not repeat

| Failure / incorrect assumption | Final working treatment | Evidence scope |
| --- | --- | --- |
| Expired login | `aws login --profile fitfinity-test`, then exact STS identity | User terminal result |
| Docker local image `.Id` assumed to be only configuration digest | Accept the two specifically recorded digest representations; retain remote manifest/config verification | Corrected uploader and Journey-reported upload success |
| `/dev/tty` text `r+` attempted seeking | Separate read and write streams; retain hidden password entry | Reproduced terminal error and corrected native continuation |
| TEST RDS backups 14 days rejected | Correct TEST template to 1 day; preserve production target and stack protections | Foundation success receipt |
| Cognito Lite with rotation | Essentials | Accepted pool/client configuration |
| Required email excluded from writable attributes | Exact `email,name` write set and verification before updates | Cognito success receipt |
| NAT-gateway CLI `--filters` | Singular `--filter` for that operation | Corrected preflight and later accepted egress |
| Unsupported EC2 instance EBS `Throughput` property | Remove that template property; retain actual volume throughput readback | Exact failure and successful recovery receipt |
| RDS `VPCSecurityGroups` | Correct `VpcSecurityGroups`; preserve exact group checks | Corrected preflight and DB success |
| Oversized source/config and incorrect Lambda runtime assumptions | Private loader, pinned source/CA, numeric runtime identity and corrected client/TLS checks | Final DB-access operator and native TLS/permission proof |
| Cognito JSON-through-stdin command validation | Explicit identity flags; password-only stdin parameter | CLI reproduction plus final Owner success; the earlier native stderr was insufficient to prove its exact cause |
| Scan finding disappeared | Dated exact finding review, not a claim the package was fixed | Retained scan review and exception |
| Unknown untracked ` 2` files | Preserve copies outside checkout, then enforce clean accepted tree | Later full source/build proof; origin of copies not established |
| Regional quota request 102 rejected | Request 1001 accepted for review; actual first-release capacity gate stays 102 | User-pasted provider error, request and case/capacity results |

A response timeout does not prove a write failed. Preserve intent and reconcile resources/request history before replay. Error categories and safe provider codes belong in receipts; secrets and raw password-bearing stderr do not.

## Automation after the proven deployment

Document now; implement and accept full deployment automation after the first complete live release and recovery rehearsal. Existing image publication and metadata-verification automation are partial capabilities, not an accepted end-to-end application release.

1. **Environment contract:** expected client account, regions, approved identity/roles, resource ownership, network/secret/Cognito references, immutable release inputs, origin/domain and retention/recovery policy.
2. **Early preflight:** identity, permissions, dependencies and service quotas before expensive builds. Persist request/case IDs and selected safe capacity values. The current hosting collector retained a response hash, so a separate native quota read was needed; improve that in its owning implementation.
3. **One-time bootstrap:** foundation, credentials/schema initialization and explicitly selected first Owner. Never run these on every release or copy developer identities/TEST IDs to production.
4. **Release:** merged-commit verification → immutable build → scan acceptance → reviewed backup/migration → rollout → configuration and smoke validation. Keep image, verification and deployment credentials separate.
5. **Recovery:** rehearse compatible application rollback and populated-data restore/upgrade recovery. Owned temporary cleanup is not sufficient proof.
6. **Activation:** only after live release, authentication and recovery acceptance, activate and verify the real main-branch pipeline. A failed prerequisite blocks rollout; failed smoke records a failed release and uses the reviewed recovery policy.

Each receipt should capture operation/revision/phase, account/region, source/image/template/artifact hashes, safe arguments or their hash, pending intent/idempotency token, provider outcome, owned resource IDs, reconciliation, verification and cleanup/recovery. Append the successful command/version and receipt here as soon as a phase passes; retain rejected forms only in the correction history.

## Security acceptance remains separate

For the historical `sha256:353907f09c208b35fd5160266e4f92da39e3db4e3a17e61236fdcd430ae15dc1` deployment, strict scan policy is **failed**. Its TEST exception `FITFINITY-TEST-2026-10-04-UNFIXED`, with dated review `FITFINITY-TEST-2026-10-05-SCAN-REVIEW`, permits only the exact reviewed current image and three High finding tuples with a complete scan no older than 24 hours. It expires **11 October 2026, 20:41:44 Singapore**. Production is excluded. This document does not extend the exception or claim the vulnerabilities are fixed.

## Source and provider references

- [Canonical stage registry](../backend/infrastructure/deployment-test.json), [dispatcher](../backend/infrastructure/deploy.py), [Journey](FITFINITY_JOURNEY.md), [Rules](FITFINITY_RULES_AND_ARCHITECTURE.md).
- Historical source/evidence recovered from `Fitfinity_GPT_6_1_Handoff_2026-09-30.zip`, final dated operators and the receipts indexed below. Current registry and `main` were reread from GitHub at the accepted commit during this compilation.
- [Lambda reserved concurrency](https://docs.aws.amazon.com/lambda/latest/dg/configuration-concurrency.html).
- [Service Quotas increase lifecycle](https://docs.aws.amazon.com/servicequotas/latest/userguide/request-quota-increase.html).
- [Request-status CLI](https://docs.aws.amazon.com/cli/latest/reference/service-quotas/get-requested-service-quota-change.html), [Lambda applied-capacity CLI](https://docs.aws.amazon.com/cli/latest/reference/lambda/get-account-settings.html).
- [Default quota CLI](https://docs.aws.amazon.com/cli/latest/reference/service-quotas/get-aws-default-service-quota.html), [request-history CLI](https://docs.aws.amazon.com/cli/latest/reference/service-quotas/list-requested-service-quota-change-history-by-quota.html).

## Receipt and corrected-operator index

Hashes identify the recovered artifact bytes. Successful phase flags were checked in the actual JSON receipts, not inferred from filenames. Reuse the current owning implementation; these historical scripts are not instructions to rerun completed setup.

| Stage | Successful receipt | Verified flag | Final operator revision |
| --- | --- | --- | --- |
| foundation | `Fitfinity_AWS_Foundation_Execution_9n_nxqjg.json` | `foundation_verified=true` | `identified by final artifact hash below` |
| cognito | `Fitfinity_AWS_Cognito_Execution_c3hufxxq.json` | `cognito_verified=true` | `identified by final artifact hash below` |
| egress | `Fitfinity_AWS_Egress_Execution_c87so5c2.json` | `egress_configuration_verified=true` | `identified by final artifact hash below` |
| private-egress | `Fitfinity_AWS_Private_Egress_Probe_9vu1hx5f.json` | `private_runtime_connectivity_verified=true` | `identified by final artifact hash below` |
| database-access | `Fitfinity_AWS_Database_Access_vle0p7n_.json` | `database_access_verified=true` | `2026-09-25-rds-tls-verification` |
| initial-schema | `Fitfinity_AWS_Database_Migrations_s9zsj0qk.json` | `migrations_applied=true` | `2026-09-25-initial-schema` |
| authentication-secret | `Fitfinity_AWS_Auth_Secret_5ko3lsp2.json` | `auth_secret_verified=true` | `2026-09-25-auth-secret` |
| github-aws-setup | `Fitfinity_AWS_GitHub_Setup_2026-10-01.2gmeXz.json` | `configuration_verified=true` | `2026-10-01-variable-pagination` |

<details>
<summary>Receipt and operator SHA256 values</summary>

- **foundation**
  - Receipt `Fitfinity_AWS_Foundation_Execution_9n_nxqjg.json`: `bdde68951cf17d952e43aed539292f0c72e3aba3a765269efd61a0f46aed3b56`.
  - Operator `Fitfinity_AWS_Foundation_Execute_2026-09-22.sh`: `5d5cdc9d0bcce1635d4a996a214f9748b8d7d96b2e9fc9ef6f1ce670afae5dc7`.
- **cognito**
  - Receipt `Fitfinity_AWS_Cognito_Execution_c3hufxxq.json`: `669f4c8b5a850a3ffcc0069166b8de6667279f7b883c133ae06d0a8c5c417510`.
  - Operator `Fitfinity_AWS_Cognito_Execute_2026-09-22.sh`: `061362f9869a7990b3b15fd9cefa25c5445853a1175ea70a629e9ec62d32b07e`.
- **egress**
  - Receipt `Fitfinity_AWS_Egress_Execution_c87so5c2.json`: `d12c67ffae4fe68cc45d76ffd1fe91b212f2c5143c68bcbb8dfe5b892f72eda1`.
  - Operator `Fitfinity_AWS_Egress_Execute_2026-09-22.sh`: `f809e164af09b528b13c3a07ad483f006ace626f5af8534ef19e03a9964679ad`.
- **private-egress**
  - Receipt `Fitfinity_AWS_Private_Egress_Probe_9vu1hx5f.json`: `73e2e40b4216733f34d9db0a4305677c05f1e34c08ac3bcba5254a5b2ec0ecc1`.
  - Operator `Fitfinity_AWS_Private_Egress_Probe_2026-09-24.sh`: `c9e7fd117d9032cc235840319513ac29db67dad478d001d63346b63b40e6e59a`.
- **database-access**
  - Receipt `Fitfinity_AWS_Database_Access_vle0p7n_.json`: `d948f6a529c7c65276b055ed058d10050062fe7530a68b79c4b57084e4e9bd92`.
  - Operator `Fitfinity_AWS_Database_Access_2026-09-25.sh`: `2a4d86473106ad58af34cfa4e3d00f2cc09cbca517dceec398600b2f863c3267`.
- **initial-schema**
  - Receipt `Fitfinity_AWS_Database_Migrations_s9zsj0qk.json`: `8319741ba4ce31eae10a9d2134de47bc5dfd5b6f5054d7a729281818bce5c963`.
  - Operator `Fitfinity_AWS_Database_Migrations_2026-09-25.sh`: `1a0810081089c5e513d0e93a294bf17bd22dc84b767278025ea9a820c06d6e2f`.
- **authentication-secret**
  - Receipt `Fitfinity_AWS_Auth_Secret_5ko3lsp2.json`: `7f89ebf75cdb623b1a232bd180201a87782e2d92976ff675e9b096eae544d932`.
  - Operator `Fitfinity_AWS_Auth_Secret_2026-09-25.sh`: `2144a6ebbface45a9fbd5fe7cd000b8be5895a3f62057cff0e54856ae3f6cfab`.
- **github-aws-setup**
  - Receipt `Fitfinity_AWS_GitHub_Setup_2026-10-01.2gmeXz.json`: `b359a9724015a76cf076952cb29a93436b75f9f6bebfdcd386b71b9e68bf7194`.
  - Operator `Fitfinity_AWS_GitHub_Setup_2026-10-01.sh`: `8513fecda06b53ced48e54bb49ec42f21cbfe5050615cd91688b7d491a9e9cf1`.
- `accepted-aws-runtime.json`: `756dff63a3addb212f7f0799ae7d8162be208282bf4c0fea7aaaacb22dbfda7a`; recorded status `aws_runtime_verified_with_exception`.
- `accepted-first-owner.json`: `4704e2b08a53919047cfe7d51c93ee837dfed25c9f9a31e5f8eb74887621b589`; recorded status `first_test_owner_created_and_linked`.
- `Fitfinity_AWS_Test_Login_2026-10-06.9ai7qy3v.json`: `dcf819fbed14310afd270c3d1139a69558eb68a7f090be7e9ae3486ab5f77f7e`; recorded status `stopped`.

The packaged aliases `accepted-aws-runtime.json` and `accepted-first-owner.json` retain the bytes of `Fitfinity_AWS_Current_Runtime_2026-10-04.1gdnm7o1.json` and `Fitfinity_AWS_First_Owner_2026-10-05.7m4s9dmk.json`, respectively.

</details>

## AWS call inventory with evidence level

This index covers the recovered final operators and receipts. `Response recorded` means a retained native receipt marked the operation `read` or `complete`; it does not certify every argument combination. `Accepted phase source` means the operation appears in a final operator whose phase passed, but its individual response was not retained. Optional diagnostic/recovery branches are not automatically successful calls. Unexercised hosting-only operations are excluded from this accepted-history index.

| AWS CLI operation | Evidence | Owning phase / recorded use |
| --- | --- | --- |
| `cloudformation create-stack` | Response recorded; Write recorded in accepted phase | authentication-secret, database-access, egress, github-aws-setup, initial-schema, private-egress, October runtime |
| `cloudformation delete-stack` | Response recorded; Write recorded in accepted phase | authentication-secret, database-access, initial-schema, private-egress, October Owner, October runtime |
| `cloudformation describe-events` | Accepted phase source | egress, private-egress |
| `cloudformation describe-stack-events` | Accepted phase source | authentication-secret, cognito, database-access, foundation, initial-schema |
| `cloudformation describe-stacks` | Response recorded; Accepted phase source | authentication-secret, cognito, database-access, egress, foundation, github-aws-setup, initial-schema, private-egress, October Owner, October hosting preflight, October runtime |
| `cloudformation get-stack-policy` | Response recorded; Accepted phase source | cognito, October Owner, October hosting preflight, October runtime |
| `cloudformation get-template` | Response recorded; Accepted phase source | authentication-secret, cognito, database-access, egress, foundation, github-aws-setup, initial-schema, private-egress, October Owner, October hosting preflight, October runtime |
| `cloudformation list-stack-resources` | Response recorded; Accepted phase source | authentication-secret, cognito, database-access, egress, foundation, github-aws-setup, initial-schema, private-egress, October Owner, October hosting preflight, October runtime |
| `cloudformation set-stack-policy` | Accepted phase source | cognito, foundation |
| `cloudformation update-stack` | Write recorded in accepted phase | authentication-secret, cognito, database-access, egress, foundation, initial-schema |
| `cloudformation update-termination-protection` | Accepted phase source | authentication-secret, database-access, foundation, initial-schema |
| `cloudformation validate-template` | Accepted phase source | authentication-secret, cognito, database-access, egress, initial-schema, private-egress |
| `cognito-idp admin-create-user` | Response recorded | October Owner |
| `cognito-idp admin-get-user` | Response recorded | October Owner, October hosting preflight |
| `cognito-idp describe-user-pool` | Response recorded; Accepted phase source | authentication-secret, cognito, October Owner, October hosting preflight, October runtime |
| `cognito-idp describe-user-pool-client` | Response recorded; Accepted phase source | authentication-secret, cognito, October Owner, October hosting preflight, October runtime |
| `cognito-idp get-user-pool-mfa-config` | Response recorded; Accepted phase source | authentication-secret, cognito, October Owner, October hosting preflight, October runtime |
| `cognito-idp list-user-pool-clients` | Accepted phase source | cognito |
| `ec2 describe-images` | Accepted phase source | egress |
| `ec2 describe-instance-credit-specifications` | Response recorded; Accepted phase source | egress, October Owner, October hosting preflight, October runtime |
| `ec2 describe-instances` | Response recorded; Accepted phase source | authentication-secret, database-access, egress, initial-schema, October Owner, October hosting preflight, October runtime |
| `ec2 describe-network-interfaces` | Response recorded; Accepted phase source | egress, October Owner, October hosting preflight, October runtime |
| `ec2 describe-route-tables` | Response recorded; Accepted phase source | authentication-secret, database-access, egress, initial-schema, October Owner, October hosting preflight, October runtime |
| `ec2 describe-security-groups` | Response recorded; Accepted phase source | authentication-secret, database-access, egress, initial-schema, October Owner, October hosting preflight, October runtime |
| `ec2 describe-subnets` | Response recorded; Accepted phase source | authentication-secret, database-access, initial-schema, October Owner, October hosting preflight, October runtime |
| `ec2 describe-volumes` | Response recorded; Accepted phase source | authentication-secret, database-access, egress, initial-schema, October Owner, October hosting preflight, October runtime |
| `ecr batch-get-image` | Response recorded | October Owner, October hosting preflight, October runtime |
| `ecr describe-image-scan-findings` | Response recorded; Accepted phase source | authentication-secret, database-access, initial-schema, October Owner, October hosting preflight, October runtime |
| `ecr describe-repositories` | Accepted phase source | github-aws-setup |
| `ecr get-registry-scanning-configuration` | Accepted phase source | github-aws-setup |
| `ecr get-repository-policy` | Response recorded | October Owner, October hosting preflight, October runtime |
| `ecr list-tags-for-resource` | Accepted phase source | github-aws-setup |
| `freetier get-account-plan-state` | Accepted phase source | authentication-secret, cognito, database-access, foundation, initial-schema, private-egress |
| `iam create-open-id-connect-provider` | Write recorded in accepted phase | github-aws-setup |
| `iam get-open-id-connect-provider` | Accepted phase source | github-aws-setup |
| `iam get-role` | Response recorded; Accepted phase source | authentication-secret, database-access, github-aws-setup, initial-schema, October Owner, October runtime |
| `iam get-role-policy` | Response recorded; Accepted phase source | authentication-secret, database-access, github-aws-setup, initial-schema, October Owner, October runtime |
| `iam list-attached-role-policies` | Response recorded; Accepted phase source | authentication-secret, database-access, github-aws-setup, initial-schema, October Owner, October runtime |
| `iam list-role-policies` | Response recorded; Accepted phase source | authentication-secret, database-access, github-aws-setup, initial-schema, October Owner, October runtime |
| `lambda get-account-settings` | Response recorded; User terminal output; see quota/identity status | October hosting preflight, manual status/identity |
| `lambda get-function` | Response recorded; Accepted phase source | authentication-secret, database-access, initial-schema, private-egress, October Owner, October runtime |
| `lambda get-function-url-config` | Accepted phase source | authentication-secret, database-access, initial-schema |
| `lambda get-policy` | Accepted phase source | authentication-secret, database-access, initial-schema |
| `lambda invoke` | Response recorded; Write recorded in accepted phase | authentication-secret, database-access, initial-schema, October Owner, October runtime |
| `lambda list-event-source-mappings` | Response recorded; Accepted phase source | authentication-secret, database-access, initial-schema, October Owner, October runtime |
| `logs describe-log-groups` | Response recorded; Accepted phase source | authentication-secret, database-access, initial-schema, October Owner, October runtime |
| `pricing get-products` | Accepted phase source | authentication-secret, database-access, foundation, initial-schema |
| `rds describe-db-instances` | Response recorded; Accepted phase source | authentication-secret, database-access, foundation, initial-schema, October Owner, October hosting preflight, October runtime |
| `rds describe-db-parameters` | Response recorded; Accepted phase source | authentication-secret, database-access, foundation, initial-schema, October Owner, October hosting preflight, October runtime |
| `secretsmanager describe-secret` | Response recorded; Accepted phase source | authentication-secret, database-access, initial-schema, October Owner, October hosting preflight, October runtime |
| `secretsmanager get-resource-policy` | Response recorded; Accepted phase source | authentication-secret, database-access, initial-schema, October Owner, October hosting preflight, October runtime |
| `service-quotas get-requested-service-quota-change` | User terminal output; see quota/identity status | manual status/identity |
| `service-quotas list-service-quotas` | User terminal output; see quota/identity status | manual status/identity |
| `service-quotas request-service-quota-increase` | User terminal output; see quota/identity status | manual status/identity |
| `ssm describe-instance-information` | Accepted phase source | egress |
| `ssm get-command-invocation` | Accepted phase source | egress |
| `ssm send-command` | Accepted phase source | egress |
| `sts get-caller-identity` | Response recorded; Accepted phase source; User terminal output; see quota/identity status | authentication-secret, cognito, database-access, egress, foundation, github-aws-setup, initial-schema, private-egress, October Owner, October hosting preflight, October runtime, manual status/identity |

Recovered inventory: **58 distinct CLI operations** with the evidence levels above. This is not a claim that 58 independent deployment actions all passed.

## Exact argument construction for final provisioning operators

The following reference preserves the AWS argument expressions from the corrected standalone operators tied to successful phase receipts. The variable values, templates, ownership and no-replay guards remain in those canonical owners. These are Python call expressions for review, **not standalone terminal commands**. An accepted phase proves its outcome, not execution of every recovery branch listed here. Repeated shared expressions are listed once with their applicable phases.

<details>
<summary>Corrected provisioning and recovery argument expressions</summary>

**`cloudformation create-stack`** — authentication-secret

Source: `historical-operator/Fitfinity_AWS_Auth_Secret_2026-09-25.sh/test-db-access.py`, line 752 (recovered artifact, not current repository line numbering).

```python
aws(
            "cloudformation",
            "create-stack",
            "--stack-name",
            name,
            "--template-body",
            "file://" + str(path),
            "--capabilities",
            "CAPABILITY_IAM",
            "--disable-rollback",
            "--client-request-token",
            uuid.uuid4().hex,
            "--tags",
            *["Key=" + k + ",Value=" + v for k, v in (tags or TAGS).items()],
            *(["--enable-termination-protection"] if protect else []),
        )
```

**`cloudformation create-stack`** — initial-schema

Source: `historical-operator/Fitfinity_AWS_Database_Migrations_2026-09-25.sh/test-db-access.py`, line 735 (recovered artifact, not current repository line numbering).

```python
aws(
            "cloudformation",
            "create-stack",
            "--stack-name",
            name,
            "--template-body",
            "file://" + str(path),
            "--capabilities",
            "CAPABILITY_IAM",
            "--disable-rollback",
            "--client-request-token",
            uuid.uuid4().hex,
            "--tags",
            *["Key=" + k + ",Value=" + v for k, v in (tags or TAGS).items()],
        )
```

**`cloudformation create-stack`** — database-access

Source: `historical-operator/Fitfinity_AWS_Database_Access_2026-09-25.sh/test-db-access.py`, line 732 (recovered artifact, not current repository line numbering).

```python
aws(
            "cloudformation",
            "create-stack",
            "--stack-name",
            name,
            "--template-body",
            "file://" + str(path),
            "--capabilities",
            "CAPABILITY_IAM",
            "--disable-rollback",
            "--client-request-token",
            uuid.uuid4().hex,
            "--tags",
            *["Key=" + k + ",Value=" + v for k, v in TAGS.items()],
        )
```

**`cloudformation create-stack`** — egress

Source: `historical-operator/Fitfinity_AWS_Egress_Execute_2026-09-22.sh/embedded-1.py`, line 197 (recovered artifact, not current repository line numbering).

```python
aws('cloudformation','create-stack','--stack-name',STACK,'--template-body','file://'+str(path),'--capabilities','CAPABILITY_IAM',
                    '--tags',*['Key='+k+',Value='+v for k,v in TAGS.items()],'--enable-termination-protection','--disable-rollback',
                    '--client-request-token','fitfinity-egress-'+TEMPLATE_SHA[:24])
```

**`cloudformation create-stack`** — private-egress

Source: `historical-operator/Fitfinity_AWS_Private_Egress_Probe_2026-09-24.sh/embedded-1.py`, line 130 (recovered artifact, not current repository line numbering).

```python
aws('cloudformation','create-stack','--stack-name',STACK,'--template-body','file://'+str(path),'--capabilities','CAPABILITY_IAM','--disable-rollback','--tags',*['Key='+k+',Value='+v for k,v in TAGS.items()])
```

**`cloudformation create-stack`** — github-aws-setup

Source: `historical-operator/Fitfinity_AWS_GitHub_Setup_2026-10-01.sh/setup.py`, line 823 (recovered artifact, not current repository line numbering).

```python
self.client.aws(
                    "cloudformation",
                    "create-stack",
                    stack_payload(name, self.templates[name]),
                )
```

**`cloudformation delete-stack`** — authentication-secret, database-access, initial-schema

Source: `historical-operator/Fitfinity_AWS_Database_Access_2026-09-25.sh/test-db-access.py`, line 1544 (recovered artifact, not current repository line numbering).

```python
aws("cloudformation", "delete-stack", "--stack-name", row["StackId"])
```

**`cloudformation delete-stack`** — private-egress

Source: `historical-operator/Fitfinity_AWS_Private_Egress_Probe_2026-09-24.sh/embedded-1.py`, line 153 (recovered artifact, not current repository line numbering).

```python
aws('cloudformation','delete-stack','--stack-name',STACK)
```

**`cloudformation set-stack-policy`** — cognito

Source: `historical-operator/Fitfinity_AWS_Cognito_Execute_2026-09-22.sh/embedded-1.py`, line 193 (recovered artifact, not current repository line numbering).

```python
aws('cloudformation', 'set-stack-policy', '--stack-name', STACK_ID, '--stack-policy-body', json.dumps(POOL_POLICY))
```

**`cloudformation set-stack-policy`** — foundation

Source: `historical-operator/Fitfinity_AWS_Foundation_Execute_2026-09-22.sh/embedded-1.py`, line 174 (recovered artifact, not current repository line numbering).

```python
aws('cloudformation','set-stack-policy','--stack-name',STACK,'--stack-policy-body',json.dumps(policy))
```

**`cloudformation update-stack`** — authentication-secret, database-access, initial-schema

Source: `historical-operator/Fitfinity_AWS_Database_Access_2026-09-25.sh/test-db-access.py`, line 1225 (recovered artifact, not current repository line numbering).

```python
aws(
        "cloudformation",
        "update-stack",
        "--stack-name",
        row["StackId"],
        "--template-body",
        "file://" + str(path),
        "--capabilities",
        "CAPABILITY_IAM",
        "--no-disable-rollback" if rollback_enabled else "--disable-rollback",
        "--client-request-token",
        uuid.uuid4().hex,
    )
```

**`cloudformation update-stack`** — cognito

Source: `historical-operator/Fitfinity_AWS_Cognito_Execute_2026-09-22.sh/embedded-1.py`, line 194 (recovered artifact, not current repository line numbering).

```python
aws('cloudformation', 'update-stack', '--stack-name', STACK_ID, '--template-body', 'file://' + str(path),
                '--parameters', 'ParameterKey=SessionHours,UsePreviousValue=true', '--disable-rollback',
                '--client-request-token', 'fitfinity-cognito-repair-' + TEMPLATE_SHA[:24])
```

**`cloudformation update-stack`** — egress

Source: `historical-operator/Fitfinity_AWS_Egress_Execute_2026-09-22.sh/embedded-1.py`, line 193 (recovered artifact, not current repository line numbering).

```python
aws('cloudformation','update-stack','--stack-name',FAILED_ARN,'--template-body','file://'+str(path),'--capabilities','CAPABILITY_IAM',
                    '--disable-rollback','--client-request-token','fitfinity-egress-repair-'+TEMPLATE_SHA[:24])
```

**`cloudformation update-stack`** — foundation

Source: `historical-operator/Fitfinity_AWS_Foundation_Execute_2026-09-22.sh/embedded-1.py`, line 137 (recovered artifact, not current repository line numbering).

```python
aws('cloudformation','update-stack','--stack-name',s['StackId'],'--template-body','file://'+str(source),
       '--disable-rollback','--client-request-token','fitfinity-retention-one-day-'+RECOVERY_HASH[:20])
```

**`cloudformation update-termination-protection`** — authentication-secret, database-access, initial-schema

Source: `historical-operator/Fitfinity_AWS_Database_Access_2026-09-25.sh/test-db-access.py`, line 1763 (recovered artifact, not current repository line numbering).

```python
aws(
                "cloudformation",
                "update-termination-protection",
                "--enable-termination-protection",
                "--stack-name",
                row["StackId"],
            )
```

**`cloudformation update-termination-protection`** — foundation

Source: `historical-operator/Fitfinity_AWS_Foundation_Execute_2026-09-22.sh/embedded-1.py`, line 171 (recovered artifact, not current repository line numbering).

```python
aws('cloudformation','update-termination-protection','--stack-name',STACK,'--enable-termination-protection')
```

**`iam create-open-id-connect-provider`** — github-aws-setup

Source: `historical-operator/Fitfinity_AWS_GitHub_Setup_2026-10-01.sh/setup.py`, line 801 (recovered artifact, not current repository line numbering).

```python
self.client.aws(
                "iam",
                "create-open-id-connect-provider",
                {
                    "Url": "https://token.actions.githubusercontent.com",
                    "ClientIDList": ["sts.amazonaws.com"],
                    "Tags": PROVIDER_TAGS,
                },
            )
```

**`ssm send-command`** — egress

Source: `historical-operator/Fitfinity_AWS_Egress_Execute_2026-09-22.sh/embedded-1.py`, line 89 (recovered artifact, not current repository line numbering).

```python
aws('ssm','send-command','--instance-ids',instance_id,'--document-name','AWS-RunShellScript',
        '--parameters',json.dumps({'commands':[CHECK_COMMAND],'executionTimeout':['900']}),'--timeout-seconds','120',
        '--comment','Fitfinity fixed non-secret NAT bootstrap check')
```

</details>

### Dynamic invocation and identity constructors

`lambda invoke` is built dynamically in the private-runtime owners. The October runtime's working contract includes the exact owned `--function-name`, synchronous `--invocation-type RequestResponse`, private JSON `--payload fileb://…`, `--cli-binary-format raw-in-base64-out`, an explicit response file, action/nonce/source checks, and function-result validation. Use each earlier phase's own constructor and response contract. The exact per-phase payload is generated by the owner. A transport success without a validated function result is not phase success.

The final Owner `identity_command` constructor is retained below; `payload` and password validation/selection are owned by the operator. Values must come from its guarded state and hidden input, not from substituting unrelated identities.

```python
def identity_command(operation, payload):
    # --cli-input-json can read its file more than once. A pipe is not replayable.
    # Only the password uses a file parameter; normal identity fields use argv.
    require(operation in {'admin-get-user', 'admin-create-user'}, 'Unsupported identity action')
    command = ['aws', 'cognito-idp', operation, '--user-pool-id', payload['UserPoolId'],
               '--username', payload['Username']]
    secret_input = None
    if operation == 'admin-create-user':
        command += ['--user-attributes', json.dumps(payload['UserAttributes']),
                    '--message-action', payload['MessageAction'], '--no-force-alias-creation',
                    '--temporary-password', 'file:///dev/stdin']
        secret_input = payload['TemporaryPassword']
    command += ['--profile', 'fitfinity-test', '--region', engine.REGION, '--output', 'json',
                '--no-cli-pager', '--no-cli-auto-prompt', '--cli-error-format', 'legacy',
                '--cli-connect-timeout', '10', '--cli-read-timeout', '30']
    return command, secret_input
```

### Keep this record current

After each accepted step, record the corrected owner/revision, safe command and input hashes, order/prerequisites, receipt and exact acceptance scope here. Keep failed attempts in the correction section. Before client automation, reconcile any missing argument transcripts against the pinned owning code/templates and verify the client environment independently.


## AWS-PRIVATE-RUNTIME-01 — prepared cloud operator, 7 October 2026

The current entry point is `python3 backend/infrastructure/deploy.py private-runtime`. Its registry stage is distinct from the historical local Docker `image-runtime`. Source was adapted from verified retained operator `2026-10-04-current-runtime-2`; the historical `353907f…` receipt is not current `86183723…` acceptance. No historical operator was executed during adaptation.

User-provided quota output received **7 October 2026**: `CASE_OPENED`, requested 1001, case `179123267300687`, actual total 1000 and unreserved 1000. This clears the >=102 recorded capacity prerequisite, without asserting approval of the 1001 request, a new AWS timestamp or a Codex read. The live operator rechecks identity and capacity. Do not resubmit.

### Runtime setup and permissions — provisioning receipt below

Review `backend/infrastructure/test-github-runtime-role.json` with the generated plan. It defines `fitfinity-test-github-runtime` plus the temporary-role permissions boundary; YS’s provisioning receipt is recorded below. The existing image/verification roles are untouched. The protected `aws-test` environment must retain required user review and main-only deployment branch policy; retain `AWS_RUNTIME_ROLE_ARN=arn:aws:iam::418638389566:role/fitfinity-test-github-runtime`. The role-variable guard passed in the failed collection run below; no environment setting is changed in this repair.

The runtime role reads STS/capacity, foundation/RDS/EC2 network metadata, Cognito configuration, secret metadata/policies, exact ECR manifest/current scan/repository policy and temporary stack/function/role/log metadata. It may create/delete only the named temporary stack, its two functions/log groups and stack-prefixed IAM roles; invoke only the two private probes; pass only those roles to Lambda. A permissions boundary caps temporary roles at application/auth secret access, Cognito reads, networking and logs. It grants no administrator/migration secret read, database migration, Owner creation, public endpoint or image publishing permission. Review the exact JSON resources and actions before provisioning.

#### Permission correction and offline audit — 7 October 2026

PR #13's policy at `ade57a055c2c6655391939ea2bb28189aaa8ff9d`, merged as `559ed1ec841b6bcf40aef06fc25d3724f0ab85a1`, had ineffective event-mapping list scope and omitted image-layer retrieval. The correction loads the actual canonical JSON in 12 additional regression cases, retaining all 36 runtime cases. These are offline policy contracts, not IAM simulation or live authorization evidence.

| Demonstrated defect / actual path | Correction and official evidence |
| --- | --- |
| `verify_live` calls `ListEventSourceMappings` with each exact function name; the action has no resource-level authorization | Own statement containing only `lambda:ListEventSourceMappings`, `Resource: "*"`, `aws:RequestedRegion=ap-southeast-1`. [Lambda authorization reference](https://docs.aws.amazon.com/service-authorization/latest/reference/list_lambda.html) and [global requested-region condition](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_condition-keys.html#condition-keys-requestedregion). The command filter remains exact, but IAM allows regional listing, not function-scoped listing. |
| CloudFormation creates container-image functions; creator lacked layer retrieval | Add `ecr:GetDownloadUrlForLayer` only on `arn:aws:ecr:ap-southeast-1:418638389566:repository/fitfinity-test-api`, alongside existing image reads. [Lambda image permissions](https://docs.aws.amazon.com/lambda/latest/dg/images-create.html). Existing repository policy must already authorize Lambda pulls; no `SetRepositoryPolicy`, publishing or broader repository access. |
| Tagged `GetFunction` reads used for ownership/integrity omitted the tag read | Add `lambda:ListTags` on only the two function ARNs. [Lambda tagging permissions](https://docs.aws.amazon.com/lambda/latest/dg/configuration-tags.html). |
| VPC function creation lacked two creator-side validation reads | Add regional wildcard `ec2:DescribeVpcs` and `ec2:GetSecurityGroupsForVpc` on exact `arn:aws:ec2:ap-southeast-1:418638389566:vpc/vpc-0b55320bb1a054441`, each with the requested-region condition. Existing `DescribeSecurityGroups`/`DescribeSubnets` remain. [Lambda VPC permissions](https://docs.aws.amazon.com/lambda/latest/dg/configuration-vpc.html) and [EC2 action/resource reference](https://docs.aws.amazon.com/service-authorization/latest/reference/list_ec2.html). No operator ENI mutation added. |
| Logs modern tagging used the wrong ARN suffix; published CloudFormation create/read contract also uses legacy tagging APIs | Move `logs:TagResource`/`UntagResource` to the two bare log-group ARNs; retain `:*` for other group operations and add `TagLogGroup`/`ListTagsLogGroup` there. [Logs ARN rules](https://docs.aws.amazon.com/AmazonCloudWatchLogs/latest/APIReference/API_LogGroup.html), [tag-on-create requirements](https://docs.aws.amazon.com/AmazonCloudWatchLogs/latest/APIReference/API_CreateLogGroup.html), and [AWS provider create/read permissions, pinned source](https://github.com/aws-cloudformation/aws-cloudformation-resource-providers-logs/blob/5cc1716174e6080698648523b8c5754175592b47/aws-logs-loggroup/aws-logs-loggroup.json). The published provider contract is evidence of required paths, not a claim to have inspected the deployed regional provider. |

Remaining execution trace: the collector's STS, Free Tier, EC2, RDS, Cognito, secret metadata, ECR manifest/scan and stack reads map to retained read statements. Runtime ownership, recovery and cleanup use stack describe/template/resource/event reads; function get/policy/URL/list reads; IAM get/inline-policy/attached-policy reads; and Logs describe/filter. Direct writes remain only create/delete of `fitfinity-test-current-runtime` and invocation of the two functions. Recovery resumes those same guarded paths, without stack updates or permission repair.

The six-resource CloudFormation template creates two functions, roles and log groups. No service role is supplied, so [CloudFormation uses caller-derived credentials](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-iam-servicerole.html). Underlying create/read/delete, inline-policy and tag permissions remain scoped to the two functions/groups and stack-prefixed role ARNs. `CreateRole` carries its exact boundary in the request ([IAM API](https://docs.aws.amazon.com/IAM/latest/APIReference/API_CreateRole.html)); its `iam:PermissionsBoundary` condition and Lambda-only `iam:PassRole` restriction remain enforced. No managed-policy attachment, boundary removal, role-policy administration outside that prefix, layer/version publication or public Lambda permission is added. Image functions have no ZIP layers/code-signing configuration requiring those unrelated actions.

The unchanged boundary matches the generated role statements: only the exact application/auth secrets at `AWSCURRENT`, auth metadata/Cognito reads, function logs and Lambda's VPC ENI actions. Both `lambda:SourceFunctionArn` denies prevent function code from using those EC2 capabilities. The operator still has only secret metadata/policy reads, not secret values. Existing ownership checks remain additional application guards, not substitutes for IAM scope.

The PR #14 template used `aud=sts.amazonaws.com` and subject `repo:LimYouSheng/FitfinityReact:environment:aws-test`; the 8 October live readback below establishes the required immutable-ID correction. An environment subject does not encode a branch: retain the protected environment's main-only branch policy and required user reviewer, in addition to the unchanged manual workflow's repository/main checks ([GitHub AWS OIDC guidance](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws)). No AWS API call or environment setting was used to validate those live prerequisites in this correction.

The original-policy test run intentionally failed, including the function-scoped mapping list and missing layer read. Corrected runtime/policy tests pass 48/48; negative controls reconstruct both original defects and widened ECR scope. The canonical backend gate retains all 416 backend/PostgreSQL and 470 previous infrastructure cases, adding 12 for 482 infrastructure cases. Final-SHA normal GitHub frontend/backend CI belongs in the correction PR. At that historical permission-review checkpoint runtime acceptance was pending; the authenticated October 8 completion above supersedes it. Exact `86183723…` approval, provenance, findings and expiry remain unchanged; no exception is extended or transferred.

### OIDC repair and operator evidence — 8 October 2026 (Singapore)

**Provisioning completed; runtime authentication failed.** YS reports successful Mac provisioning using profile `fitfinity-test`, region `ap-southeast-1`, account `418638389566`, principal `fitfinity-deployer`. Source was PR #14 merge `d80021b0f99ec4637e90c63ac0ad3d8332fdcb1a`; template SHA-256 `00fa091151848d6a715a1193c20d781973712e7ec90f314ad1fd500cf6dae077`. Stack `fitfinity-test-github-runtime-role` reached `CREATE_COMPLETE`, ID `arn:aws:cloudformation:ap-southeast-1:418638389566:stack/fitfinity-test-github-runtime-role/b0791310-c26b-11f1-a0a3-02ffc1e0235f`. It created role `arn:aws:iam::418638389566:role/fitfinity-test-github-runtime` and boundary `arn:aws:iam::418638389566:policy/fitfinity-test-private-runtime-boundary`. Evidence location reported by YS: `/Users/lys/fitfinity-aws-evidence/runtime-role.2cYziG`. These are owner-provided readbacks; Codex did not inspect those Mac files or call AWS.

Successful owner-reported calls, normalized with explicit profile/region for repeatability (not a verbatim terminal transcript):

```bash
aws --profile fitfinity-test --region ap-southeast-1 sts get-caller-identity
aws --profile fitfinity-test --region ap-southeast-1 cloudformation deploy \
  --stack-name fitfinity-test-github-runtime-role \
  --template-file backend/infrastructure/test-github-runtime-role.json \
  --capabilities CAPABILITY_NAMED_IAM
aws --profile fitfinity-test --region ap-southeast-1 cloudformation describe-stacks \
  --stack-name fitfinity-test-github-runtime-role
aws --profile fitfinity-test --region ap-southeast-1 iam get-role \
  --role-name fitfinity-test-github-runtime
```

Profileless Mac calls failed because those credentials belong to the named `fitfinity-test` profile. Retain the successful identity, deploy, stack readback and role readback as provisioning evidence; do not repeat deployment as an authentication diagnostic.

The separate failed collection is [run 37653771533](https://github.com/LimYouSheng/FitfinityReact/actions/runs/37653771533), runtime job [112915682111](https://github.com/LimYouSheng/FitfinityReact/actions/runs/37653771533/job/112915682111), attempt 1, operation ID `eb829b700e6c412b8bb3dbe1e850f034`. GitHub readback confirms both full verification jobs passed, credentials failed, the operator was skipped and runtime artifact upload failed. The reported credential error was `Not authorized to perform sts:AssumeRoleWithWebIdentity`; no collector files existed and no runtime resources were created. This is not successful collection, runtime proof or a recoverable operator-state artifact.

YS's OIDC readbacks at `/Users/lys/fitfinity-aws-evidence/oidc-readback.5oQfoi` showed runtime subject `repo:LimYouSheng/FitfinityReact:environment:aws-test`, while the working verification role trusts `repo:LimYouSheng@141623519/FitfinityReact@1353173586:environment:aws-test`. Both use audience `sts.amazonaws.com` and provider `arn:aws:iam::418638389566:oidc-provider/token.actions.githubusercontent.com`. This repair changes only the runtime template's exact subject to the verified immutable-ID form. It preserves audience/provider/environment, every permission scope and the boundary. It neither accepts both subjects nor changes GitHub's subject configuration. These live trust values are owner-provided evidence, not a new Codex AWS observation.

The [pinned credentials action metadata](https://github.com/aws-actions/configure-aws-credentials/blob/e3dd6a429d7300a6a4c196c26e071d42e0343502/action.yml) declares output `aws-account-id` and does not declare input `allowed-account-ids`. Keep that action pin; the workflow now checks its output immediately after successful credential acquisition. Empty/wrong account fails before the operator; the collector's own STS/account/runtime-role checks remain. `plan` skips credentials and the output check, and its existing offline test rejects all subprocess calls.

An `always()` step writes only mode and credential/account/operator step outcomes to `private-runtime-workflow-diagnostic.json`, uploaded separately as `fitfinity-runtime-diagnostic-<run>-<attempt>`. It contains no credentials, token, full environment or runtime receipt. Authentication failure still fails the job and skips the operator. Collector/recovery upload runs only if the operator started, retaining `if-no-files-found: error`; diagnostics never substitute for missing state or runtime acceptance.

### Prepared post-merge trust update — historical procedure

This procedure was prepared before the successful October 8 OIDC/collection/runtime runs above. It is retained as history, not an instruction to repeat the update; exact update execution details were not separately supplied. Its original prerequisites were: only after YS merges/reviews the correction and separately authorizes the AWS update, use the named Mac profile and a clean checkout of the exact reviewed merge. This is an **UPDATE** to the existing stack, not a new provisioning or runtime dispatch. The following preview checks the complete proposed template against the provisioned baseline, reads back that exact existing stack/template and creates a change set without executing it. Supply the reviewed merged SHA; do not substitute an unreviewed moving `main`.

```bash
set -euo pipefail
: "${REVIEWED_OIDC_MERGE:?Set the full reviewed merge SHA after YS merges}"
test "$(git rev-parse HEAD)" = "$REVIEWED_OIDC_MERGE"
test -z "$(git status --porcelain=v1 --untracked-files=all)"
test "$(git ls-remote origin refs/heads/main | cut -f1)" = "$REVIEWED_OIDC_MERGE"
git merge-base --is-ancestor d80021b0f99ec4637e90c63ac0ad3d8332fdcb1a HEAD
export AWS_PAGER=''
aws_args=(--profile fitfinity-test --region ap-southeast-1)
stack_id='arn:aws:cloudformation:ap-southeast-1:418638389566:stack/fitfinity-test-github-runtime-role/b0791310-c26b-11f1-a0a3-02ffc1e0235f'
evidence="$(mktemp -d /tmp/fitfinity-runtime-oidc.XXXXXX)"
git show d80021b0f99ec4637e90c63ac0ad3d8332fdcb1a:backend/infrastructure/test-github-runtime-role.json > "$evidence/baseline.json"
cp backend/infrastructure/test-github-runtime-role.json "$evidence/proposed.json"
aws "${aws_args[@]}" sts get-caller-identity > "$evidence/identity.json"
aws "${aws_args[@]}" cloudformation describe-stacks --stack-name "$stack_id" > "$evidence/stack.json"
aws "${aws_args[@]}" cloudformation get-template --stack-name "$stack_id" \
  --template-stage Original > "$evidence/deployed-template.json"
python3 - "$evidence" "$stack_id" <<'PY'
import hashlib, json, pathlib, sys
root = pathlib.Path(sys.argv[1])
read = lambda name: json.loads((root / name).read_text())
assert hashlib.sha256((root / 'baseline.json').read_bytes()).hexdigest() == '00fa091151848d6a715a1193c20d781973712e7ec90f314ad1fd500cf6dae077'
identity = read('identity.json')
assert identity['Account'] == '418638389566'
assert identity['Arn'] == 'arn:aws:iam::418638389566:user/fitfinity-deployer'
stack, = read('stack.json')['Stacks']
assert stack['StackId'] == sys.argv[2] and stack['StackStatus'] == 'CREATE_COMPLETE'
baseline = read('baseline.json')
body = read('deployed-template.json')['TemplateBody']
assert (json.loads(body) if isinstance(body, str) else body) == baseline
claims = baseline['Resources']['RuntimeRole']['Properties']['AssumeRolePolicyDocument']['Statement'][0]['Condition']['StringEquals']
assert claims['token.actions.githubusercontent.com:sub'] == 'repo:LimYouSheng/FitfinityReact:environment:aws-test'
claims['token.actions.githubusercontent.com:sub'] = 'repo:LimYouSheng@141623519/FitfinityReact@1353173586:environment:aws-test'
assert read('proposed.json') == baseline, 'Changes beyond the exact trust subject refused'
PY
change_name="runtime-oidc-$(date -u +%Y%m%dT%H%M%SZ)"
aws "${aws_args[@]}" cloudformation create-change-set --stack-name "$stack_id" \
  --change-set-name "$change_name" --change-set-type UPDATE \
  --template-body "file://$evidence/proposed.json" --capabilities CAPABILITY_NAMED_IAM \
  > "$evidence/change-set-created.json"
change_id="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["Id"])' "$evidence/change-set-created.json")"
aws "${aws_args[@]}" cloudformation wait change-set-create-complete --stack-name "$stack_id" --change-set-name "$change_id"
aws "${aws_args[@]}" cloudformation describe-change-set --stack-name "$stack_id" \
  --change-set-name "$change_id" > "$evidence/change-set-review.json"
python3 - "$evidence/change-set-review.json" <<'PY'
import json, sys
change_set = json.load(open(sys.argv[1]))
assert change_set['Status'] == 'CREATE_COMPLETE' and change_set['ExecutionStatus'] == 'AVAILABLE'
change, = change_set['Changes']
resource = change['ResourceChange']
assert resource['LogicalResourceId'] == 'RuntimeRole'
assert resource['ResourceType'] == 'AWS::IAM::Role'
assert resource['Action'] == 'Modify' and resource['Replacement'] == 'False'
assert resource['Scope'] == ['Properties']
assert resource['Details'] and all(d['Target'].get('Name') == 'AssumeRolePolicyDocument' and d['Target']['Attribute'] == 'Properties' and d['Evaluation'] == 'Static' for d in resource['Details'])
print('Review: only RuntimeRole AssumeRolePolicyDocument modification; no replacement.')
PY
printf 'Retain evidence at %s; review change set %s before execution.\n' "$evidence" "$change_id"
```

Stop if the stack/template changed, checks fail, the change set is empty/failed, any resource could be replaced, the boundary changes, or any permission changes appear. Do not relax these checks to fit unexpected drift. Inspect the saved change set and full baseline/proposed diff. **The preview block does not authorize execution.** After YS approves that exact change set, recheck its content and the deployed template, then execute only its saved ARN:

```bash
# Same reviewed shell/evidence variables; execute only after separate YS approval.
aws "${aws_args[@]}" cloudformation get-template --stack-name "$stack_id" \
  --change-set-name "$change_id" --template-stage Original > "$evidence/change-set-template.json"
aws "${aws_args[@]}" cloudformation get-template --stack-name "$stack_id" \
  --template-stage Original > "$evidence/before-execute.json"
python3 - "$evidence" <<'PY'
import json, pathlib, sys
root = pathlib.Path(sys.argv[1])
def body(name):
    value = json.loads((root / name).read_text())['TemplateBody']
    return json.loads(value) if isinstance(value, str) else value
assert body('change-set-template.json') == json.loads((root / 'proposed.json').read_text())
assert body('before-execute.json') == json.loads((root / 'baseline.json').read_text())
PY
aws "${aws_args[@]}" cloudformation execute-change-set --stack-name "$stack_id" --change-set-name "$change_id"
aws "${aws_args[@]}" cloudformation wait stack-update-complete --stack-name "$stack_id"
aws "${aws_args[@]}" cloudformation describe-stacks --stack-name "$stack_id" > "$evidence/updated-stack.json"
aws "${aws_args[@]}" iam get-role --role-name fitfinity-test-github-runtime > "$evidence/updated-role.json"
aws "${aws_args[@]}" cloudformation get-template --stack-name "$stack_id" \
  --template-stage Original > "$evidence/updated-template.json"
```

Verify `UPDATE_COMPLETE`, the same stack/role identity, exact new subject/audience/provider, and unchanged boundary/permissions against the saved proposed template. Retain all outputs, including failures; no automatic rollback/retry or delete is prescribed. Only then may YS separately authorize a fresh `collect` workflow. Do not rerun/resume the failed authentication run as though it held operator state. OIDC success, successful collection, current-image runtime proof and cleanup were subsequently evidenced as recorded above; no repeat is needed. Future release execution still rechecks the existing ECR pull policy, artifact access, quota/identity, scan freshness and exact image approval/expiry.

Preserve the existing ECR Lambda pull policy; if it does not cover both temporary names, the operator stops. Resolve that prerequisite through a separate reviewed permission change. Authenticated GitHub artifact access must work; this coding environment received `Forbidden` from the acceptance artifact storage redirect.

### Retained runtime operator procedure

Operation `aa2b2e439c3943b3b425de90302833ab` has completed successfully, including cleanup; do not repeat it for documentation or hosting preparation. The commands below remain a reference for a separately authorized future runtime operation using reviewed main. Generate and retain one operation ID; reuse it and the previous completed workflow run ID on recovery. They do not authorize dispatch or describe the pending persistent hosting procedure.

```bash
operation_id="$(python3 -c 'import uuid; print(uuid.uuid4().hex)')"
python3 backend/infrastructure/deploy.py private-runtime --mode plan \
  --operation-id "$operation_id" --directory /tmp/fitfinity-unused-plan

gh workflow run aws-private-runtime.yml --repo LimYouSheng/FitfinityReact --ref main \
  -f mode=collect -f operation_id="$operation_id"
# Inspect completed collection evidence before authorizing the run.
gh workflow run aws-private-runtime.yml --repo LimYouSheng/FitfinityReact --ref main \
  -f mode=run -f operation_id="$operation_id"
```

The workflow runs unchanged full frontend/backend verification first, uses protected OIDC only for live modes and retains partial evidence with `always()`. Planning makes no AWS calls. Collection makes reads only. Live execution creates no public endpoint, performs no bootstrap/migration/customer-data writes, and cleans only its owned temporary resources on success.

Collect output or resume/clean an interrupted operation, substituting the actual prior completed runtime run ID:

```bash
runtime_run=REPLACE_WITH_COMPLETED_RUNTIME_RUN_ID
gh run download "$runtime_run" --repo LimYouSheng/FitfinityReact --dir runtime-evidence
gh workflow run aws-private-runtime.yml --repo LimYouSheng/FitfinityReact --ref main \
  -f mode=run -f operation_id="$operation_id" -f resume_run="$runtime_run"
# Explicit cleanup instead of further runtime proof:
gh workflow run aws-private-runtime.yml --repo LimYouSheng/FitfinityReact --ref main \
  -f mode=cleanup -f operation_id="$operation_id" -f resume_run="$runtime_run"
```

Recovery authenticates the prior workflow/run/artifact checksum and exact operator commit. Preserve all receipts. A changed main/operator revision, missing artifact, uncertain create without a discoverable owned stack, unverifiable invocation or drift stops instead of recreating/deleting blindly. Do not manually repeat provider writes. If artifact upload was lost, preserve provider resources and obtain a reviewed recovery procedure; the implementation does not invent ownership. Cleanup can run after approval expiry using unchanged reviewed source and authenticated operation state; it does not reassert runtime acceptance.

The receipt binds operator commit separately from original image source/build; exact digest/approval, authenticated acceptance artifact, probe/template hashes, account/region, both subnets and operation ID. `aws_runtime_verified` and `temporary_cleanup_complete` are separate; `accepted` requires both plus a successful completed command. Failures remain visible with `accepted=false`. Historical receipt flags and caller-supplied success flags do not substitute for validated current results. Full application deployment and live sign-in/MFA/recovery remain blocked.
