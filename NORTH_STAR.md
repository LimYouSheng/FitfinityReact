# North Star: persistent API-backed Fitfinity prototype parity

Deliver the approved [GitHub Pages prototype](https://limyousheng.github.io/FitfinityReact/) as a fully functioning persistent application backed by FastAPI, PostgreSQL and Cognito. Preserve its appearance, navigation, workflows and Owner/Admin/Trainer behaviour. A login, green CI, read-only directory or deployment is an intermediate checkpoint, not completion. `PROGRESS.md` is the only task ledger; `docs/SERVICE_CONTRACTS.md` owns the route/operation coverage matrix. No exclusions are accepted without YS's explicit agreement.

## Definition of done

- [ ] All **55 named operations** in `src/services/portalContracts.js` have an explicit completed outcome in the existing `docs/SERVICE_CONTRACTS.md` matrix: connected durable behavior where persistence is required, or an evidenced genuinely local implementation. Authentication and route parity remain additional requirements. An API-enabled flag, endpoint, mock test or empty response alone does not complete an operation.
- [ ] Every approved prototype workflow has an implementation and documented acceptance result for its applicable roles, with server-enforced identity, assignment and permissions.
- [ ] Shared data persists across reload, sign-out, another browser/device and service restart. Browser/demo storage is not the production datastore.
- [ ] Conflicts, duplicate submissions, interrupted requests and recovery behave correctly; writes are transactional, versioned and idempotent where required. A committed save remains successful if refresh fails.
- [ ] Equivalent controlled test data demonstrates prototype layout, navigation, filters, pagination, Back behaviour, responsiveness and accessibility. No unintended account-placeholder dashboard, demo fallback, fabricated schedules or silently missing workflows remain.
- [ ] Full final-commit frontend/backend/api-browser CI passes, including macOS WebKit and real PostgreSQL. Every integrated server operation has traceable real-database tests; simulator results alone never satisfy integration acceptance.
- [ ] Real enrollment, repeat login, refresh, expiry, sign-out, account lifecycle and separately specified secure lost-authenticator recovery pass. YS's desktop, Samsung and iPad checks are recorded separately.
- [ ] Deployment/update and populated-data recovery procedures are reviewed and evidenced. Final source/artifacts/image provenance, costs and remaining security limits are recorded.

## Current execution order

1. Reconcile source and evidence; refactor documentation using relevant current SoccerBot practices.
2. Complete real API coverage against isolated PostgreSQL for every integrated server operation. Cover UI writes and reload/fresh-login persistence, conflicts, unknown outcomes and unauthorized/foreign records. Resolve the test-build Lambda-adapter dependency needed to run these checks. The local predicate needs local evidence, not an invented endpoint.
3. Resume incomplete session scheduling/writes and request decisions; then plans/outcomes/summaries/acknowledgement/credits; assessment/report/media gaps; remaining messaging/Undo/remuneration/content/profile parity.
4. Validate final-head CI, merge eligible source, and separately prepare release and live/provider/device acceptance.

[Progress](PROGRESS.md) owns tasks, dependencies and evidence. Hardening items start as planned work; do not provision tools or paid services merely because they are listed.

## Authority and invariants

Use one agent, the existing checkout/caches and valid receipts. YS's 13 October instruction is to keep going until all 55 operations are complete. Continue routine investigation, implementation, focused tests, documentation and draft PR preparation autonomously; PR readiness is a checkpoint, not an automatic stop. Do not inherit obsolete repair budgets. Keep one focused slice per PR and one active branch at a time; dependent draft PRs may be stacked with their exact base/dependency recorded while earlier PRs await merge. Never claim an unmerged dependency is accepted main. Continue independent authorized work while CI or review is pending; stop only at a concrete blocker, required user decision or authorization boundary, with the next action prepared. This is an active-session work instruction, not an unattended background schedule. YS resumed on 23 October with the execution order above. Source progress continues under the existing authority; deployment remains separate.

Maintain this file as the single North Star, `PROGRESS.md` as the single progress ledger, and the existing service-contract matrix as the operation/route evidence reference. Do not create a second North Star or competing checklist. Track implemented, full-CI-verified, merged, deployed and live/device-accepted states separately. The 55/55 implementation target does not waive the release and acceptance conditions above.

YS authorizes Codex to merge North Star PRs once their complete final-head frontend and backend CI passes (standing instruction, 13 October 2026). Handle ordinary branch updates and dependency ordering without another confirmation. Preserve branch protection; merge only tested heads, with no administrator bypass or unattended auto-merge setting. Previously approved stacked source may land through an aggregate PR when ancestry and scope are verified and the updated aggregate head passes both complete jobs. New AWS mutations, image publication, scans, deployment, IAM changes, security-exception renewal, real invitations/messages and destructive actions still need applicable authorization. No direct main/force push, reset, bootstrap replay or replacement operation to evade reconciliation. Source binding, historical receipts, resource identities, write intents and ownership checks remain mandatory.

Preserve Owner/Admin-only access to the initial 11 assessment forms; YS authorizes current assigned Trainers to read/edit general health notes separately (13 October 2026). Preserve Owner-only rate management and remuneration approval, Admin financial restrictions, scheduling conflicts, validity/credit rules, completed-record immutability and current authority at commit. Never trust browser-supplied actors or fabricate WhatsApp/native-share sent/delivered states. Preserve test/security gates.

## Preserved deployment and limits

Current deployed source is `b3a97897bc733c2ddbbbd17a40c1407b2a506649`, frontend release 38311509067, deployment 38340492199, artifact 11788346033, ZIP SHA-256 `4e181227297a1585499fc83348d996ee35e6aaead08ed7c75dbe0f4b0e53fd9a`. Forty-one frontend files, public health/readiness and signed-out rejection were verified at https://d21430zmxp3m5m.cloudfront.net. YS reported Owner login after an account-specific MFA correction. The application repair is not deployed; historical logs do not identify every rejection cause.

Preserve the database, Cognito pool, Owner, successful edge and retained buckets. Completed deletion/replacement preparation/first-create execution are historical and must not be replayed. New backend bytes require a new reviewed image and appropriate update path; prior image/runtime proof cannot represent them.

Current image `sha256:861837230551824fdf37f868def500ca14abdbe489583f60ddacee932451eb5a` retains original source `33d124fcd59ffd3f9cb30d645660bdad99a21278`. Private-runtime proof on 8 October at 12:23:04 Singapore, operation `aa2b2e439c3943b3b425de90302833ab`, run 37721383277 remains unchanged. Historical approvals ending 11 October 20:41:44 and 12 October 23:41:30 are preserved in the runbook. Owner-merged PR #23's TEST exception ends **13 October 2026, 23:42:58 Singapore**. Expiry does not stop resources or billing; no silent renewal or teardown.

SESSION-OPEN-01 demo/device acceptance on 7 October does not accept API/live behaviour. CLOUD-01 public PR preview remains incomplete; no tunnel retry is implied. Journey owns history; Rules/Service Contracts own product behaviour; AGENTS/cloud guide own development workflow; AWS runbook owns release and recovery evidence.
