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

## Configuration

Local prototype development uses `VITE_PORTAL_MODE=demo` and an empty `VITE_API_BASE_URL`. API builds explicitly select API mode and the reviewed API origin. Unsupported API operations do not fall back to demo storage. Public frontend configuration is separate from server secrets; never put credentials in a Vite bundle.

Real-API tests create temporary Docker PostgreSQL databases, private buckets in the pinned Docker S3-compatible service and synthetic accounts. They require no production database, AWS credentials or Lambda redeployment. The local signed-token provider substitutes Cognito; FastAPI, PostgreSQL and object IO are real. Local storage compatibility does not prove AWS S3 deployment acceptance. The verifier owns isolation checks and cleanup; browser storage uses loopback port4181 or the internal Compose hostname.

Pending Trainer email correction is disabled by default (`FITFINITY_STAFF_EMAIL_CORRECTIONS_ENABLED=false`). Enable it only after all serving application instances understand superseded requests and the forward migration is verified. Once corrections exist, rollback requires a correction-aware application; old pending-request readers are incompatible, and populated schema downgrade refuses evidence loss. Disabling creation does not prevent account holders from finishing existing verification.

Protected media is disabled by default. An authorized deployment must explicitly set `FITFINITY_MEDIA_ENABLED=true` and `FITFINITY_MEDIA_BUCKET` for an existing private bucket; source code does not create AWS resources. The runtime uses its workload identity and Singapore S3 endpoint. Reviewed bucket CORS must permit only the staff origin, GET/PUT/HEAD and the required content-type/checksum/conditional-write headers. Test endpoints and synthetic credentials exist only in test fixtures. `python -m app.library_cleanup` performs a bounded cleanup sweep after configuration; scheduling, grants and production activation remain release tasks in Progress. It retains durable work after failure and never deletes a library object while it is attached or its upload lease remains valid. `python -m app.session_media_cleanup` similarly performs a bounded session-media sweep, respecting package-deletion Undo holds, original fixed expiry and worker leases. Both commands require separate release activation; source integration does not schedule them.

Prepared environments may reuse `FITFINITY_BROWSER_BACKEND_IMAGE`, `FITFINITY_BROWSER_RUNNER_IMAGE` and `PLAYWRIGHT_BROWSERS_PATH` with matching source/engine inputs. Keep public CA/proxy settings and TLS verification intact; cloud-specific trust setup stays outside tracked source. If Docker or trust is unavailable, record the blocker rather than substitute SQLite or a simulator.
