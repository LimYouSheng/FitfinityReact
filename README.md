# Fitfinity

Development entry point for the Fitfinity staff portal. See [AGENTS](AGENTS.md#authority-and-document-ownership) for the document map and engineering instructions.

## Development setup

Use Node 24, Python 3.12, Git and Docker Compose. Install frontend dependencies with `npm ci` from the reviewed lockfile; reuse matching dependencies, prepared images and Playwright caches during routine work. Backend versions and hashes are owned by `backend/pyproject.toml`, its requirements files and `backend/Dockerfile`.

`npm run dev` starts Vite; `npm run build` creates `dist/`; `npm run preview` serves it locally. `npm run build:pages-test` creates the `/FitfinityReact/` demo export. Local ports are not public preview URLs.

## Verification commands

| Command | Scope |
| --- | --- |
| `npm run verify:lint` / `verify:health` | Semantic lint and source ownership/health |
| `npm run verify:quality-checker` / `verify:health-checker` | Verifier regressions |
| `npm test -- --reporter=verbose` | Frontend units; append a real test path for focused work |
| `npm run verify:assessments` | Assessment form parity |
| `npm run verify:backend` | Full backend against isolated Docker PostgreSQL and S3-compatible storage, including offline infrastructure checks |
| `npm run verify:infrastructure` | Offline infrastructure checks alone |
| `CI=true npm run test:e2e -- --reporter=list` | Root/Pages/API-fixture builds, PWA and simulator browser suite |
| `npm run test:api-browser` | Real frontend/FastAPI/migrations/PostgreSQL and protected-media browser suite |

The [full-suite diagram](docs/Architecture/diagram.md#full-verification-suite) explains existing test scopes and planned mutation, performance, security, telemetry and operational verification. Planned suites have no executable command here until implemented.

CI runs the real-API suite in two complementary shards, each with its own disposable databases/storage and the existing 20-minute budget. The required `verify / api-browser` aggregate checks both successful jobs and every discovered case identity, rejecting missing, duplicated, skipped, retried or failed cases. Local `npm run test:api-browser` still runs the complete suite; `-- --shard=1/2 --reporter=list,json` selects a shard for diagnosis, with `PLAYWRIGHT_JSON_OUTPUT_FILE` selecting its report path. A shard alone is not complete acceptance. Overall job budgets are 60 minutes each for frontend/backend, 20 minutes per API-browser shard and 5 minutes for the aggregate; these are separate from test and database timeouts.

Required CI and evidence rules belong to [AGENTS](AGENTS.md#verify-and-publish). Test inventories are defined by the verifiers, not historical counts in documentation.

## Dependency maintenance

The design has three layers:

| Layer | Purpose | Behaviour |
| --- | --- | --- |
| Version updates | Keep dependencies current | Weekly Monday, 9 am Singapore. At most one open version-update PR each for npm, Actions and backend Dockerfile images. |
| Security alerts and updates | Identify known vulnerabilities and propose fixes | GitHub alerts and security PRs have been observed. Settings and the complete alert inventory still require verification with appropriate read access; security updates are independent of the weekly schedule and version-PR limits. |
| Blocking audit | Prevent known high/critical npm findings from passing verification | Full verification runs `npm audit --include=dev --audit-level=high --json`, including development tooling, and retains the report even on failure. Registry/access errors fail verification too. This does not audit Python, OS/container packages or the deployed environment. |

Routine minor/patch updates are grouped. Major upgrades and sensitive tooling (TypeScript, ESLint, Playwright, Wrangler and Miniflare, where present) remain separate from routine and security groups. Other minor/patch npm security fixes have their own group. Exclusions from grouping do not ignore updates. Python runtime proposals remain within the supported 3.12 line. The version-PR limit controls the queue, not a guarantee that all updates fit one PR.

Every update follows **PR → compatibility fixes → all three CI gates → review and authorized merge → fresh main CI → separately authorized deployment and verification**. There is no automatic merge. Failed updates leave the deployed version unchanged and require investigation; never weaken tests to accept them. Main verification can publish the Pages demo; AWS image publication and Lambda deployment remain separate manual, authorized actions. A deployed security fix is complete only after the affected deployment is verified.

GitHub alerts/PRs notify according to account notification preferences; they do not automatically message this chat. Recheck security settings for each client repository. Closing update PRs neither fixes vulnerabilities nor disables future proposals. The five formerly floating frontend test/build declarations remain pinned.

Review release notes, compatibility, dependency/lockfile diffs, vulnerability reachability and license changes before accepting an update. Require full final-head frontend/backend/API-browser CI and preserve SHA-pinned Actions and image digest/source evidence. Triage critical or actively exploited findings within24 hours, high severity within3 business days and other alerts within10 business days; record exposure, owner and disposition rather than treating these targets as a waiver or guaranteed remediation date. Release-blocking findings must be resolved or separately reviewed before deployment.

Python version updates remain manually maintained: `pyproject.toml` feeds uv-generated `requirements.lock` and `requirements-test.lock`, which the current Dependabot pip fetcher does not discover as ordinary requirements files. Observed security PR106 updated only the manifest; a bot proposal is incomplete until both hashed locks are regenerated and verified. Review/regenerate both hashed locks together with manifest changes and run the complete isolated backend/API gates. Compose PostgreSQL/RustFS pins also remain manually reviewed; Dockerfile automation is not claimed to cover Compose or every embedded image reference. A tested lock-updater integration, remaining image coverage, security-alert activation, SBOMs and provenance remain in Progress H4.

## Manual AWS image publication

Normal main verification and Pages demo publishing do not queue an AWS image. For an independently authorized image candidate, open **Build and scan the verified AWS image candidate** in GitHub Actions, select `main`, and enter its exact 40-character commit SHA as `source_sha`. A mismatch stops before verification; main advancing later does not change the run’s selected commit. `AWS_IMAGE_RELEASE_ENABLED=true` must remain explicitly configured. The workflow reruns the complete frontend, backend and API-browser gates for that SHA before requesting the existing `aws-test` environment approval. Inspect the run SHA and successful gates before approving; cancel an obsolete candidate instead of approving it to clear a queue.

The image retains its commit/run/attempt binding, exact AWS account/role checks, scan and receipt evidence. Historical candidates retain their original provenance rules; new manual candidates require all three verification gates. Image publication does not deploy Lambda, run migrations or authorize customer/provider actions. AWS release workflows remain serialized separately from ordinary verification/demo publishing.

## Configuration

Local prototype development uses `VITE_PORTAL_MODE=demo` and an empty `VITE_API_BASE_URL`. API builds explicitly select API mode and the reviewed API origin. Unsupported API operations do not fall back to demo storage. Public frontend configuration is separate from server secrets; never put credentials in a Vite bundle.

Real-API tests create temporary Docker PostgreSQL databases, private buckets in the pinned Docker S3-compatible service and synthetic accounts. They require no production database, AWS credentials or Lambda redeployment. The local signed-token provider substitutes Cognito; FastAPI, PostgreSQL and object IO are real. Local storage compatibility does not prove AWS S3 deployment acceptance. The verifier owns isolation checks and cleanup; browser storage uses loopback port4181 or the internal Compose hostname.

Pending Trainer email correction is disabled by default (`FITFINITY_STAFF_EMAIL_CORRECTIONS_ENABLED=false`). Enable it only after all serving application instances understand superseded requests and the forward migration is verified. Once corrections exist, rollback requires a correction-aware application; old pending-request readers are incompatible, and populated schema downgrade refuses evidence loss. Disabling creation does not prevent account holders from finishing existing verification.

Protected media is disabled by default. An authorized deployment must explicitly set `FITFINITY_MEDIA_ENABLED=true` and `FITFINITY_MEDIA_BUCKET` for an existing private bucket; source code does not create AWS resources. The runtime uses its workload identity and Singapore S3 endpoint. Reviewed bucket CORS must permit only the staff origin, GET/PUT/HEAD and the required content-type/checksum/conditional-write headers. Test endpoints and synthetic credentials exist only in test fixtures. `python -m app.library_cleanup` performs a bounded cleanup sweep after configuration; scheduling, grants and production activation remain release tasks in Progress. It retains durable work after failure and never deletes a library object while it is attached or its upload lease remains valid. `python -m app.session_media_cleanup` similarly performs a bounded session-media sweep, respecting package-deletion Undo holds, original fixed expiry and worker leases. Both commands require separate release activation; source integration does not schedule them.

Prepared environments may reuse `FITFINITY_BROWSER_BACKEND_IMAGE`, `FITFINITY_BROWSER_RUNNER_IMAGE` and `PLAYWRIGHT_BROWSERS_PATH` with matching source/engine inputs. Keep public CA/proxy settings and TLS verification intact; cloud-specific trust setup stays outside tracked source. If Docker or trust is unavailable, record the blocker rather than substitute SQLite or a simulator.

## Operator-assisted lost-authenticator recovery

This is a controlled operator procedure, not an app-admin feature. [The recovery policy](docs/SERVICE_CONTRACTS.md#authority-and-privacy) governs it. Preparation and synthetic drills do not authorize a live reset; first bind the deployment and obtain the applicable provider/database authorization.

1. Open an access-controlled recovery case. Independently verify the person against trusted records; record the verifier, approving operator, case reference and timestamps. Never collect passwords, codes or TOTP secrets in the case.
2. Verify the AWS account, Singapore region, pool/app client, staff UUID, immutable issuer/subject and provider Username. Use `python -m app.auth.admin check-config` in the reviewed environment. Confirm the same enabled provider identity and verified recovery address. Stop on a mismatch, pending email change or unsupported second factor; pool-wide software-token MFA stays required.
3. In a reviewed database transaction, lock the exact authentication account then mapped identity and set that identity inactive, matching all bound identifiers. The existing identity trigger advances its epoch and closes its sessions; old challenge flows also lose authority. Record the transaction receipt and verify revocation. Do not deactivate the Trainer/client business records or touch another identity.
4. With separately authorized operator IAM, call Cognito `AdminUserGlobalSignOut`, then `AdminDeleteSoftwareToken` for that exact pool/Username. Retain sanitized request IDs and CloudTrail evidence in the case. Never replace the user/subject, disable pool MFA or use MFA preference changes as a factor reset. Runtime IAM receives no administrator recovery permissions.
5. Confirm the same enabled subject has no old software-token registration. A timeout or uncertain response leaves the application identity inactive; reconcile the exact action and provider/audit evidence before proceeding. Do not blindly repeat a reset that could erase a newly enrolled authenticator.
6. After confirmed reset and a coordinated handoff, restore only that mapped identity to active in a reviewed transaction. Its epoch advances again; old sessions/flows stay invalid. The staff member signs in, enrolls their own authenticator and proves fresh sign-out/re-login. Check required MFA and close the recovery case with evidence; suspend access again if verification fails.

The full backend gate includes [the synthetic recovery drill](backend/tests/test_mfa_recovery_drill.py) and [actual HTTP worker crash/restart tests](backend/tests/test_process_restart.py), using isolated PostgreSQL. Cognito reset responses are SDK-stubbed; an authorized real-provider recovery and deployment-specific execution receipt remain separate acceptance.
