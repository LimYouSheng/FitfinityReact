# Fitfinity versions

Repository snapshot: **28 October 2026 Singapore**, dependency inputs from merged main **`1246fb815b1240a92fd953b85abc05f18f46bc73` (PR104)**. This is a searchable inventory for manual vulnerability triage, not a clean scan certificate or a list of what is currently deployed. Manifests, lockfiles and workflow pins remain authoritative. Refresh this file in every PR that changes them; do not patch versions only in this document.

[Runtime and images](#runtime-and-images) · [Direct npm](#direct-npm-dependencies) · [All npm](#all-locked-npm-dependencies) · [Python](#all-locked-python-dependencies) · [GitHub Actions](#github-actions) · [Browser engines](#browser-engines) · [Manual patching](#manual-patch-guide) · [Unknown versions](#versions-that-require-artifact-or-environment-inspection)

## Runtime and images

| Component | Repository version / selection | Version owner and scope |
| --- | --- | --- |
| Frontend application | 0.1.0 | [package.json](../package.json); project metadata, not a release fingerprint |
| Backend application | 0.1.0 | [backend/pyproject.toml](../backend/pyproject.toml); project metadata |
| FastAPI application/OpenAPI metadata | 0.2.0 | [backend/app/main.py](../backend/app/main.py); API metadata differs from backend package metadata |
| Node.js | 24 (major only; patch floats) | [.github/workflows/verify.yml](../.github/workflows/verify.yml) and other workflows; build/test runtime |
| npm | Bundled with selected Node; not independently pinned | Capture `node --version` and `npm --version` for each verification/release |
| Python | 3.12.14; supported range >=3.12,<3.13 | [backend/Dockerfile](../backend/Dockerfile), [pyproject.toml](../backend/pyproject.toml) |
| Backend base image | `python:3.12.14-slim-trixie` | Dockerfile; Debian 13 (Trixie); tag is not a digest lock |
| Lambda Web Adapter | `public.ecr.aws/awsguru/aws-lambda-adapter:1.0.1` | Dockerfile runtime stage only; tag is not a digest lock |
| Local/test PostgreSQL | `postgres:17.11-bookworm` | [backend/compose.yaml](../backend/compose.yaml); Debian 12 (Bookworm); local/test only |
| RDS engine configuration | PostgreSQL 17.11 | [backend/infrastructure/test-foundation.json](../backend/infrastructure/test-foundation.json); desired configuration, not a current live query |
| Isolated S3-compatible test storage | `ghcr.io/rustfs/rustfs:1.0.3@sha256:9ca9559533b537d10482fe923288b676ad08f92a7069d9a17327fbae3cab688b` | Compose; synthetic test media only, not production S3 |
| Frontend CI host | `macos-15` | verify.yml; runner image/tool patches change outside this repository |
| Backend/API/release CI host | `ubuntu-latest` | Workflows; alias floats; latest investigated run used Ubuntu 24.04.5 image20261012.334.1 |
| Browser system packages | Installed by Playwright through APT; exact versions not locked | [scripts/prepare-browser-apt.py](../scripts/prepare-browser-apt.py) selects official US archive; signing keys and suites retained |
| Perl/OpenSSL build floors | `perl-base >=5.40.1-6+deb13u1`; `libssl3t64 >=3.5.7-1~deb13u2` | Dockerfile runs APT upgrade then checks these minimums; actual installed versions may be newer |

The optional `FITFINITY_BROWSER_BACKEND_IMAGE` and `FITFINITY_BROWSER_RUNNER_IMAGE` overrides select environment-prepared images, not additional production pins. Their actual digest and contents must be captured when used. The rejected official Playwright container trial is not part of the selected runtime.

## Direct npm dependencies

Resolved versions come from [package-lock.json](../package-lock.json), including when [package.json](../package.json) allows a range. Development tools execute in CI and may contribute code to generated assets; “development” does not mean irrelevant to security.

| Package | Manifest constraint | Locked version | Scope |
| --- | --- | --- | --- |
| `react` | `19.2.0` | `19.2.0` | application |
| `react-dom` | `19.2.0` | `19.2.0` | application |
| `@eslint/js` | `10.0.1` | `10.0.1` | development/build/test |
| `@playwright/test` | `1.64.1` | `1.64.1` | development/build/test |
| `@testing-library/jest-dom` | `7.0.1` | `7.0.1` | development/build/test |
| `@testing-library/react` | `16.3.3` | `16.3.3` | development/build/test |
| `@testing-library/user-event` | `14.6.6` | `14.6.6` | development/build/test |
| `@vitejs/plugin-react` | `6.1.1` | `6.1.1` | development/build/test |
| `css-tree` | `3.2.1` | `3.2.1` | development/build/test |
| `eslint` | `10.11.0` | `10.11.0` | development/build/test |
| `eslint-plugin-react-hooks` | `7.1.1` | `7.1.1` | development/build/test |
| `globals` | `17.12.0` | `17.12.0` | development/build/test |
| `jsdom` | `30.0.1` | `30.0.1` | development/build/test |
| `rolldown` | `1.2.6` | `1.2.6` | development/build/test |
| `vite` | `^8.3.5` | `8.3.5` | development/build/test |
| `vitest` | `^4.1.12` | `4.1.12` | development/build/test |
| `yaml` | `2.9.1` | `2.9.1` | development/build/test |

## All locked Python dependencies

[Runtime lock](../backend/requirements.lock): **33 packages**. [Test lock](../backend/requirements-test.lock): **42 packages**, including runtime dependencies. Both locks contain install hashes. Direct declarations are in [pyproject.toml](../backend/pyproject.toml); a transitive package may still be security-critical. Runtime dependencies appear in both locks unless noted.

| Distribution | Runtime lock | Test lock | Declaration |
| --- | --- | --- | --- |
| `alembic` | 1.20.0 | 1.20.0 | direct |
| `annotated-doc` | 0.0.5 | 0.0.5 | transitive |
| `annotated-types` | 0.8.0 | 0.8.0 | transitive |
| `anyio` | 4.15.1 | 4.15.1 | transitive |
| `boto3` | 1.43.94 | 1.43.94 | direct |
| `botocore` | 1.43.94 | 1.43.94 | transitive |
| `cffi` | 2.1.1 | 2.1.1 | transitive |
| `click` | 8.5.0 | 8.5.0 | transitive |
| `cryptography` | 50.0.1 | 50.0.1 | transitive |
| `fastapi` | 0.141.1 | 0.141.1 | direct |
| `greenlet` | 3.5.6 | 3.5.6 | transitive |
| `h11` | 0.16.0 | 0.16.0 | transitive |
| `httpcore2` | — | 2.13.0 | transitive |
| `httpx2` | — | 2.13.0 | direct |
| `idna` | 3.19 | 3.19 | transitive |
| `iniconfig` | — | 2.3.0 | transitive |
| `jmespath` | 1.1.0 | 1.1.0 | transitive |
| `mako` | 1.4.1 | 1.4.1 | transitive |
| `markupsafe` | 3.0.3 | 3.0.3 | transitive |
| `packaging` | — | 26.3 | transitive |
| `pluggy` | — | 1.6.0 | transitive |
| `psycopg` | 3.3.5 | 3.3.5 | direct |
| `psycopg-binary` | 3.3.5 | 3.3.5 | transitive |
| `pycparser` | 3.0 | 3.0 | transitive |
| `pydantic` | 2.13.5 | 2.13.5 | transitive |
| `pydantic-core` | 2.46.5 | 2.46.5 | transitive |
| `pydantic-settings` | 2.15.0 | 2.15.0 | direct |
| `pygments` | — | 2.21.0 | transitive |
| `pyjwt` | 2.15.0 | 2.15.0 | direct |
| `pytest` | — | 9.1.1 | direct |
| `python-dateutil` | 2.9.0.post0 | 2.9.0.post0 | transitive |
| `python-dotenv` | 1.2.3 | 1.2.3 | transitive |
| `ruff` | — | 0.16.7 | direct |
| `s3transfer` | 0.19.2 | 0.19.2 | transitive |
| `six` | 1.17.0 | 1.17.0 | transitive |
| `sqlalchemy` | 2.0.53 | 2.0.53 | direct |
| `starlette` | 1.6.0 | 1.6.0 | transitive |
| `truststore` | — | 0.10.4 | transitive |
| `typing-extensions` | 4.16.0 | 4.16.0 | transitive |
| `typing-inspection` | 0.4.4 | 0.4.4 | transitive |
| `urllib3` | 2.8.0 | 2.8.0 | transitive |
| `uvicorn` | 0.53.0 | 0.53.0 | direct |

## GitHub Actions

Full commit SHA is the effective pin. Version labels below are comments from the workflows, not independently verified release tags. Inspect the action's own dependencies/runtime at that SHA when an advisory affects it; those dependencies are not in this repository's npm lock. Local reusable workflows are source in this repository, not third-party versioned dependencies.

| Action | Pinned commit | Workflow label | Used in |
| --- | --- | --- | --- |
| `actions/checkout` | `3d3c42e5aac5ba805825da76410c181273ba90b1` | v7 | [aws-image-accept.yml](../.github/workflows/aws-image-accept.yml), [aws-image.yml](../.github/workflows/aws-image.yml), [aws-private-runtime.yml](../.github/workflows/aws-private-runtime.yml), [aws-test-hosting.yml](../.github/workflows/aws-test-hosting.yml), [aws-verify.yml](../.github/workflows/aws-verify.yml), [infrastructure.yml](../.github/workflows/infrastructure.yml), [pages.yml](../.github/workflows/pages.yml), [verify.yml](../.github/workflows/verify.yml) |
| `actions/configure-pages` | `45bfe0192ca1faeb007ade9deae92b16b8254a0d` | v6 | [pages.yml](../.github/workflows/pages.yml) |
| `actions/deploy-pages` | `cd2ce8fcbc39b97be8ca5fce6e763baed58fa128` | v5 | [pages.yml](../.github/workflows/pages.yml) |
| `actions/download-artifact` | `d3f86a106a0bac45b974a628896c90dbdf5c8093` | v4 | [verify.yml](../.github/workflows/verify.yml) |
| `actions/setup-node` | `820762786026740c76f36085b0efc47a31fe5020` | v7 | [aws-test-hosting.yml](../.github/workflows/aws-test-hosting.yml), [infrastructure.yml](../.github/workflows/infrastructure.yml), [pages.yml](../.github/workflows/pages.yml), [verify.yml](../.github/workflows/verify.yml) |
| `actions/upload-artifact` | `ea165f8d65b6e75b540449e92b4886f43607fa02` | v4.6.2 | [aws-image-accept.yml](../.github/workflows/aws-image-accept.yml), [aws-image.yml](../.github/workflows/aws-image.yml), [aws-private-runtime.yml](../.github/workflows/aws-private-runtime.yml), [aws-test-hosting.yml](../.github/workflows/aws-test-hosting.yml), [aws-verify.yml](../.github/workflows/aws-verify.yml), [infrastructure.yml](../.github/workflows/infrastructure.yml), [verify.yml](../.github/workflows/verify.yml) |
| `actions/upload-pages-artifact` | `fc324d3547104276b827a68afc52ff2a11cc49c9` | v5 | [pages.yml](../.github/workflows/pages.yml) |
| `aws-actions/configure-aws-credentials` | `e3dd6a429d7300a6a4c196c26e071d42e0343502` | No tag label; use SHA | [aws-image-accept.yml](../.github/workflows/aws-image-accept.yml), [aws-image.yml](../.github/workflows/aws-image.yml), [aws-private-runtime.yml](../.github/workflows/aws-private-runtime.yml), [aws-test-hosting.yml](../.github/workflows/aws-test-hosting.yml), [aws-verify.yml](../.github/workflows/aws-verify.yml) |

## Browser engines

Source: `playwright-core@1.64.1` package's `browsers.json`, checked against the npm lock. CI installs Chromium and WebKit; not every engine available in the package is used. Browser revisions, host libraries and platform overrides matter in addition to the Playwright npm version. Recheck this table after every Playwright update.

| Engine/tool | Browser version | Playwright revision | Scope / platform override |
| --- | --- | --- | --- |
| chromium | 156.0.8078.4 | 1248 | CI browser engine |
| chromium-headless-shell | 156.0.8078.4 | 1248 | CI browser engine |
| firefox | 157.0 | 1555 | Available in package; not selected by current CI |
| webkit | 27.2 | 2370 | CI browser engine; mac14: revision 2251, mac14-arm64: revision 2251 |
| ffmpeg | Not provided by package | 1013 | Playwright recording helper |
| winldd | Not provided by package | 1007 | Available in package; not selected by current CI |
| android | Not provided by package | 1001 | Available in package; not selected by current CI |

## Manual patch guide

1. Find the affected name here, then confirm the exact advisory's affected/fixed versions against the owning lock or image digest. An alert count of zero does not prove absence of undisclosed or unscanned vulnerabilities. Use vendor advisories and recorded exposure; do not assume the newest version is compatible.
2. **npm:** update the relevant declaration and regenerate `package-lock.json` with npm. For transitive findings, inspect `npm explain PACKAGE` and update the owning dependency or deliberately reviewed override. Keep multiple nested versions in view. Review the diff, run `npm ci` and `npm audit --include=dev --audit-level=high`, and update this inventory. Do not hand-edit integrity hashes.
3. **Python:** update `backend/pyproject.toml` for direct requirements and regenerate **both hashed locks** with uv. Runtime compilation uses `uv pip compile backend/pyproject.toml --generate-hashes --python-version 3.12 -o backend/requirements.lock`; test compilation adds `--extra test -c backend/requirements.lock -o backend/requirements-test.lock`. Use a targeted `--upgrade-package PACKAGE` where appropriate, retain unrelated pins and review the resolution. Install with `--require-hashes`, run `pip check`, and verify isolated backend/PostgreSQL and API workflows. Never accept a manifest-only bot change as complete.
4. **Images/OS:** update Dockerfile or Compose references deliberately, including digest pins where present. Rebuild and inspect the exact resulting image's OS and Python packages; APT upgrades mean a Dockerfile tag alone cannot identify installed OS versions. Scan the resulting digest. A tag update, minimum-version check or alternate mirror is not a clean scan receipt. Review PostgreSQL compatibility/migrations and RustFS storage behavior when those images change.
5. **Actions/browser tooling:** update the reviewed Action commit SHA or Playwright package/lock and installed matching engines. Review upstream changes and platform support; do not weaken tests or raise timeouts to accept an upgrade.
6. Complete the required frontend, backend and real-API CI on the exact final head, review and merge, then check fresh main verification. AWS publication/deployment and provider actions require separate authorization. Record the deployed digest and verify the affected runtime before claiming a deployed fix. [Runbook](runbook.md#dependency-maintenance) and [AGENTS](../AGENTS.md) own the standing process.

## Versions that require artifact or environment inspection

| Surface | Why no exact current version is claimed | Evidence needed |
| --- | --- | --- |
| Deployed Lambda and frontend assets | Source merge does not update either artifact | Authorized release receipt: source SHA, image digest / asset manifest and actual deployed identity |
| Debian/Ubuntu/macOS system libraries, OpenSSL, GStreamer and codecs | Image tags, APT upgrades and hosted runner images can change independently | Exact-image SBOM or `dpkg-query -W`, OS release, image digest and scan timestamp; runner setup logs for CI |
| Docker Engine, Buildx, Compose, Git, uv, pip and AWS CLI | Host/build tools are not all version-locked by this repo | `docker version`, `docker buildx version`, `docker compose version`, `git --version`, `uv --version`, `python -m pip --version`, `aws --version` in the actual environment |
| Current RDS patch version | Template specifies desired version; provider/maintenance state may differ | Separately authorized read of actual engine version and maintenance state |
| Cognito, S3, API Gateway, CloudFront and other managed services | Provider-managed internals have no application package version to patch | Provider advisories, enabled configuration/features and service-specific response plan |
| Action-internal/transitively downloaded tools and browser native libraries | Not included in the app's package locks | Action source/SBOM at pinned SHA, engine manifest and exact runner/image package evidence |
| User physical browsers and OS | Controlled by each device | Device OS/browser versions during physical acceptance and subsequent update review |

This inventory is not a complete artifact SBOM. In particular, no unverified OS/library version is invented to fill a gap. The separately scanned Playwright container trial exposed GStreamer and bundled-npm findings; rejecting that image does not establish that the retained runner is clean. [Progress](../PROGRESS.md) owns that follow-up and future SBOM/provenance automation.

## All locked npm dependencies

Every non-root `packages` entry in [package-lock.json](../package-lock.json) is represented below, including optional OS/architecture packages and nested duplicates. These are **271 locked entries**, not 271 packages guaranteed to be installed on every host or shipped to browsers. “Development” and “optional” are lockfile classifications. Paths disambiguate duplicate versions and can be searched directly in the lockfile.

| Package | Locked version | Lock scope | Lock path |
| --- | --- | --- | --- |
| `@adobe/css-tools` | `4.5.0` | development | `node_modules/@adobe/css-tools` |
| `@asamuzakjp/css-color` | `6.0.7` | development | `node_modules/@asamuzakjp/css-color` |
| `@asamuzakjp/dom-selector` | `8.3.2` | development | `node_modules/@asamuzakjp/dom-selector` |
| `@babel/code-frame` | `7.29.7` | development | `node_modules/@babel/code-frame` |
| `@babel/compat-data` | `7.29.7` | development | `node_modules/@babel/compat-data` |
| `@babel/core` | `7.29.7` | development | `node_modules/@babel/core` |
| `@babel/generator` | `7.29.8` | development | `node_modules/@babel/generator` |
| `@babel/helper-compilation-targets` | `7.29.7` | development | `node_modules/@babel/helper-compilation-targets` |
| `@babel/helper-globals` | `7.29.7` | development | `node_modules/@babel/helper-globals` |
| `@babel/helper-module-imports` | `7.29.7` | development | `node_modules/@babel/helper-module-imports` |
| `@babel/helper-module-transforms` | `7.29.7` | development | `node_modules/@babel/helper-module-transforms` |
| `@babel/helper-string-parser` | `7.29.7` | development | `node_modules/@babel/helper-string-parser` |
| `@babel/helper-validator-identifier` | `7.29.7` | development | `node_modules/@babel/helper-validator-identifier` |
| `@babel/helper-validator-option` | `7.29.7` | development | `node_modules/@babel/helper-validator-option` |
| `@babel/helpers` | `7.29.7` | development | `node_modules/@babel/helpers` |
| `@babel/parser` | `7.29.9` | development | `node_modules/@babel/parser` |
| `@babel/runtime` | `7.29.7` | development | `node_modules/@babel/runtime` |
| `@babel/template` | `7.29.7` | development | `node_modules/@babel/template` |
| `@babel/traverse` | `7.29.8` | development | `node_modules/@babel/traverse` |
| `@babel/types` | `7.29.8` | development | `node_modules/@babel/types` |
| `@bramus/specificity` | `2.4.2` | development | `node_modules/@bramus/specificity` |
| `@cacheable/memory` | `2.2.0` | development | `node_modules/@cacheable/memory` |
| `@cacheable/utils` | `2.5.0` | development | `node_modules/@cacheable/utils` |
| `@csstools/color-helpers` | `6.1.1` | development | `node_modules/@csstools/color-helpers` |
| `@csstools/css-calc` | `3.3.0` | development | `node_modules/@csstools/css-calc` |
| `@csstools/css-color-parser` | `4.2.2` | development | `node_modules/@csstools/css-color-parser` |
| `@csstools/css-parser-algorithms` | `4.0.0` | development | `node_modules/@csstools/css-parser-algorithms` |
| `@csstools/css-syntax-patches-for-csstree` | `1.1.12` | development | `node_modules/@csstools/css-syntax-patches-for-csstree` |
| `@csstools/css-tokenizer` | `4.0.0` | development | `node_modules/@csstools/css-tokenizer` |
| `@eslint-community/eslint-utils` | `4.10.1` | development | `node_modules/@eslint-community/eslint-utils` |
| `@eslint-community/regexpp` | `4.12.2` | development | `node_modules/@eslint-community/regexpp` |
| `@eslint/config-array` | `0.23.5` | development | `node_modules/@eslint/config-array` |
| `@eslint/config-helpers` | `0.7.0` | development | `node_modules/@eslint/config-helpers` |
| `@eslint/core` | `1.2.1` | development | `node_modules/@eslint/core` |
| `@eslint/js` | `10.0.1` | development | `node_modules/@eslint/js` |
| `@eslint/object-schema` | `3.0.5` | development | `node_modules/@eslint/object-schema` |
| `@eslint/plugin-kit` | `0.7.3` | development | `node_modules/@eslint/plugin-kit` |
| `@exodus/bytes` | `1.15.1` | development | `node_modules/@exodus/bytes` |
| `@humanfs/core` | `0.19.2` | development | `node_modules/@humanfs/core` |
| `@humanfs/node` | `0.16.8` | development | `node_modules/@humanfs/node` |
| `@humanfs/types` | `0.15.0` | development | `node_modules/@humanfs/types` |
| `@humanwhocodes/module-importer` | `1.0.1` | development | `node_modules/@humanwhocodes/module-importer` |
| `@humanwhocodes/retry` | `0.4.3` | development | `node_modules/@humanwhocodes/retry` |
| `@jridgewell/gen-mapping` | `0.3.13` | development | `node_modules/@jridgewell/gen-mapping` |
| `@jridgewell/remapping` | `2.3.5` | development | `node_modules/@jridgewell/remapping` |
| `@jridgewell/resolve-uri` | `3.1.2` | development | `node_modules/@jridgewell/resolve-uri` |
| `@jridgewell/sourcemap-codec` | `1.6.0` | development | `node_modules/@jridgewell/sourcemap-codec` |
| `@jridgewell/trace-mapping` | `0.3.31` | development | `node_modules/@jridgewell/trace-mapping` |
| `@keyv/bigmap` | `1.3.1` | development | `node_modules/@keyv/bigmap` |
| `@keyv/serialize` | `1.1.1` | development | `node_modules/@keyv/serialize` |
| `@oxc-project/types` | `0.147.0` | development | `node_modules/@oxc-project/types` |
| `@oxc-project/types` | `0.155.0` | development | `node_modules/vite/node_modules/@oxc-project/types` |
| `@playwright/test` | `1.64.1` | development | `node_modules/@playwright/test` |
| `@rolldown/binding-android-arm-eabi` | `1.2.6` | development; optional | `node_modules/@rolldown/binding-android-arm-eabi` |
| `@rolldown/binding-android-arm-eabi` | `1.2.15` | development; optional | `node_modules/vite/node_modules/@rolldown/binding-android-arm-eabi` |
| `@rolldown/binding-android-arm64` | `1.2.6` | development; optional | `node_modules/@rolldown/binding-android-arm64` |
| `@rolldown/binding-android-arm64` | `1.2.15` | development; optional | `node_modules/vite/node_modules/@rolldown/binding-android-arm64` |
| `@rolldown/binding-darwin-arm64` | `1.2.6` | development; optional | `node_modules/@rolldown/binding-darwin-arm64` |
| `@rolldown/binding-darwin-arm64` | `1.2.15` | development; optional | `node_modules/vite/node_modules/@rolldown/binding-darwin-arm64` |
| `@rolldown/binding-darwin-x64` | `1.2.6` | development; optional | `node_modules/@rolldown/binding-darwin-x64` |
| `@rolldown/binding-darwin-x64` | `1.2.15` | development; optional | `node_modules/vite/node_modules/@rolldown/binding-darwin-x64` |
| `@rolldown/binding-freebsd-x64` | `1.2.6` | development; optional | `node_modules/@rolldown/binding-freebsd-x64` |
| `@rolldown/binding-freebsd-x64` | `1.2.15` | development; optional | `node_modules/vite/node_modules/@rolldown/binding-freebsd-x64` |
| `@rolldown/binding-linux-arm-gnueabihf` | `1.2.6` | development; optional | `node_modules/@rolldown/binding-linux-arm-gnueabihf` |
| `@rolldown/binding-linux-arm-gnueabihf` | `1.2.15` | development; optional | `node_modules/vite/node_modules/@rolldown/binding-linux-arm-gnueabihf` |
| `@rolldown/binding-linux-arm64-gnu` | `1.2.6` | development; optional | `node_modules/@rolldown/binding-linux-arm64-gnu` |
| `@rolldown/binding-linux-arm64-gnu` | `1.2.15` | development; optional | `node_modules/vite/node_modules/@rolldown/binding-linux-arm64-gnu` |
| `@rolldown/binding-linux-arm64-musl` | `1.2.6` | development; optional | `node_modules/@rolldown/binding-linux-arm64-musl` |
| `@rolldown/binding-linux-arm64-musl` | `1.2.15` | development; optional | `node_modules/vite/node_modules/@rolldown/binding-linux-arm64-musl` |
| `@rolldown/binding-linux-ppc64-gnu` | `1.2.6` | development; optional | `node_modules/@rolldown/binding-linux-ppc64-gnu` |
| `@rolldown/binding-linux-ppc64-gnu` | `1.2.15` | development; optional | `node_modules/vite/node_modules/@rolldown/binding-linux-ppc64-gnu` |
| `@rolldown/binding-linux-s390x-gnu` | `1.2.6` | development; optional | `node_modules/@rolldown/binding-linux-s390x-gnu` |
| `@rolldown/binding-linux-s390x-gnu` | `1.2.15` | development; optional | `node_modules/vite/node_modules/@rolldown/binding-linux-s390x-gnu` |
| `@rolldown/binding-linux-x64-gnu` | `1.2.6` | development; optional | `node_modules/@rolldown/binding-linux-x64-gnu` |
| `@rolldown/binding-linux-x64-gnu` | `1.2.15` | development; optional | `node_modules/vite/node_modules/@rolldown/binding-linux-x64-gnu` |
| `@rolldown/binding-linux-x64-musl` | `1.2.6` | development; optional | `node_modules/@rolldown/binding-linux-x64-musl` |
| `@rolldown/binding-linux-x64-musl` | `1.2.15` | development; optional | `node_modules/vite/node_modules/@rolldown/binding-linux-x64-musl` |
| `@rolldown/binding-openharmony-arm64` | `1.2.6` | development; optional | `node_modules/@rolldown/binding-openharmony-arm64` |
| `@rolldown/binding-openharmony-arm64` | `1.2.15` | development; optional | `node_modules/vite/node_modules/@rolldown/binding-openharmony-arm64` |
| `@rolldown/binding-win32-arm64-msvc` | `1.2.6` | development; optional | `node_modules/@rolldown/binding-win32-arm64-msvc` |
| `@rolldown/binding-win32-arm64-msvc` | `1.2.15` | development; optional | `node_modules/vite/node_modules/@rolldown/binding-win32-arm64-msvc` |
| `@rolldown/binding-win32-x64-msvc` | `1.2.6` | development; optional | `node_modules/@rolldown/binding-win32-x64-msvc` |
| `@rolldown/binding-win32-x64-msvc` | `1.2.15` | development; optional | `node_modules/vite/node_modules/@rolldown/binding-win32-x64-msvc` |
| `@rolldown/pluginutils` | `1.0.1` | development | `node_modules/@rolldown/pluginutils` |
| `@standard-schema/spec` | `1.1.0` | development | `node_modules/@standard-schema/spec` |
| `@testing-library/dom` | `10.4.1` | development | `node_modules/@testing-library/dom` |
| `@testing-library/jest-dom` | `7.0.1` | development | `node_modules/@testing-library/jest-dom` |
| `@testing-library/react` | `16.3.3` | development | `node_modules/@testing-library/react` |
| `@testing-library/user-event` | `14.6.6` | development | `node_modules/@testing-library/user-event` |
| `@types/aria-query` | `5.0.4` | development | `node_modules/@types/aria-query` |
| `@types/chai` | `5.2.3` | development | `node_modules/@types/chai` |
| `@types/deep-eql` | `4.0.2` | development | `node_modules/@types/deep-eql` |
| `@types/esrecurse` | `4.3.1` | development | `node_modules/@types/esrecurse` |
| `@types/estree` | `1.0.9` | development | `node_modules/@types/estree` |
| `@types/json-schema` | `7.0.15` | development | `node_modules/@types/json-schema` |
| `@vitejs/plugin-react` | `6.1.1` | development | `node_modules/@vitejs/plugin-react` |
| `@vitest/expect` | `4.1.12` | development | `node_modules/@vitest/expect` |
| `@vitest/mocker` | `4.1.12` | development | `node_modules/@vitest/mocker` |
| `@vitest/pretty-format` | `4.1.12` | development | `node_modules/@vitest/pretty-format` |
| `@vitest/runner` | `4.1.12` | development | `node_modules/@vitest/runner` |
| `@vitest/snapshot` | `4.1.12` | development | `node_modules/@vitest/snapshot` |
| `@vitest/spy` | `4.1.12` | development | `node_modules/@vitest/spy` |
| `@vitest/utils` | `4.1.12` | development | `node_modules/@vitest/utils` |
| `acorn` | `8.18.0` | development | `node_modules/acorn` |
| `acorn-jsx` | `5.3.2` | development | `node_modules/acorn-jsx` |
| `ajv` | `6.15.0` | development | `node_modules/ajv` |
| `ansi-regex` | `5.0.1` | development | `node_modules/ansi-regex` |
| `ansi-styles` | `5.2.0` | development | `node_modules/ansi-styles` |
| `aria-query` | `5.3.0` | development | `node_modules/aria-query` |
| `assertion-error` | `2.0.1` | development | `node_modules/assertion-error` |
| `balanced-match` | `4.0.4` | development | `node_modules/@eslint/config-array/node_modules/balanced-match` |
| `balanced-match` | `4.0.4` | development | `node_modules/eslint/node_modules/balanced-match` |
| `baseline-browser-mapping` | `2.11.26` | development | `node_modules/baseline-browser-mapping` |
| `bidi-js` | `1.0.3` | development | `node_modules/bidi-js` |
| `brace-expansion` | `5.0.12` | development | `node_modules/@eslint/config-array/node_modules/brace-expansion` |
| `brace-expansion` | `5.0.12` | development | `node_modules/eslint/node_modules/brace-expansion` |
| `browserslist` | `4.29.1` | development | `node_modules/browserslist` |
| `cacheable` | `2.5.0` | development | `node_modules/cacheable` |
| `caniuse-lite` | `1.0.30001812` | development | `node_modules/caniuse-lite` |
| `chai` | `6.3.0` | development | `node_modules/chai` |
| `convert-source-map` | `2.0.0` | development | `node_modules/convert-source-map` |
| `cross-spawn` | `7.0.6` | development | `node_modules/cross-spawn` |
| `css-tree` | `3.2.1` | development | `node_modules/css-tree` |
| `css.escape` | `1.5.1` | development | `node_modules/css.escape` |
| `data-urls` | `7.0.0` | development | `node_modules/data-urls` |
| `debug` | `4.4.3` | development | `node_modules/debug` |
| `decimal.js` | `10.6.0` | development | `node_modules/decimal.js` |
| `deep-is` | `0.1.4` | development | `node_modules/deep-is` |
| `dequal` | `2.0.3` | development | `node_modules/dequal` |
| `detect-libc` | `2.1.2` | development | `node_modules/detect-libc` |
| `dom-accessibility-api` | `0.6.3` | development | `node_modules/@testing-library/jest-dom/node_modules/dom-accessibility-api` |
| `dom-accessibility-api` | `0.5.16` | development | `node_modules/dom-accessibility-api` |
| `electron-to-chromium` | `1.5.439` | development | `node_modules/electron-to-chromium` |
| `entities` | `8.0.0` | development | `node_modules/entities` |
| `es-module-lexer` | `2.3.2` | development | `node_modules/es-module-lexer` |
| `escalade` | `3.2.0` | development | `node_modules/escalade` |
| `escape-string-regexp` | `4.0.0` | development | `node_modules/escape-string-regexp` |
| `eslint` | `10.11.0` | development | `node_modules/eslint` |
| `eslint-plugin-react-hooks` | `7.1.1` | development | `node_modules/eslint-plugin-react-hooks` |
| `eslint-scope` | `9.1.2` | development | `node_modules/eslint-scope` |
| `eslint-visitor-keys` | `3.4.3` | development | `node_modules/@eslint-community/eslint-utils/node_modules/eslint-visitor-keys` |
| `eslint-visitor-keys` | `5.0.1` | development | `node_modules/eslint-visitor-keys` |
| `espree` | `11.2.0` | development | `node_modules/espree` |
| `esquery` | `1.7.0` | development | `node_modules/esquery` |
| `esrecurse` | `4.3.0` | development | `node_modules/esrecurse` |
| `estraverse` | `5.3.0` | development | `node_modules/estraverse` |
| `estree-walker` | `3.0.3` | development | `node_modules/estree-walker` |
| `esutils` | `2.0.3` | development | `node_modules/esutils` |
| `expect-type` | `1.4.0` | development | `node_modules/expect-type` |
| `fast-deep-equal` | `3.1.3` | development | `node_modules/fast-deep-equal` |
| `fast-json-stable-stringify` | `2.1.0` | development | `node_modules/fast-json-stable-stringify` |
| `fast-levenshtein` | `2.0.6` | development | `node_modules/fast-levenshtein` |
| `fdir` | `6.5.0` | development | `node_modules/fdir` |
| `file-entry-cache` | `11.1.5` | development | `node_modules/file-entry-cache` |
| `find-up` | `5.0.0` | development | `node_modules/find-up` |
| `flat-cache` | `6.1.23` | development | `node_modules/flat-cache` |
| `flatted` | `3.4.4` | development | `node_modules/flatted` |
| `fsevents` | `2.3.3` | development; optional | `node_modules/vite/node_modules/fsevents` |
| `gensync` | `1.0.0-beta.2` | development | `node_modules/gensync` |
| `glob-parent` | `6.0.2` | development | `node_modules/glob-parent` |
| `globals` | `17.12.0` | development | `node_modules/globals` |
| `hashery` | `1.5.1` | development | `node_modules/hashery` |
| `hermes-estree` | `0.25.1` | development | `node_modules/hermes-estree` |
| `hermes-parser` | `0.25.1` | development | `node_modules/hermes-parser` |
| `hookified` | `1.15.1` | development | `node_modules/hookified` |
| `hookified` | `2.2.0` | development | `node_modules/qified/node_modules/hookified` |
| `html-encoding-sniffer` | `6.0.0` | development | `node_modules/html-encoding-sniffer` |
| `ignore` | `5.3.2` | development | `node_modules/ignore` |
| `imurmurhash` | `0.1.4` | development | `node_modules/imurmurhash` |
| `indent-string` | `4.0.0` | development | `node_modules/indent-string` |
| `is-extglob` | `2.1.1` | development | `node_modules/is-extglob` |
| `is-glob` | `4.0.3` | development | `node_modules/is-glob` |
| `is-potential-custom-element-name` | `1.0.1` | development | `node_modules/is-potential-custom-element-name` |
| `isexe` | `2.0.0` | development | `node_modules/isexe` |
| `js-tokens` | `4.0.0` | development | `node_modules/js-tokens` |
| `jsdom` | `30.0.1` | development | `node_modules/jsdom` |
| `jsesc` | `3.1.0` | development | `node_modules/jsesc` |
| `json-schema-traverse` | `0.4.1` | development | `node_modules/json-schema-traverse` |
| `json-stable-stringify-without-jsonify` | `1.0.1` | development | `node_modules/json-stable-stringify-without-jsonify` |
| `json5` | `2.2.3` | development | `node_modules/json5` |
| `keyv` | `5.6.0` | development | `node_modules/keyv` |
| `levn` | `0.4.1` | development | `node_modules/levn` |
| `lightningcss` | `1.33.0` | development | `node_modules/lightningcss` |
| `lightningcss-android-arm64` | `1.33.0` | development; optional | `node_modules/lightningcss-android-arm64` |
| `lightningcss-darwin-arm64` | `1.33.0` | development; optional | `node_modules/lightningcss-darwin-arm64` |
| `lightningcss-darwin-x64` | `1.33.0` | development; optional | `node_modules/lightningcss-darwin-x64` |
| `lightningcss-freebsd-x64` | `1.33.0` | development; optional | `node_modules/lightningcss-freebsd-x64` |
| `lightningcss-linux-arm-gnueabihf` | `1.33.0` | development; optional | `node_modules/lightningcss-linux-arm-gnueabihf` |
| `lightningcss-linux-arm64-gnu` | `1.33.0` | development; optional | `node_modules/lightningcss-linux-arm64-gnu` |
| `lightningcss-linux-arm64-musl` | `1.33.0` | development; optional | `node_modules/lightningcss-linux-arm64-musl` |
| `lightningcss-linux-x64-gnu` | `1.33.0` | development; optional | `node_modules/lightningcss-linux-x64-gnu` |
| `lightningcss-linux-x64-musl` | `1.33.0` | development; optional | `node_modules/lightningcss-linux-x64-musl` |
| `lightningcss-win32-arm64-msvc` | `1.33.0` | development; optional | `node_modules/lightningcss-win32-arm64-msvc` |
| `lightningcss-win32-x64-msvc` | `1.33.0` | development; optional | `node_modules/lightningcss-win32-x64-msvc` |
| `locate-path` | `6.0.0` | development | `node_modules/locate-path` |
| `lru-cache` | `5.1.1` | development | `node_modules/@babel/helper-compilation-targets/node_modules/lru-cache` |
| `lru-cache` | `11.5.2` | development | `node_modules/lru-cache` |
| `lz-string` | `1.5.0` | development | `node_modules/lz-string` |
| `magic-string` | `0.30.21` | development | `node_modules/magic-string` |
| `mdn-data` | `2.27.1` | development | `node_modules/mdn-data` |
| `min-indent` | `1.0.1` | development | `node_modules/min-indent` |
| `minimatch` | `10.2.6` | development | `node_modules/@eslint/config-array/node_modules/minimatch` |
| `minimatch` | `10.2.6` | development | `node_modules/eslint/node_modules/minimatch` |
| `ms` | `2.1.3` | development | `node_modules/ms` |
| `nanoid` | `3.3.20` | development | `node_modules/nanoid` |
| `natural-compare` | `1.4.0` | development | `node_modules/natural-compare` |
| `node-releases` | `2.0.57` | development | `node_modules/node-releases` |
| `obug` | `2.1.4` | development | `node_modules/obug` |
| `optionator` | `0.9.4` | development | `node_modules/optionator` |
| `p-limit` | `3.1.0` | development | `node_modules/p-limit` |
| `p-locate` | `5.0.0` | development | `node_modules/p-locate` |
| `parse5` | `8.0.1` | development | `node_modules/parse5` |
| `path-exists` | `4.0.0` | development | `node_modules/path-exists` |
| `path-key` | `3.1.1` | development | `node_modules/path-key` |
| `pathe` | `2.0.3` | development | `node_modules/pathe` |
| `picocolors` | `1.1.1` | development | `node_modules/picocolors` |
| `picomatch` | `4.0.7` | development | `node_modules/picomatch` |
| `playwright` | `1.64.1` | development | `node_modules/playwright` |
| `playwright-core` | `1.64.1` | development | `node_modules/playwright-core` |
| `postcss` | `8.5.32` | development | `node_modules/postcss` |
| `prelude-ls` | `1.2.1` | development | `node_modules/prelude-ls` |
| `pretty-format` | `27.5.1` | development | `node_modules/pretty-format` |
| `punycode` | `2.3.1` | development | `node_modules/punycode` |
| `qified` | `0.10.1` | development | `node_modules/qified` |
| `react` | `19.2.0` | application | `node_modules/react` |
| `react-dom` | `19.2.0` | application | `node_modules/react-dom` |
| `react-is` | `17.0.2` | development | `node_modules/react-is` |
| `redent` | `3.0.0` | development | `node_modules/redent` |
| `require-from-string` | `2.0.2` | development | `node_modules/require-from-string` |
| `rolldown` | `1.2.6` | development | `node_modules/rolldown` |
| `rolldown` | `1.2.15` | development | `node_modules/vite/node_modules/rolldown` |
| `saxes` | `6.0.0` | development | `node_modules/saxes` |
| `scheduler` | `0.27.0` | application | `node_modules/scheduler` |
| `semver` | `6.3.1` | development | `node_modules/semver` |
| `shebang-command` | `2.0.0` | development | `node_modules/shebang-command` |
| `shebang-regex` | `3.0.0` | development | `node_modules/shebang-regex` |
| `siginfo` | `2.0.0` | development | `node_modules/siginfo` |
| `source-map-js` | `1.2.2` | development | `node_modules/source-map-js` |
| `stackback` | `0.0.2` | development | `node_modules/stackback` |
| `std-env` | `4.2.0` | development | `node_modules/std-env` |
| `strip-indent` | `3.0.0` | development | `node_modules/strip-indent` |
| `symbol-tree` | `3.2.4` | development | `node_modules/symbol-tree` |
| `tinybench` | `2.9.0` | development | `node_modules/tinybench` |
| `tinyexec` | `1.3.0` | development | `node_modules/tinyexec` |
| `tinyglobby` | `0.2.17` | development | `node_modules/tinyglobby` |
| `tinyrainbow` | `3.2.0` | development | `node_modules/tinyrainbow` |
| `tldts` | `7.4.11` | development | `node_modules/tldts` |
| `tldts-core` | `7.4.11` | development | `node_modules/tldts-core` |
| `tough-cookie` | `6.0.2` | development | `node_modules/tough-cookie` |
| `tr46` | `6.0.0` | development | `node_modules/tr46` |
| `type-check` | `0.4.0` | development | `node_modules/type-check` |
| `undici` | `8.12.3` | development | `node_modules/undici` |
| `update-browserslist-db` | `1.3.3` | development | `node_modules/update-browserslist-db` |
| `uri-js` | `4.4.1` | development | `node_modules/uri-js` |
| `vite` | `8.3.5` | development | `node_modules/vite` |
| `vitest` | `4.1.12` | development | `node_modules/vitest` |
| `w3c-xmlserializer` | `5.0.0` | development | `node_modules/w3c-xmlserializer` |
| `webidl-conversions` | `8.0.1` | development | `node_modules/webidl-conversions` |
| `whatwg-mimetype` | `5.0.0` | development | `node_modules/whatwg-mimetype` |
| `whatwg-url` | `16.0.1` | development | `node_modules/data-urls/node_modules/whatwg-url` |
| `whatwg-url` | `17.1.0` | development | `node_modules/whatwg-url` |
| `which` | `2.0.2` | development | `node_modules/which` |
| `why-is-node-running` | `2.3.0` | development | `node_modules/why-is-node-running` |
| `word-wrap` | `1.2.5` | development | `node_modules/word-wrap` |
| `xml-name-validator` | `5.0.0` | development | `node_modules/xml-name-validator` |
| `xmlchars` | `2.2.0` | development | `node_modules/xmlchars` |
| `yallist` | `3.1.1` | development | `node_modules/yallist` |
| `yaml` | `2.9.1` | development | `node_modules/yaml` |
| `yocto-queue` | `0.1.0` | development | `node_modules/yocto-queue` |
| `zod` | `4.6.7` | development | `node_modules/zod` |
| `zod-validation-error` | `4.0.2` | development | `node_modules/zod-validation-error` |

## Inventory input fingerprints

These SHA256 values identify the source inputs used above. Any change requires a refresh; this document is manually maintained, with no automatic freshness gate claimed.

| Input | SHA256 |
| --- | --- |
| [package.json](../package.json) | `6e81d313b97be9d843b3a3547187bcdf2a28bb592a7b7585c1b9b06acdb42fc5` |
| [package-lock.json](../package-lock.json) | `afc7e3de7e7637e6158a449149e196c30542a32579ebfc7a7bf6de6b158f881d` |
| [backend/pyproject.toml](../backend/pyproject.toml) | `85aaa5e760bb7acf12fbd2a18e46bdb927d6d77368ef66780cf6b69cbdefaee9` |
| [backend/requirements.lock](../backend/requirements.lock) | `98d634b5342229a80ae1d17b330f95969076c5bd7eac0780eb59d5ce50d7e1a3` |
| [backend/requirements-test.lock](../backend/requirements-test.lock) | `3f233cce42b451c422ecc94b58546da782c6f92f2cb04ba1e335b3fc322e0e4a` |
| [backend/Dockerfile](../backend/Dockerfile) | `f1f5810efd4ac06b15b305ed4b88dc6667af6dcdd18ad30d5e5d34c770bfb87f` |
| [backend/compose.yaml](../backend/compose.yaml) | `5bcd4982a2c36fac48f59b2bf4ea72a713d7036e23db45eb2f4e36b9bb810a7b` |
| [backend/compose.browser.yaml](../backend/compose.browser.yaml) | `b0a7da6ed501b990f3536e3043b8a175fd53206d1e3d3fefcd744b9201f77a8a` |
| [backend/infrastructure/test-foundation.json](../backend/infrastructure/test-foundation.json) | `fc3671d622fce133ea5a2cec81d400e48de906269b2d61747aa61200b65bb5c1` |
| [.github/workflows/aws-image-accept.yml](../.github/workflows/aws-image-accept.yml) | `8cac2acb8dde0e980c70aac9dc286f97224e1695672511b759168a472c3f1fed` |
| [.github/workflows/aws-image.yml](../.github/workflows/aws-image.yml) | `53fd7514b330737ed79152df7afd64dd1d9902f527eed8b52ff68cb807177205` |
| [.github/workflows/aws-private-runtime.yml](../.github/workflows/aws-private-runtime.yml) | `a2d2b24bd9988c02c69085a58eefd2670ec2d3526c25f8a2059bb3b5cd159336` |
| [.github/workflows/aws-test-hosting.yml](../.github/workflows/aws-test-hosting.yml) | `39d5b78260e3c435460a81d16c2bab62a4106acfb22c7fbbf6a69c6db301d172` |
| [.github/workflows/aws-verify.yml](../.github/workflows/aws-verify.yml) | `dd35a9ec51f96c20b2e884f137cccc989dbce0e3be0a265506b6d0b2c5fc28e4` |
| [.github/workflows/infrastructure.yml](../.github/workflows/infrastructure.yml) | `f2c9c46692bd58d7806d2147d6a93cfe508473183a1220b6ee5e375c92b4a942` |
| [.github/workflows/pages.yml](../.github/workflows/pages.yml) | `43859f616032d14fad386850f0c17df3fbcdfcf4e5c6f0d9953897f42e34c558` |
| [.github/workflows/verify.yml](../.github/workflows/verify.yml) | `f01328b42a3b3b4642e9c8d3c8ed22ef05d093bd033e45a16db5217b4fa86923` |
