---
name: fitfinity-ci-diagnosis
description: Diagnose Fitfinity CI failures and resource inefficiency from preserved exact-run evidence. Use for failing, skipped, queued or duplicate jobs, PostgreSQL/disk/memory pressure, fixture cleanup races, stale guards, shard coverage and runner/billing issues; consolidate repairs without weakening tests.
---

# CI failure diagnosis and efficiency

## Authority and owners

Read [AGENTS](../../../AGENTS.md), [North Star](../../../NORTH_STAR.md), [Progress](../../../PROGRESS.md), the [verification guide](../../../docs/development.md#verification-commands), actual workflows and relevant runners. Apply the [testing skill](../fitfinity-testing/SKILL.md) for acceptance, dependent guards, fixtures and inventories, and the [documentation skill](../fitfinity-documentation/SKILL.md) for evidence and handover. Use the [dependency skill](../fitfinity-dependencies/SKILL.md) when package/runtime compatibility is involved and the [deployment skill](../fitfinity-deployment/SKILL.md) for release/configuration effects.

This skill owns diagnosis, experiment selection and CI resource assessment; it does not duplicate test contracts or runner commands. Follow existing authorization, preserve explicitly protected runs and unknown local work, and do not change billing, runner plans, credentials, protection or deployment policy merely to unblock CI. Fitfinity permits assistant-run isolated Playwright checks using synthetic records, Docker PostgreSQL/object storage and the local signed-token Cognito substitute. Never connect routine tests to production PostgreSQL or invoke real provider/customer effects. Authoritative macOS/WebKit CI and physical-device acceptance remain separate. This is an instruction source, not a standing monitor or automatic Actions summary.

Adapted from the [SoccerBot CI diagnosis skill](https://github.com/soccerbotstudiosg/soccerbotstudioSG/blob/docs/dependency-review-skill/.agents/skills/soccerbot-ci-diagnosis/SKILL.md), inspected2 November2026. Fitfinity instructions and actual workflows govern.

## 1. Establish which run and what actually failed

Capture repository, workflow/event, PR/branch, exact source SHA, target/profile, run ID, attempt, job/matrix shard, timestamps and conclusion. Match the head to the current PR before calling it final. Distinguish old/superseded runs and jobs with similar names; trace reusable workflows and triggers before claiming duplicate execution.

Read job logs and relevant reports/receipts, not just the red badge. Locate the earliest causal failure and any independent failures; downstream skipped gates or missing artifacts can be consequences. An intentionally skipped deploy is different from a failed verification. A queued job or a billing/permission rejection that never started is not a test failure. Verify runner labels, image/version and resource evidence rather than inferring public/private repository hardware from visibility alone.

Retain original logs, artifacts and failure context. Redact credentials and customer data from any diagnostic excerpts. Establish the expected outcome from the owning contract and describe observed behavior. Separate evidence, hypothesis and unknowns; a successful rerun alone does not explain a previous failure or establish flakiness.

## 2. Classify before choosing a repair

| Class                           | Evidence and owning repair                                                                                                                                                                   |
| ------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Application defect              | Actual behavior violates the business/API contract. Fix the owning source and meaningful regression.                                                                                         |
| Test or fixture defect          | Setup, clocks, isolation, synthetic provider behavior or teardown differs from the intended scenario. Repair the fixture while preserving assertions and coverage.                           |
| Guard or evidence defect        | Tests pass but discovery/order/counts, shard receipts, report schema, fingerprint or artifact aggregation disagree. Reconcile the owning guard and prove invalid evidence is still rejected. |
| Dependency/environment mismatch | Lockfile, package APIs, Node/browser image, native libraries or external bootstrap differ. Research compatibility and repair the actual owner.                                               |
| Resource/lifecycle failure      | Measured disk, tmpfs, inode, memory, process or open-handle pressure explains the error. Locate allocation and teardown ownership before changing limits.                                    |
| Infrastructure or account issue | Logs show service outage, download/rate-limit failure, runner availability, permission or billing rejection. Keep platform remediation separate from source changes.                         |
| Unresolved                      | Record competing explanations and the smallest experiment that discriminates them. Do not force a convenient classification.                                                                 |

## 3. Investigate resource and lifecycle failures

For PostgreSQL storage/connection failures, browser crashes or similar failures, locate the affected container, database, process and mount. Inspect connection-pool utilization, active transactions/locks and readiness before attributing a timeout to insufficient hardware; use only the isolated test environment for routine probes. Inspect available bytes/inodes, tmpfs capacity, memory limits, database/journal/WAL growth, temporary files, process counts and open/deleted file descriptors where authorized and available. Distinguish peak within a case from cumulative growth between cases. Free space after cleanup does not prove there was adequate space at the failure; missing counters mean unknown, not zero.

Inspect the complete lifecycle: runtime construction, browser/FastAPI processes, storage handles, callbacks, timers/background tasks, pending requests and final disposal. Deleting a pathname may leave disk allocated while a process holds the file open. Disposal calls do not prove awaited shutdown or OS resource release. A smaller filesystem/tmpfs is a bound, not additional capacity; check memory consequences before moving storage there. Preserve evidence rather than deleting arbitrary files or state to produce a pass.

Check route/event and teardown ordering against the actual dependency API. Stop scenario traffic, await owned work and dispose in a justified order; do not suppress all cleanup exceptions or broadly ignore route errors. Reproduce lifecycle bugs with a controlled non-browser regression where possible, then exercise the isolated browser/API path and authoritative CI where relevant. Fix the cause before proposing a larger runner; paid GitHub plans, spending budgets, concurrency allowances and larger-runner hardware are separate decisions with separate costs.

## 4. Preserve test meaning while optimizing

Keep these execution models distinct:

- Independent tests need isolated storage and predictable fixtures; grouping alone does not repair shared state.
- Journey/concurrency scenarios retain the same runtime and storage for the whole scenario, including overlapping operations, retries and recovery.
- Restart scenarios deliberately replace the runtime while retaining durable storage. Browser reload, fixture reconstruction, actual API process restart and deployed Lambda/database recovery are different evidence; never erase the state under test to lower resource usage.

Shard at independent case/suite boundaries, not inside a journey. Rebalance from measured duration and peak resources while preserving sustained-runtime and restart coverage. Bound browser/runtime lifetimes between independent cases where appropriate; do not periodically restart the very scenario intended to detect sustained-state failures. More shards may reduce elapsed time while increasing total runner minutes, setup/download cost and resource contention. Compare both wall time and total cost before recommending expansion.

Under the testing skill, verify the complete discovered and executed file/title set and order, not counts alone. Preserve device/engine coverage, zero-retry policy, timeouts, strict guards and rejection of missing/duplicate/skipped/failed/foreign-revision evidence. Check build-once artifact consumers, per-shard receipts, grouping policy and final aggregation. Do not edit thresholds, inventory or assertions merely to make the badge green.

Fitfinity’s required gates are `verify / frontend`, `verify / backend` and `verify / api-browser`. Inspect the current workflow budgets: presently60 minutes each for frontend/backend,20 minutes per API shard and5 minutes for aggregation. The two API shards must succeed and the aggregate must verify complete case identity exactly once. Result/shard owners are scripts/verify-test-results.mjs and scripts/verify-api-shards.mjs; quality/source-health and dependency checks have their own negative regressions. Do not change counts without legitimate coverage changes. A Pages publish skipped on a PR is expected; an AWS image approval is not an application test and must not be approved merely to clear a queue.

## 5. Use bounded experiments and consolidate repairs

1. State the hypothesis, original failure, discriminating observation, affected scope and resource budget under North Star. Inspect all available failed jobs before assuming one repair covers everything.
2. Run the smallest meaningful permitted check. Where practical, prove the regression fails before and passes after the repair. Replay retained exact evidence for a guard-only defect when valid; source/runtime changes need new execution.
3. Review adjacent fixtures and dependent guards using the testing skill. Consolidate known source, tooling, environment and documentation repairs before another expensive full CI run. Do not issue unchanged reruns to hunt for green or repeatedly install matching dependencies.
4. If an infrastructure failure is evidenced and recovered, a scoped rerun may be justified; record why, retain the first failure and distinguish the new attempt. A partial rerun is not complete final-head acceptance until all required evidence is present and release rules accept it.
5. Inspect active, pending and superseded runs before managing them. Preserve explicit user instructions to let a run finish or leave it untouched. Any authorized cancellation must preserve available evidence and must not be represented as a successful run; unavailable cancellation tools are not a reason to bypass access controls.
6. Recheck the exact head and every required gate after completion. Distinguish PR verification, main verification, staged release and production deployment. Report remaining failures or blockers without weakening the release rules.

Upstream-supported ranges, repository-selected versions/profiles and observed test coverage are different claims. Use the [development coverage matrix](../../../docs/development.md#browser-testing-coverage) and exact runner/browser evidence; do not turn two passing endpoint versions into a continuous tested range or label emulation as a physical device.

## 6. Diagnosis and handover receipt

Record the original run/job/case and artifact links; expected versus observed behavior; confirmed cause and unresolved hypotheses; changed owner and why it is correct; regression/guard evidence; resource and timing measurements where relevant; final source/run/attempt and gate results; and the next action. Use the existing PR description and Progress/Journey owners, not a separate permanent incident ledger. A later pass cannot erase the original failure. Report any unverified platform/provider or resource limit explicitly; do not promise future CI cannot fail.
