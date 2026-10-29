# Campaign operating guide

Use this file as a reusable, skill-like procedure for sustained engineering work. It defines how to scope a campaign, run a bounded Ralph loop, manage budgets and hand over evidence. It is a Markdown instruction source, not an installed skill, background agent, scheduler or executable loop. Read it through [AGENTS.md](AGENTS.md), which remains the authority for engineering rules and permissions. Explicit user instructions take precedence.

## 1. Activate and establish the checkpoint

Use this procedure for a feature, audit/repair campaign, integration, documentation refactor or release preparation that needs several verified iterations. A small correction needs only the applicable steps; do not create a campaign bureaucracy for a one-line fix.

Read AGENTS → [Progress](PROGRESS.md) → the relevant business rules, API contracts and code owners linked from AGENTS. Inspect the existing checkout, unknown edits/stashes, current main, active PRs, exact source head and CI. Establish the user's intended outcome and already-granted authority before acting. Historical receipts are evidence, not current configuration or standing permission to repeat provider operations.

In Fitfinity, Progress owns the active outcome and campaign, [Journey](docs/journey.md#full-milestone-roadmap) owns milestone scope/history, and [API contracts](docs/api-contracts.md#domain-operation-inventory) owns the 55-operation acceptance matrix. Do not recreate another feature backlog or status ledger here. When adapting this guide to another project, first map these owners, commands and permissions to that project; Fitfinity's authority and technology choices do not transfer.

## 2. Define one campaign

Record the following compact campaign contract inside Progress's current task, using existing headings/tables where practical. Resolve routine choices from source and current instructions; ask only for missing decisions that materially affect the work.

| Field | Required content |
| --- | --- |
| Identity and outcome | Campaign name; one observable result; target feature/domain and relevant BR/contract IDs. |
| Starting evidence | Repository, branch/base/head, current behavior, failed receipt or accepted baseline; preserve unknown local work. |
| Scope and exclusions | Included operations/files/roles; dependencies; external effects that are outside current authority. |
| Acceptance | Independent expected behavior, negative/concurrency/recovery cases, evidence environment and required complete gates. Define what would falsify success. |
| Work queue | Ordered, bounded slices with owning modules and evidence needed; investigate the highest-impact ready item first. |
| Budget | Iteration/time limits, expensive validation plan, available resource/cost authority and explicit exceptions to defaults below. |
| Delivery | Intended PR boundary, review/merge requirements, source/artifact bindings and separate deployment/provider/device acceptance. |
| Stop/handover | Completion criteria, concrete blockers, unresolved decisions and the next action if interrupted. |

Keep one active campaign and one coherent slice in progress. New findings enter the current scoped queue or the existing remaining-work backlog; discovery does not automatically authorize unrelated implementation. Preserve the original objective when the user provides corrections or asks for status.

## 3. Ralph loop specification

A Ralph loop is an evidence-driven repetition of the following steps during the active session. It must make measurable progress; it is not “rerun until green” or a promise of an error-free system.

1. **Observe:** select one ready queue item. Read its owner and current evidence; reproduce a defect or define the independent acceptance probe before changing behavior.
2. **Hypothesize:** state the suspected cause or intended behavior, smallest useful change and expected evidence. Distinguish application, test fixture, environment and provider failures.
3. **Act:** implement the bounded change in its canonical owner. Preserve current authority, persistence, concurrency and recovery invariants under AGENTS and the relevant BRs.
4. **Verify:** run the focused checks that can disprove the hypothesis. Inspect results and side effects, including foreign records, stale writes and uncertain responses where applicable. Measure visible lag when relevant; functional success alone does not establish responsiveness.
5. **Review:** inspect the diff, test meaning and evidence. A passing rerun does not explain an earlier failure. Retain the first failure, identify what changed and classify unresolved observations honestly.
6. **Checkpoint:** record the item, hypothesis, change, exact check/environment/result, budget consumed and next action in Progress. Put durable dated receipts/decisions in Journey; avoid copying full logs into both.
7. **Decide:** advance to the next scoped item, revise the hypothesis using new evidence, or enter a stop state below. Run full applicable verification at a coherent candidate boundary, not after every prose edit or private helper change.

Loop states are **ready → investigating → changing → focused verification → review → next item or final verification → complete**. Any state may become **blocked**, **budget checkpoint** or **user-paused**. These are process labels, not new application states or test-status values.

An iteration is one hypothesis/change/evidence cycle. Shell commands, automatic polling and repeating the same failure without new information are not productive iterations. Regressions return the owning item to investigation; do not hide them by broadening timeouts or narrowing acceptance.

## 4. Budget and resource controls

These are default planning limits for a newly scoped campaign, not retroactive acceptance criteria or changes to CI configuration. State any different user-directed limits in the campaign contract before using them.

| Budget | Default and action at the boundary |
| --- | --- |
| Campaign work block | Up to 6 substantive iterations or 90 minutes of active investigation/editing, whichever comes first. At the boundary, checkpoint and reassess scope, remaining evidence and resource use. Authorized productive work may continue in another explicitly recorded bounded block; do not silently reset counters or treat the boundary as completion. |
| No-progress limit | After 2 consecutive iterations on the same hypothesis without new evidence, change the diagnostic method. If the next bounded investigation still cannot advance, mark that item blocked with the missing evidence/decision; continue independent in-scope work. Do not repeat unchanged tests. |
| Focused checks | Choose the smallest meaningful set for the change. Repeat only after a relevant change, new diagnostic hypothesis or evidence of a transient cause; retain prior failures. |
| Full verification | One complete applicable local pass per coherent candidate when required, then exact-final-head CI. Further passes require changed inputs, failures or unresolved concerns. Documentation-only local validation follows AGENTS; full GitHub gates still apply. |
| CI time | Read the actual workflow before launch. Current Fitfinity verification declares 60 minutes each for frontend/backend, 20 minutes per real-API shard and 5 minutes for the aggregate. These are per-job limits, not a one-hour total campaign/workflow allowance. See [verification commands and budgets](docs/development.md#verification-commands). |
| Concurrency | Reuse the existing checkout; avoid overlapping heavy suites that distort results. No additional agents/worktrees unless requested under AGENTS. A new head does not authorize approving an obsolete image job to clear a queue. |
| External cost/data | No new paid services, AWS changes, production load, customer data or real provider actions under routine source authority. Use isolated synthetic storage. Preparation may continue while a separately scoped external action is blocked. |
| Context/evidence | Checkpoint before context exhaustion or handoff. Keep exact commands, source IDs and artifact references; never copy secrets or raw customer data. If token/tool-cost accounting is unavailable, say so rather than invent a numerical spend. |
| Communication | Give concise updates during active work, normally within 60 seconds. CI elapsed time and queue waits are separate from active-work time. Do not claim monitoring or loops continue after the turn ends. |

The block budget is a review boundary, not permission to abandon authorized work early or to exceed an explicit user cap. An explicit hard time/cost limit cannot be extended without the required authorization. Do not spend money merely because another block is technically possible.

## 5. Evidence and completion

Use acceptance appropriate to the change, linked to AGENTS and the owning contract rather than duplicated here. For Fitfinity server integrations, real FastAPI/migrations and isolated Docker PostgreSQL evidence are mandatory; simulator tests remain supplementary. Real Cognito, process restart, physical devices, deployed infrastructure and backup restoration each require their own evidence scope.

| State | What may be claimed |
| --- | --- |
| Implemented | Reviewed source contains the intended behavior; testing may still be pending. |
| Focused-tested | Named checks passed on the recorded head/environment; this is not complete CI acceptance. |
| CI-verified | All required final-head gates passed with complete inventories and no bypass. |
| Merged | GitHub confirms the tested source merged; fresh-main validation is separately recorded. |
| Deployed | The authorized target reports the reviewed source/artifact and applicable health evidence. Source merge or image publication alone is insufficient. |
| Accepted | The campaign's defined behavior and environment-specific acceptance criteria are evidenced; remaining exceptions are explicit. |

A campaign is complete only when every in-scope acceptance item and required delivery step is evidenced. “No issues found in these probes” is valid; “completely error-free forever” is not. A known unresolved failure remains recorded even if later runs pass. Do not label a campaign complete merely because the work-block budget expired or the next action requires approval.

## 6. Stop, recover and hand over

Pause dependent actions for a user stop, exhausted hard budget, unavailable prerequisite, unresolved product/security decision, scope mismatch, denied tool action or missing external authority. Preserve state and evidence; continue independent authorized work where useful. Explain the concrete blocker and required next step without repeatedly seeking already-granted permission.

The handover in Progress must identify the campaign outcome, current branch/head and PR/run, work completed, unknown edits/stashes, exact checks and failures, unresolved hypotheses, consumed/remaining budget, acceptance state and next executable step. Link durable history in Journey. Do not leave competing “latest” handovers.

On resume, re-read the campaign and verify source/environment/evidence still match. Resume the outstanding item instead of restarting the audit or repeating accepted work. A budget extension, source merge, resolved symptom or successful rerun never expands AWS/provider authority automatically.
