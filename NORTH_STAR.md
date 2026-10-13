# North Star: persistent API-backed Fitfinity prototype parity

Deliver the approved [GitHub Pages prototype](https://limyousheng.github.io/FitfinityReact/) as a fully functioning persistent application backed by FastAPI, PostgreSQL and Cognito. Preserve its appearance, navigation, workflows and Owner/Admin/Trainer behaviour. A login, green CI, read-only directory or deployment is an intermediate checkpoint, not completion. `PROGRESS.md` is the only task ledger; `docs/SERVICE_CONTRACTS.md` owns the route/operation coverage matrix. No exclusions are accepted without YS's explicit agreement.

## Definition of done

- [ ] Every approved prototype workflow has an implementation and documented acceptance result for its applicable roles, with server-enforced identity, assignment and permissions.
- [ ] Shared data persists across reload, sign-out, another browser/device and service restart. Browser/demo storage is not the production datastore.
- [ ] Conflicts, duplicate submissions, interrupted requests and recovery behave correctly; writes are transactional, versioned and idempotent where required. A committed save remains successful if refresh fails.
- [ ] Equivalent controlled test data demonstrates prototype layout, navigation, filters, pagination, Back behaviour, responsiveness and accessibility. No unintended account-placeholder dashboard, demo fallback, fabricated schedules or silently missing workflows remain.
- [ ] Full final-commit frontend/backend CI passes, including required browser/macOS WebKit and real PostgreSQL coverage.
- [ ] Real enrollment, repeat login, refresh, expiry, sign-out, account lifecycle and separately specified secure lost-authenticator recovery pass. YS's desktop, Samsung and iPad checks are recorded separately.
- [ ] Deployment/update and populated-data recovery procedures are reviewed and evidenced. Final source/artifacts/image provenance, costs and remaining security limits are recorded.

## Dependency order

0. Authentication foundation: PR #24 final head `44373574c47f1452c185189a7066ac6d8da1b604` passed both required jobs in run 38352674116. YS merged it on 13 October 2026 at 14:29:47 Singapore as verified remote main `eed077e1500e09ca2b486d0a991f520b76ceeeb5`. Source entry gate is satisfied; repaired deployment and live acceptance remain pending.
1. Inventory every prototype route and all named operations against existing frontend/backend/persistence/permissions/tests, recording exact comparison source. Classify connected, backend-only, missing orchestration or genuinely local before adding endpoints.
2. Complete core client/trainer/package records, availability, assignment, renewal and history; preserve Admin onboarding protections. First slice: package catalogue creation/edit/lifecycle.
3. Connect real session/calendar and renewal reads, restoring existing dashboard and navigation only as contracts become functional.
4. Complete fixed/open scheduling, postponement/reassignment, requests/approvals, plans/outcomes/summaries, acknowledgement and credit accounting.
5. Complete durable assessment drafts/history, reports, exercise media and session videos with privacy, upload ownership, replacement/deletion and truthful export/share history.
6. Complete personal messages/read receipts, permitted Undo, resolution/cancellation, remuneration/approvals, content, profiles and remaining approved workflows.
7. Review/deploy updates and demonstrate end-to-end persistence, recovery, role and physical-device acceptance.

This is dependency order, not permission to rewrite completed components. Each PR contains one focused dependency-ready integration slice. Source work can advance after the merged entry gate; it cannot stand in for the live authentication release.

## Authority and invariants

Use one agent, the existing checkout/caches and valid receipts. Continue routine investigation, implementation, focused tests, documentation and draft PR preparation autonomously. Do not inherit obsolete repair budgets. Stop at PR readiness, a concrete blocker or an applicable authorization boundary with the next action prepared.

YS alone merges. New AWS mutations, image publication, scans, deployment, IAM changes, security-exception renewal, real invitations/messages and destructive actions need applicable authorization. No auto-merge, main/force push, reset, bootstrap replay or replacement operation to evade reconciliation. Source binding, historical receipts, resource identities, write intents and ownership checks remain mandatory.

Preserve Owner/Admin assessment access and restricted Trainer access, Owner-only rate management and remuneration approval, Admin financial restrictions, scheduling conflicts, validity/credit rules, completed-record immutability and current authority at commit. Never trust browser-supplied actors or fabricate WhatsApp/native-share sent/delivered states. Preserve test/security gates.

## Preserved deployment and limits

Current deployed source is `b3a97897bc733c2ddbbbd17a40c1407b2a506649`, frontend release 38311509067, deployment 38340492199, artifact 11788346033, ZIP SHA-256 `4e181227297a1585499fc83348d996ee35e6aaead08ed7c75dbe0f4b0e53fd9a`. Forty-one frontend files, public health/readiness and signed-out rejection were verified at https://d21430zmxp3m5m.cloudfront.net. YS reported Owner login after an account-specific MFA correction. The application repair is not deployed; historical logs do not identify every rejection cause.

Preserve the database, Cognito pool, Owner, successful edge and retained buckets. Completed deletion/replacement preparation/first-create execution are historical and must not be replayed. New backend bytes require a new reviewed image and appropriate update path; prior image/runtime proof cannot represent them.

Current image `sha256:861837230551824fdf37f868def500ca14abdbe489583f60ddacee932451eb5a` retains original source `33d124fcd59ffd3f9cb30d645660bdad99a21278`. Private-runtime proof on 8 October at 12:23:04 Singapore, operation `aa2b2e439c3943b3b425de90302833ab`, run 37721383277 remains unchanged. Historical approvals ending 11 October 20:41:44 and 12 October 23:41:30 are preserved in the runbook. Owner-merged PR #23's TEST exception ends **13 October 2026, 23:42:58 Singapore**. Expiry does not stop resources or billing; no silent renewal or teardown.

SESSION-OPEN-01 demo/device acceptance on 7 October does not accept API/live behaviour. CLOUD-01 public PR preview remains incomplete; no tunnel retry is implied. Journey owns history; Rules/Service Contracts own product behaviour; AGENTS/cloud guide own development workflow; AWS runbook owns release and recovery evidence.
