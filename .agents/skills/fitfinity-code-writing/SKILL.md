---
name: fitfinity-code-writing
description: Write and review Fitfinity code by fixing the owning cause, avoiding layered workarounds and hardcoded business or environment values, and proving intended behavior with the existing guards and tests.
---

# Code writing and repair

## Authority and scope

Apply before application, service, FastAPI, styling, configuration or tooling changes and during code review. Read [AGENTS](../../../AGENTS.md), [North Star](../../../NORTH_STAR.md), [Progress](../../../PROGRESS.md), then the affected business rule, contract and [code owner](../../../docs/code-owners/index.md). Inspect current source, branch/head and preserved edits; do not infer current behavior from old chat or a historical skill.

AGENTS and explicit user instructions govern permissions. This skill does not authorize publication, merge, deployment, live provider effects or browser execution. Use the [testing](../fitfinity-testing/SKILL.md) and [documentation](../fitfinity-documentation/SKILL.md) skills; use the dependency skill when dependencies change. This is an instruction procedure, not a newly installed automated guard.

## 1. “Do not patch”: repair the owning cause

“Patch” here means a symptom-hiding workaround layered over faulty behavior. It does not prohibit small diffs, Git patches, or the apply_patch editing tool. Prefer the smallest complete correction that preserves the contract.

Before editing, identify the expected behavior, observed failure, causal path, authoritative owner and affected callers. Distinguish a product defect from obsolete tests, invalid fixtures, provider failure or missing configuration. If the cause is uncertain, gather discriminating evidence rather than guessing a repair.

- Edit the existing component, service, state transition, adapter or style owner. Remove superseded logic and update its callers in the same change. Do not add `Fixed`/`V2` duplicates, parallel state, injected DOM repairs, CSS override tails or wrapper chains that leave the original defect active.
- Do not hide failures with catch-and-ignore, success-shaped fallback data, frontend approval or credit assumptions, arbitrary delays, repeated verification calls or broad retry loops. A retry requires the operation's documented idempotency, bounded policy and preserved attempt identity.
- Preserve server authority, ownership, correlation of late responses, expiry, scheduling conflicts, purchased terms and duplicate-effect protection. Fix every affected path, including reload, return, recovery and consecutive sessions/purchases; a normal first journey alone is insufficient evidence.
- Legitimate boundaries remain valid: adapters translate external contracts, caches improve reads, and compatibility paths support a documented requirement. They must have one owner, explicit entry/exit conditions and meaningful coverage; remove obsolete paths when support ends.
- Avoid speculative rewrites or generic frameworks. If a temporary mitigation is necessary, record its evidence, limitation, owner, removal condition and regression coverage in the existing PR/Journey. Do not present it as a permanent root-cause repair or silently relax a guard.

## 2. “Do not hardcode”: choose the authoritative source

Hardcoding means embedding a value where it can disagree with the environment, provider, approved business configuration or authoritative state. Not every literal is hardcoding. Naming a copied value as a constant does not fix the source-of-truth problem.

| Value                                                                       | Required owner / treatment                                                                                                                               |
| --------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Secrets and credentials                                                     | Existing server-side secret bindings; never source, browser bundles, fixtures, logs or documentation                                                     |
| Staff/provider IDs, package terms, eligibility and media identities       | Existing validated configuration/provider contract; preserve returned identifiers, never guess prefixes or substitute a production fixture               |
| Environment origins, account/resource IDs, return URLs and feature switches | Reviewed target manifests/configuration and existing URL builders; validate at the boundary; no scattered staging/production branches                    |
| Approved business limits, lead times, Undo/recovery windows and timezone       | Existing business/domain/configuration owner, with units and rationale; server enforces writes; do not create a competing UI constant                    |
| Customer copy, contact information and visual styles                        | Existing content/component/style owners; avoid duplicating shared values across screens or embedding operational state in customer messages              |
| Protocol constants, enum values and stable algorithms                       | Explicit literals or named constants are appropriate when contract-defined; extract only when it improves meaning or prevents drift                      |
| Dependency, runtime and Action versions                                     | Keep reviewed exact pins and lockfiles; apply the dependency skill, do not replace pins with “latest” to avoid hardcoding                                |
| Test expectations and fixtures                                              | Independent, explicit synthetic values are appropriate; never compute the expected result using the implementation under test or copy real customer data |

Trace each changed value to its source and consumers. Use the existing configuration mechanism rather than adding an environment variable for every literal. Validate required values and fail clearly when absent; do not silently fall back to demo, stale cached authority, a different provider or an invented default. Defaults are acceptable only where the contract explicitly permits them.

Do not turn workflow versions or strict inventories into unexplained magic counts. Use authoritative enumeration where designed, while retaining independent expected counts/fixtures when they deliberately detect missing execution. Update all affected discovery, ordering, aggregation and rejection guards together.

## 3. Prove behavior and guard execution

State independently what must happen and what must not happen. Assert the positive result and relevant state/effects, together with negative safety assertions. “No error text” or exit status alone cannot prove the operation occurred. For purchases/credits/recovery, retain original attempt identity, receipt ownership and effect-count assertions.

Use the [testing skill's regression-evidence procedure](../fitfinity-testing/SKILL.md#prove-the-test-can-detect-the-defect) for bounded pre-fix/mutation proof, legitimate execution limitations and positive/negative assertions. Its [dependent-guard review](../fitfinity-testing/SKILL.md#required-dependent-guard-review) owns proof of actual guard execution, committed executable modes and rejection of missing/skipped evidence. A present test or hook is not proof that it runs or detects the defect. Use this repository's actual tools, not commands copied from another project.

Preserve failures. Never weaken assertions, add sleeps/retries, force clicks, enlarge deadlines, drop cases or bypass guards to obtain green. Intentional animations may be synchronized through their actual lifecycle before measuring final geometry; preserve the size requirement and confirmation timing assertions.

## 4. Review before publication

Review the full candidate, not just the latest hunk:

1. Does each change correct the owning cause without leaving a competing implementation?
2. Are business/environment/provider values read from their correct owner, with secrets kept server-side?
3. Are unchanged invariants preserved through alternate, failed, stale and consecutive flows?
4. Are callers, copy locators, fixtures, titles, inventories and all dependent guards reconciled?
5. Do checks prove intended outcomes and actual execution? Record local, CI, provider and physical evidence separately.
6. Are code owners, contracts, scenarios and acceptance docs updated only where affected? Progress holds the latest checkpoint; Journey holds dated evidence.

Keep related work on the current appropriate branch/PR, consolidate before expensive CI and preserve existing publication/merge authority. Record a concise root-cause/owner, value-source, test-impact and remaining-risk summary in the existing PR description; no separate checklist document is required.

## Fitfinity boundaries

Use FastAPI/PostgreSQL transactions and the existing service adapters as authoritative owners. Keep original command keys, reviewed versions, per-package Trainer assignment, credit accounting and private media scope intact. Do not add implicit demo fallbacks or use cached client state as write authority. Apply the existing three exact-head CI gates; source merge, AWS deployment, Cognito/provider effects and physical-device acceptance remain distinct. Isolated browser execution is permitted under AGENTS. No additional worktree or agent is authorized by this skill.
