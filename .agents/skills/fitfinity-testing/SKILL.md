---
name: fitfinity-testing
description: Review and maintain Fitfinity tests, guards, fixtures and strict verifier inventories for every PR and behavior change. Use during implementation, bug repair, dependency/workflow updates, CI diagnosis and release preparation; record test impact and exact evidence before publication.
---

# Test maintenance and evidence

## Authority and scope

Apply this procedure to every PR, including documentation-only, dependency, workflow and automated updates, and repeat the impact review when scope changes. Read root AGENTS.md, NORTH_STAR.md and PROGRESS.md first; paths below are repository-root relative unless explicitly linked. AGENTS owns engineering rules and permissions. Explicit user instructions take precedence. The documentation skill owns document state, and the campaign guide owns work budgets. This skill owns test-impact review and evidence quality, not business policy or deployment authority.

Review tests during implementation and before publication, not only after merge. This is an instruction skill, **not an automatic CI hook**. Existing verifiers enforce declared inventories/outcomes but cannot prove that every changed behavior has a meaningful assertion. Include a review receipt in the PR. AGENTS directs agents here explicitly if automatic repository-skill discovery is unavailable.

Fitfinity permits Codex to run Playwright and inspect isolated internal previews. Use synthetic records, isolated Docker PostgreSQL/object storage and the local signed-token Cognito substitute. Never use production PostgreSQL or real customer data for routine tests. Real Cognito/email/invitations, AWS changes, image publication, deployment, provider operations and production load require their own authority. Local emulation, simulator browsers, real-API browsers, process restart, authoritative macOS/WebKit CI, physical devices and deployed acceptance are distinct evidence scopes. Do not copy SoccerBot's owner-only browser restriction or its Worker/provider architecture.

## 1. Map the whole change to existing tests

1. Inspect the full PR diff against its actual base, exact source head, working tree and relevant CI receipts. Identify inherited changes in a stacked PR separately. Preserve unknown edits and original failures.
2. Identify each changed behavior/guard/contract using docs/business-rules.md, docs/api-contracts.md and docs/code-owners/index.md plus technical-behavior.md. Trace callers, UI state, adapters, API schemas, models/migrations, configuration and storage/provider boundaries; filename matching alone is insufficient.
3. Search existing tests by operation, function, route, state, error and business-rule meaning. Read assertions, fixtures and setup. A matching test title or endpoint count is not coverage evidence.
4. Assign every affected behavior a disposition: **add**, **update**, **retain with evidence**, or **remove with replacement/retirement justification**. Identify concrete test paths/titles and independent expected outcomes. Close missing coverage or record it as a readiness blocker.
5. Inspect the following owners and extend existing suites rather than creating duplicate harnesses.

| Change surface | Test and verification owners to inspect |
| --- | --- |
| Browser domain rules, services, React state and components | Colocated `src/**/*.test.js` / `src/**/*.test.jsx`, shared fixtures and Vitest configuration; `scripts/verify-test-results.mjs`. |
| Navigation, layout, PWA, exports and simulator contracts | `tests/*.spec.js`, Node API fixtures, `playwright.config.js`, build/PWA helpers. Preserve relevant root/Pages/API-fixture and desktop/phone/tablet coverage; simulator writes do not prove database persistence. |
| Browser-to-database behavior | `tests-api/*.spec.js`, `tests-api/fixtures.js`, `playwright.api.config.js`, `backend/tests/browser_server.py`, `backend/compose.browser.yaml`, `scripts/verify-api-browser.mjs` and `scripts/verify-api-shards.mjs`. Exercise real UI/HTTP/migrations/PostgreSQL and protected-media storage. |
| API authorization, persistence, concurrency and migration compatibility | `backend/tests/test_*.py`, actual domain/HTTP fixtures, `backend/tests/test_process_restart.py`, `backend/scripts/verify.py`, `scripts/verify-backend.mjs` and backend Compose/Docker owners. Use actual isolated PostgreSQL, not a SQLite replacement or mocked transaction result. |
| Infrastructure/configuration/artifact/release behavior | `backend/infrastructure/verify-*.py`, related fixtures/tests, `backend/scripts/verify-infrastructure.py`, `scripts/verify-infrastructure.mjs` and workflow owners. Tests are offline; actual infrastructure execution is separate. |
| Tooling, lint/source health and result verifiers | `scripts/*.test.mjs`, `scripts/verify-quality.mjs`, `scripts/verify-code-health.mjs`, result/shard verifiers and `.github/workflows/verify.yml`. Preserve wrong-source/resource, incomplete execution and checker-rejection cases. |
| Dependencies/runtime/container/browser updates | Affected consumers and compatibility suites, lockfiles, build paths and all required CI. An unchanged application diff does not imply no runtime risk. Distinguish security remediation from optional upgrades. |
| Documentation-only or low-impact prose/presentation | Validate affected links, schemas/examples, diagrams, tables and preservation. Explain why executable assertions/fixtures/inventories remain valid; do not invent tests or change unrelated expectations just to satisfy this skill. |
| Planned mutation, latency/load, observability and recovery work | Review H1–H6 in Progress and the full-suite diagram before claiming a tool or command exists. These planned campaigns are not implemented suites merely because the backlog describes them. Use a separately scoped implementation and synthetic isolated targets. |

## 2. Establish meaningful acceptance before changing expectations

For a defect, preserve its original run/job/artifact or reproduce it in an authorized isolated check. State the independently expected behavior and suspected mechanism. Where practical, demonstrate that a regression assertion fails on old behavior and passes after the repair. If the failure is not reproduced or requires a different browser/environment, report that limitation rather than claiming a fix from a later pass.

Select relevant cases by risk instead of mechanically copying this list into every PR:

- Intended results, boundaries and invalid inputs; verify database changes and protected non-effects, not only status 200 or a toast.
- Owner/Admin/Trainer authority, current assignment, inactive records, foreign clients/purchases/people, expired/revoked identity, CSRF and sensitive-data exposure. Include foreign records so filtering assertions can detect leaks.
- Concurrent Owner/Admin or Trainer edits, stale reviewed versions, duplicate keys and changed intent, late replies, lost responses, interrupted writes, actual process restart and original-actor receipt recovery where applicable.
- UI writes followed by reload or a fresh authenticated browser context; verify durable records, not a retained React snapshot or simulator store. Confirm that Check reads receipts without replacement writes and that failed refresh does not undo a committed save.
- Session scheduling/proposals/approval, current versus historical Trainer authority, immutable purchased terms and attribution, signatures, exactly-once credits, approved remuneration and domain-specific permitted Undo.
- Initial 11 assessment forms denied to Trainers versus assigned general notes; per-person/couple scope, immutable revisions and explicit correction/void behavior.
- Media intent/upload/commit boundaries, checksum and post-IO authority checks, expiry versus physical deletion, cleanup leases, original bytes/ownership and retained Undo windows. Do not infer processing/capture compliance from client metadata.
- Browser editor lifetime, cancellation/unmount, background refresh, navigation/focus, privacy retirement, PDF generation/export and perceived lag. Arm event listeners before the action; a network response alone does not prove React state has settled.
- Additive/populated migration compatibility, outgoing application behavior, safe reruns, rollback constraints and wrong-target rejection for storage/release changes. A worker crash/restart test is not a backup-restore drill.

Derive expected results from rules/contracts or independently constructed fixtures, not the implementation calculating its own expected answer. Avoid tautological assertions, blanket snapshots and arbitrary coverage thresholds. Existing adequate coverage may remain unchanged with a specific explanation; small reversible low-impact changes need not create a new test.

If requirements legitimately change, update obsolete assertions and fixtures in the **same PR**, explaining the old/new contract. If requirements do not change, repair the defect rather than rewriting expectations. Removing/renaming a test must preserve its behavioral coverage or explain authorized retirement. Retain original failures in Journey under the documentation skill.

## 3. Synchronize fixtures and strict inventories

Fixtures must represent valid and deliberately invalid domain states, current role/assignment, bounded clocks and real persistence constraints. Synthetic Cognito still exercises JWT verification/cookies/CSRF; it does not establish provider delivery. Keep simulator fixtures aligned with supported contracts without treating their responses as real PostgreSQL acceptance. Each isolated run/shard owns its disposable data/resources; cleanup must not target unrelated databases or containers.

Fitfinity does **not** use SoccerBot's `test-inventory.json` or Worker inventory. Inspect the actual current inventory owners:

| Owner | What must remain synchronized |
| --- | --- |
| `scripts/verify-test-results.mjs` and its regression tests | Declared unit file/case totals and browser/API-browser totals; actual Playwright discovery checks both browser inventories, including navigation-generated cases; rejection of failed, skipped, retried/flaky, interrupted and incomplete output. Totals alone do not establish behavioral coverage. |
| `scripts/verify-api-shards.mjs`, its tests and `verify.yml` | Shared API-browser count in `verify-api-shards.mjs`, consumed by text receipts and checked against actual Playwright discovery in the quality suite; two complementary shard reports, exact case identity and complete execution once. Preserve worker/retry/repeat settings and shard-success requirements. |
| `backend/scripts/verify.py` | Backend collection/execution acceptance and declared constraints; inspect its actual collection/report checks before changing tests. |
| `backend/scripts/verify-infrastructure.py` | Explicit suite/file inventories and per-suite case counts, including rejection of skips and expected failures. |
| Playwright/Vitest/pytest configuration and owning harnesses | Project, fixture, collection, isolation and timeout behavior; do not silently omit a device, file or runtime path. |

When adding, renaming, moving or retiring tests, update every affected verifier expectation and its regression tests in the same PR. Compare discovered and executed cases, not just unchanged totals. Do not regenerate a reduced inventory to conceal missing tests or change checker expectations to accept a failure.

**Required guard impact review.** For every change, identify all guards that enforce the affected contract, including indirect callers. Give each an update or retain-with-evidence disposition in the PR; update necessary guards, fixtures and checker regressions in the same PR, not as a forgotten follow-up.

| Guard family | Required review and evidence |
| --- | --- |
| Runtime authority and lifecycle | Server authorization, assignment/active-state checks, versions, idempotency, receipt recovery, editor/review lifetime and post-IO checks. Test allowed behavior and rejected stale/foreign/retired behavior; UI guards never replace server authority. |
| Schema, migration and artifact compatibility | Request/response validation, OpenAPI agreement, migration readiness and outgoing-runtime/source/artifact compatibility. Update guards only for an intentional contract change, preserving wrong-version/resource and populated-data rejection. |
| Verification and collection | Result totals, shard identity/completeness, backend/infrastructure inventories, lint/source-health constraints, forbidden patterns and quality-checker regressions. A new valid case must pass while incomplete/skipped/duplicated or otherwise invalid evidence still fails. |
| Environment and delivery | Isolated database/storage targets, readiness checks, credential/data boundaries, workflow source bindings and protected release gates. Preserve failure paths and required approval boundaries; a new fixture must not silently bypass the production guard it exercises. |

Inspect executable owners before editing counts, allowlists, thresholds, fingerprints or exclusions. A legitimate test addition or architecture change may require a narrow guard update with its rationale and positive/negative regression evidence. A guard rejecting a defective candidate is not an obsolete guard. Never loosen a limit, broaden an allowlist, skip a checker or recalculate expected evidence merely to accept the failing output. If no guard update is necessary, identify the relevant existing guards and why they remain valid.

For setup races, wait on the actual observable prerequisite before dependent assertions. Verify listeners match the intended request/attempt. Never use fixed sleeps, retries, forced clicks, skipped/exclusive cases, relaxed assertions, inflated timeouts or reduced device scope to obtain green. Investigate whether an event indicates dispatch, completion or only an intermediate state before choosing the wait.

## 4. Execute, diagnose and keep evidence bounded

Use docs/development.md's verification commands and inspect executable harnesses before selecting focused work. Run the smallest meaningful checks, then applicable complete gates at a coherent candidate boundary. A filtered test or one API shard is not full acceptance. Reuse matching dependencies, images/browser caches and evidence; do not repeatedly run unchanged suites without a relevant change or new diagnostic evidence.

Classify failures as application, test/fixture, environment, provider or unresolved. Save the first failure with source, command/run, environment, test title, expected versus observed state and available logs/traces. A passing rerun alone does not prove “flaky,” identify a root cause or repair the original defect. For perceived slowness, record first/repeat timing and where time is spent; do not loosen the timeout to hide it. Fix the owning cause and review adjacent coverage.

**Recurring or frequent failures.** Search retained Journey entries, CI jobs/artifacts and adjacent tests before treating a failure as new. A second comparable occurrence triggers an explicit recurring-failure investigation; similar error text alone does not establish the same root cause. Record each source/run/test/project, stage, timing, expected/observed state and relevant runtime/fixture/load differences. Report observed failures and inspected runs together when describing frequency; do not invent a failure rate from a few anecdotes.

Compare the first and latest traces/logs and test isolation, clocks, shared state, dependency startup, transport, resource pressure and browser/render lifecycle. Separate slowness, missing readiness and application deadlock from an arbitrary timeout label. Form a bounded reproduction or fault-injection hypothesis using synthetic isolated targets; record cases that cannot be reproduced. Change the owning cause and any affected guards, then verify the regression and a relevant adjacent/concurrent scenario. Broader repetition must have a stated diagnostic purpose and campaign budget, never “repeat until green.”

Keep the recurring issue in Progress with the next diagnostic step and link durable occurrences/repair evidence in Journey. Mark it fixed only with a causal explanation and relevant verification; otherwise retain it as unresolved even after a passing run. Recurring unresolved failures that undermine the candidate's required acceptance remain readiness blockers; unrelated historical findings keep their recorded scope. Do not quarantine, skip, add retries, inflate timeouts, reduce parallel/device coverage or weaken assertions to hide recurrence. Escalate the missing evidence or environment constraint when the bounded investigation cannot advance.

Fitfinity requires all three exact-final-head gates: **`verify / frontend`, `verify / backend`, `verify / api-browser`**, including successful API shards/aggregate and authoritative macOS/WebKit checks. Recheck complete outcomes and SHA before an authorized merge. Current workflow limits are per job: 60 minutes frontend/backend, 20 per API shard and 5 for aggregation; inspect actual source if they change. Campaign budgets do not override test/CI budgets.

Keep local simulated-provider acceptance separate from real Cognito, current physical devices, AWS image publication, Lambda rollout and deployed recovery. Fresh-main verification is separate from PR success. No test-suite command grants permission to invoke real invitations, send customer messages or exercise production storage.

## 5. PR test-impact receipt and handover

Add a concise paragraph/table to the existing PR body alongside the documentation-state receipt:

| Field | Evidence to include |
| --- | --- |
| Behavior / risk | Changed BR, operation or boundary and the independently expected result. |
| Test disposition | Concrete paths/titles added, updated, retained or retired with rationale; justify no test changes for documentation-only work. |
| Fixtures / inventories / guards | Exact owners updated or retained, rationale, positive/negative checker evidence and why discovered/executed coverage and declared constraints agree. |
| Verification | Actual commands/run links, source/environment and outcomes; distinguish focused local checks from complete CI and real provider/device evidence. |
| Failure / gaps | Original and recurring failure receipts, inspected occurrence count/conditions, causal diagnosis or unresolved hypothesis, blocked checks and missing acceptance. |
| Next action | Current readiness and remaining verification; no invented success or unattended monitoring. |

Use Progress for the current task and Journey for durable receipts under the documentation skill. After a final-head pass, update the PR/user receipt rather than repeatedly committing “green” and invalidating that head. Apply the same review to Dependabot updates before merge; release notes and green badges do not replace a test-impact assessment.

## Exit criteria

Every changed behavior has a justified test disposition; affected assertions, fixtures and verifier inventories agree with the intended contract; relevant negative/concurrency/recovery cases are covered or explicitly blocked; actual checks have recorded outcomes; no coverage was weakened. Publication may precede CI completion; merge readiness cannot. This discipline improves evidence quality but does not certify exhaustive coverage or an error-free application.
