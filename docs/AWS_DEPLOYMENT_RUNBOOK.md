# AWS deployment runbook

**Current evidence checkpoint: 7 October 2026 (Singapore), AWS-HOSTING-PREFLIGHT-01.** Exact-image security acceptance below is verified. Hosting/runtime and quota gates remain separate. The recovered deployment/command history retains its 6 October 2026, 04:41 Singapore checkpoint; it is not a live infrastructure readback.

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
| [deployment-test.json](../backend/infrastructure/deployment-test.json) | September 25 registry of explicit bootstrap/review/probe/release/recovery stages | `accepted` flags describe recorded native history, not a live query. Several release-blocker strings predate October Owner/OIDC/image work; registry is unchanged in this documentation task |
| [deploy.py](../backend/infrastructure/deploy.py) | Stage dispatch, metadata verification, image candidate and exact-image acceptance | `status` explicitly returns `automatic_release_ready=false`; `deploy` refuses full release. Metadata verification is not private runtime or hosting proof |
| [test-image-runtime.py](../backend/infrastructure/test-image-runtime.py) | Earlier image inspection owner | Still pins historical `efa53edd…`; it cannot establish runtime acceptance for `86183723…` |
| Dated October runtime operator/receipt | `Fitfinity_AWS_Current_Runtime_2026-10-04.1gdnm7o1.json` records private startup/health/shutdown, DB TLS, Cognito and cleanup in both subnets for `353907f…` | No private-runtime receipt found for newly accepted `86183723…`; image security acceptance is not runtime proof |
| Dated October hosting operator | `Fitfinity_AWS_Test_Login_2026-10-06.sh`, revision `2026-10-06-test-login-1`; 152 offline/25 CLI serialization checks and a native quota stop before writes | Retained external operator is not a merged repository hosting entry point. Its old source/image/frontend pins must not be bypassed or blindly resumed |
| GitHub image/verification roles | Checked-in `test-github-image-role.json` and `test-github-verification-role.json` implement their separate limited purposes | Neither policy grants `servicequotas:GetRequestedServiceQuotaChange` or `lambda:GetAccountSettings`; do not assume access or broaden IAM/workflows |

No authorized AWS operator connection is available in this coding session: current environment status exposes no outbound identities/secrets, and no operator connector is available. Credentials remain outside the coding environment. **Live quota request status, total concurrency and unreserved concurrency are unverified.** The account-guarded CloudShell procedure below is the fallback, not evidence that it ran.

### Next concrete task: review the TEST release bundle and runtime/hosting operator

Before any separately authorized hosting execution, prepare and review one immutable bundle with:

1. **Reviewed source:** explicitly select an accepted clean full commit for the hosting operator/templates and frontend, with successful final frontend/backend CI. This preflight starts at `c66acf9…`; its eventual documentation merge must be adopted explicitly if used. Keep the image's original `33d124f…` build provenance separate and verify compatibility; never relabel it with a documentation/repair SHA.
2. **Frontend artifact:** identify its source, API-mode configuration, exact intended CloudFront origin/API contract, build/PWA receipt, file manifest and checksum. Historical manifest `b63c6c3f7eb59128a52bfcf6368301e7e3d9637a6edbd34d8ba5644b04fde70c` and saved 40-file native bundle belong to the older `d2e8a4b…` release. Main Pages success is demo hosting evidence, not this AWS API-mode artifact. No new hosting frontend artifact was built or verified here.
3. **Image and private runtime:** retain the exact accepted `86183723…` digest, original candidate artifact and live acceptance receipt. Recheck approval validity/freshness under separately authorized operations at execution time. Obtain digest-bound startup/health/shutdown, database TLS/permissions, Cognito connectivity and temporary cleanup receipts in both private subnets; historical `353907f…` success is insufficient.
4. **Capacity and permissions:** obtain the three permitted CloudShell read results below, distinguishing request status from applied capacity; first CREATE requires at least 102 unreserved before reserving 2. Review an explicitly authorized operator identity and exact required CloudFormation/S3/CloudFront/API Gateway/WAF/Lambda/IAM operations, with application resources in Singapore and edge WAF in `us-east-1`. Existing image/verification roles do not authorize hosting. Do not change IAM or replay bootstrap to compensate.
5. **Recovery and acceptance:** review ownership/Add-only change sets, reconciliation of interrupted writes, immutable uploads, protected database/retained bucket handling, application rollback and populated-data migration/restore plan before rollout. Temporary cleanup is not a restore rehearsal. Preserve the existing Owner; do not recreate or resend invitations. Public HTTPS/API bytes, first login/password setup/MFA, `/me`, refresh/sign-out and recovery still require separate live acceptance.

The immediate next action is to return the guarded CloudShell quota outputs and review/adopt the exact operator/source/frontend bundle with digest-bound runtime evidence. Missing prerequisites block hosting execution. This task does not authorize those future AWS operations, dispatch, image rebuild, scan request or deployment.

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

### 10. Current-image runtime and first Owner

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
| Lambda total / unreserved concurrency | `10` / `10` |
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

### Proposed setup and permissions — not applied

Review `backend/infrastructure/test-github-runtime-role.json` with the generated plan. It proposes `fitfinity-test-github-runtime` plus the temporary-role permissions boundary. The existing image/verification roles are untouched. The protected `aws-test` environment must retain required user review and main-only deployment branch policy; an authorized operator must configure `AWS_RUNTIME_ROLE_ARN=arn:aws:iam::418638389566:role/fitfinity-test-github-runtime` before dispatch.

The proposed runtime role reads STS/capacity, foundation/RDS/EC2 network metadata, Cognito configuration, secret metadata/policies, exact ECR manifest/current scan/repository policy and temporary stack/function/role/log metadata. It may create/delete only the named temporary stack, its two functions/log groups and stack-prefixed IAM roles; invoke only the two private probes; pass only those roles to Lambda. A permissions boundary caps temporary roles at application/auth secret access, Cognito reads, networking and logs. It grants no administrator/migration secret read, database migration, Owner creation, public endpoint or image publishing permission. Review the exact JSON resources and actions before provisioning.

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

OIDC still requires the exact provider, `aud=sts.amazonaws.com` and `sub=repo:LimYouSheng/FitfinityReact:environment:aws-test`. An environment subject does not encode a branch: retain the protected environment's main-only branch policy and required user reviewer, in addition to the unchanged manual workflow's repository/main checks ([GitHub AWS OIDC guidance](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws)). No AWS API call or environment setting was used to validate those live prerequisites in this correction.

The original-policy test run intentionally failed, including the function-scoped mapping list and missing layer read. Corrected runtime/policy tests pass 48/48; negative controls reconstruct both original defects and widened ECR scope. The canonical backend gate retains all 416 backend/PostgreSQL and 470 previous infrastructure cases, adding 12 for 482 infrastructure cases. Final-SHA normal GitHub frontend/backend CI belongs in the correction PR. Current-image runtime acceptance remains pending separately authorized execution and cleanup. Exact `86183723…` approval, provenance, findings and expiry remain unchanged; no exception is extended or transferred.

Future user-authorized provisioning command (not run in this task):

```bash
aws cloudformation deploy --region ap-southeast-1 \
  --stack-name fitfinity-test-github-runtime-role \
  --template-file backend/infrastructure/test-github-runtime-role.json \
  --capabilities CAPABILITY_NAMED_IAM
```

Preserve the existing ECR Lambda pull policy; if it does not cover both temporary names, the operator stops. Resolve that prerequisite through a separate reviewed permission change. Authenticated GitHub artifact access must work; this coding environment received `Forbidden` from the acceptance artifact storage redirect.

### Exact future sequence

After user review/merge and provisioning, use the reviewed main checkout. Generate and retain one operation ID; reuse it and the previous completed workflow run ID on recovery. These commands are preparation instructions, not authorization to dispatch now.

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
