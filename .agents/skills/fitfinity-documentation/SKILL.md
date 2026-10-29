---
name: fitfinity-documentation
description: Reconcile Fitfinity documentation with source and verified evidence for every PR, CI outcome, merge, release and handover. Use when preparing or revising any PR, changing behavior/contracts/dependencies/infrastructure, reporting acceptance, or resuming work from a checkpoint.
---

# Documentation state reconciliation

## Purpose and authority

Keep every documentation owner's relevant state consistent with the actual change and available evidence. Apply this skill to **every PR, including documentation-only, dependency, workflow and automated update PRs**, and again when its delivery state changes. AGENTS.md is the engineering authority; explicit user instructions take precedence. This skill owns the reconciliation procedure, not business requirements, a second backlog or deployment permission.

Read root AGENTS.md, NORTH_STAR.md and PROGRESS.md first. Resolve all paths below from the repository root. Inspect source and actual PR/CI evidence before editing. A checked box, generated proposal or old receipt does not establish a current implementation or acceptance state.

Some hosts discover `.agents/skills/*/SKILL.md`; others do not. AGENTS explicitly directs readers here so the procedure remains available without automatic skill discovery. This is an instruction skill, **not a CI-enforced hook or unattended automation**. An agent must perform and report the checks.

## 1. Establish the change and checkpoint

1. Identify the current user request, repository, branch, base/head, working tree, preserved work and open PR. Preserve unknown edits and stashes.
2. Compare the entire PR against its actual base, not just the most recent commit. For a stacked PR, distinguish parent-branch implementation from accepted main.
3. Inspect affected source, tests, contracts and delivery workflow. Confirm which evidence applies to the exact head and which is historical.
4. Classify the change: behavior, API/schema, UI/role, architecture/security, dependency/runtime, data lifecycle, operational workflow, documentation or a combination. Use the owner map below for the impact review.
5. Identify state transitions explicitly: planned → implemented → tested → CI-verified → merged → deployed → accepted. Transitions may have different scopes; a synthetic-provider pass does not accept a real provider.

## 2. Review every owner; edit the affected ones

For every PR, review all rows for impact. Update every affected owner; leave unaffected content unchanged and explain that conclusion in the PR's concise documentation-state receipt. Do not make token edits to every file or copy the same status into several owners.

| Owner | Required reconciliation when affected |
| --- | --- |
| `PROGRESS.md` — every PR | Replace the current-task/leave-off checkpoint with actual outcome, branch/PR, tested/inspected source, validations, failures, blockers and next action. Move completed work out of the active queue; preserve remaining work and current campaign budget. Never accumulate competing “latest” notes. |
| `docs/journey.md` — every PR | Append a dated Singapore-time record of the material change, decision and available evidence. Preserve original failures and full historical content. A follow-up updates delivery evidence without rewriting an earlier event to pretend it already knew the outcome. |
| `AGENTS.md` | Update reading paths, unique owners and engineering instructions if tools, commands, permissions, document paths or ownership change. Do not silently broaden standing authority. |
| `NORTH_STAR.md` | Update only when the reusable campaign/loop/budget procedure changes. Active product status stays in Progress; avoid embedding each PR's checkpoint here. |
| `docs/business-rules.md` | Reconcile permanent requirements with the final behavior. Preserve BR IDs/anchors and link changed/new rules to code owners; move superseded implementation checkpoints to Journey. Do not silently change an undecided product policy. |
| `docs/api-contracts.md` | Reconcile operation status/evidence, actual methods/paths/schemas, authorization, errors and recovery. Refresh affected indexes/fingerprint from checked-in OpenAPI; schema-check examples and preserve synthetic-only data. Do not count endpoints or mocked tests as operation completion. |
| `docs/code-owners/index.md` and `technical-behavior.md` | Update moved/new owners, diagrams, named functions, visible behavior, guards, failure/recovery and evidence links. Every BR remains mapped to implementation or an explicit planned/operational owner. |
| `docs/architecture/adr.md` and `diagram.md` | Reconcile architecture choices, consequences, alternatives and topology/test-suite diagrams when boundaries or services change. Label proposed tools and unimplemented suites. |
| `docs/security.md` | Reflect actual controls/tools, trust boundaries, defaults, permissions and remaining gaps. Distinguish source configuration, deployed settings, audit results and expired exceptions. |
| `docs/data-lifecycle.md` | Reconcile storage/fields, browser copies, expiry, revocation, archival, physical cleanup, logs/backups/providers and policy gaps. Do not equate logical expiry with erasure or source cleanup with deployed scheduling. |
| `docs/development.md` | Update setup/runtime/verification commands and budgets when their executable owners change. Preserve isolated-data and environment boundaries. |
| `docs/runbook.md` | Reconcile operator steps, release/rollback compatibility, maintenance, monitoring and recovery. Keep proposed targets, unassigned responders and unexecuted restore/alert drills explicit. |
| `docs/versions.md` | Refresh affected manifests, locks, image references, browser engines, Action pins and fingerprints in the same PR. Keep deployed/OS values unknown unless observed. Security remediation is separate from optional upgrades and deployed patch acceptance. |
| `docs/uat/owner.md`, `admin.md`, `trainer.md` | Update affected role workflows, expected outcomes and permission boundaries. Preserve blank worksheet masters; never turn a newly drafted case into a completed physical/live test. |
| This skill | Reconcile the procedure and owner map if documentation ownership or delivery mechanics change; preserve its AGENTS entry point. |

A reviewer should be able to answer: **what changed, what is true now, what evidence supports it, what remains unverified, and where does the next developer resume?**

## 3. Validate the documentation delta

- Inspect the final diff for contradictions, duplicate instructions, stale filenames, accidental history/rule loss and misleading acceptance claims.
- Validate local links and anchors, including root docs and this skill. Check fenced blocks and GFM tables; render every changed Mermaid diagram. For a structural move or a requested full audit, include historical diagrams in Journey as well as current architecture diagrams.
- For contract changes, compare matrix/endpoint/schema references with actual source and validate example payloads against the owning schemas plus relevant domain restrictions. Placeholders must be unmistakable and must not contain real credentials or customer data.
- For code-owner changes, confirm named paths/functions exist and the behavior/guard/recovery description matches their implementation and evidence. A link existing alone does not prove the description.
- For rule moves, preserve stable IDs/anchors and all decisions; for history moves, compare retained content and record any purely syntactic rendering correction.
- For dependency changes, compare the inventory with manifests/locks/workflows; do not invent current vulnerability or deployed-image status without a receipt.
- Use meaningful existing checks and applicable complete gates under AGENTS. A documentation check does not replace required final-head frontend/backend/API-browser CI. Do not weaken assertions or rerun unchanged failures to obtain green.

Record actual commands/tools, source head, environment and outcome. If a check cannot run, say which one and why; do not call the review complete without the required evidence. An external link's existence or a local renderer pass does not prove GitHub's current UI or an external service's acceptance.

## 4. Keep delivery state current without an endless commit loop

| Event | Required action |
| --- | --- |
| Before first push / PR | Update Progress and Journey with the prepared change and completed local checks. Clearly mark CI, merge and external acceptance pending. Use the base/inspected SHA; a commit cannot contain its own final SHA. |
| PR created or revised | Put the PR number/head in the current handover when making the next meaningful update. Include a documentation-state receipt in the PR body. Any pushed documentation edit creates a new head that needs its own complete gates. |
| CI failure | Preserve the original run/job/artifact and failure scope. Diagnose before repair. Record unresolved findings in Progress/Journey with the next substantive update; meanwhile keep the exact status in the PR receipt and user report. A later pass does not retroactively explain the failure. |
| Final-head CI passes | Recheck exact SHA, all required gates and GitHub requirements. Record the immutable result in the PR receipt/user handover; do not amend the tested commit merely to insert “green” and invalidate it again. |
| Merge / fresh-main CI | Verify merge SHA and fresh-main result separately. Update the PR receipt/user handover immediately. Reconcile repository Progress/Journey in the next substantive authorized change, or a specifically requested documentation reconciliation PR. Never directly push main or recursively create “merged the status-update PR” commits. |
| Deployment / provider / UAT acceptance | Only after authorized execution, record exact environment/source/artifact, result and evidence in the appropriate owner. A source merge grants no new AWS or provider authority. |
| Pause / resume | State last-observed status and timestamp, pending facts and next action. Before new implementation, reconcile stale repository checkpoints against GitHub/source. Do not represent the last commit's checkpoint as live monitoring. |

“All states current” means each claim is accurate for its clearly stated observation point, and later evidence is discoverable from the delivery receipt until the next repository checkpoint. It does not mean every historical paragraph must be rewritten after every workflow event.

## 5. PR documentation-state receipt

Add a short paragraph or compact table to the existing PR description; follow its established structure instead of creating a second report. Include:

- **Updated owners:** paths and the state/behavior reconciled.
- **Reviewed unchanged:** grouped owners and why the change does not affect them.
- **Evidence:** checks actually completed, exact applicable source/run and preserved failures.
- **Pending:** CI/merge/main/deployment/provider/device/recovery states that are not yet accepted.
- **Next checkpoint:** concrete remaining action and where the next developer resumes.

For automated dependency PRs, perform this review before an eligible merge; the bot's release notes do not replace the version/security/runbook impact assessment. Do not mark the skill satisfied solely because Progress and Journey were touched while affected contracts, diagrams or version inventories remain stale.

## 6. Exit criteria

The PR is documentation-ready when all affected owners agree with the final source, permanent rules and acceptance evidence; unaffected owners have a reasoned no-change classification; validations passed; prior decisions/failures remain retained; and the current handover is usable. Overall merge readiness still requires AGENTS' complete final-head gates and GitHub requirements. Report incomplete or externally blocked work explicitly; do not invent acceptance to close a checklist.
