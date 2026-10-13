# North Star: Fitfinity AWS TEST login ready

Carry Fitfinity from M6.21 to a working, secure AWS TEST login that YS can use. This goal persists across repairs, PRs and operational checkpoints. Passing CI, merging a repair or preparing hosting advances the goal; none completes it. `PROGRESS.md` owns individual tasks and evidence; the AWS runbook owns exact release inputs, recovery commands and approval gates.

## Definition of done

- [ ] A verified public AWS TEST HTTPS URL serves the exact immutable API-mode frontend release and working backend.
- [ ] The existing Owner completes the applicable password setup and MFA flow and reaches the authenticated application.
- [ ] Reload/session refresh, expiry and sign-out work; signed-out navigation cannot restore protected access.
- [ ] YS's agreed desktop, Samsung and iPad checks are recorded separately from automated CI.
- [ ] Final source, frontend/runtime artifacts, image provenance, operational receipts and remaining limitations are recorded.

Broader M6 functionality, populated-database recovery and production readiness remain separate. Preserve the existing database, secrets, Cognito pool and Owner.

## Current path

Owner-merged PR #23 main is `b3a97897bc733c2ddbbbd17a40c1407b2a506649`. Deployment run 38340492199 passed with exact immutable frontend/public smoke evidence at https://d21430zmxp3m5m.cloudfront.net. YS reports Owner login succeeded after an account-specific MFA preference correction. Live session lifecycle/device acceptance and full prototype/API integration are still incomplete.

1. Fix the missing MFA-preference reconciliation after successful TOTP verification, preserving provider/local identity checks and testing failure paths. Deliver a reviewed PR before a new image/deployment.
2. Use GitHub Pages as the expected product interface. The current API dashboard is an account placeholder; map the real session/renewal reads and domain writes needed to use the prototype components without fabricated demo data.
3. YS alone merges. A backend repair requires new image provenance/security review and an explicitly reviewed deployment; do not relabel the accepted image or replay first-create recovery operations against the now-live app.
4. Complete fresh Owner login/session/reload/sign-out and agreed desktop/Samsung/iPad acceptance after the repaired deployment. Preserve the existing account, database, edge, retained bucket, operation history and credentials boundary.

## Authority and iteration

One agent; reuse the existing checkout, dependencies, caches and valid receipts. Continue authorized investigation, focused repairs, tests and canonical documentation autonomously. Do not inherit the obsolete 30-minute automatic stop from earlier repairs. Honor explicitly agreed execution budgets with CI waiting separate; carry unfinished work forward accurately. Stop at a concrete blocker, required user action or authorization boundary with the next action prepared.

YS is the sole merge authority. No merge, auto-merge, main/force push, account reset, bootstrap replay or replacement operation to evade reconciliation. AWS mutations, hosting execution, scan requests, IAM changes and approval renewal require applicable explicit authorization. Keep credentials outside coding work. Source binding, historical receipts, resource identities, write intents and ownership checks remain mandatory.

Preserve image `sha256:861837230551824fdf37f868def500ca14abdbe489583f60ddacee932451eb5a`, original image source `33d124fcd59ffd3f9cb30d645660bdad99a21278` and the historical TEST exception expiry **11 October 2026, 20:41:44 Singapore**. Owner-merged PR #21 records the separately authorized bounded renewal ending 12 October 2026, 23:41:30 Singapore; historical receipts must not be rewritten. PR #23 proposes the separately authorized three-finding renewal ending 13 October 2026, 23:42:58 Singapore; only owner merge makes it effective. Stale scan evidence or expired approval blocks execution; never silently extend, transfer or weaken approval.

## Retained acceptance and limits

Private-runtime proof completed on 8 October at 12:23:04 Singapore, operation `aa2b2e439c3943b3b425de90302833ab`, run 37721383277, for the exact accepted digest with owned cleanup. Preserve that evidence; it is not live hosting/sign-in acceptance. Existing hosting source/operator, IAM preparation and release evidence are retained in the runbook.

SESSION-OPEN-01 is accepted for the demo, including YS's 7 October physical checks. Those results do not accept the AWS TEST login. CLOUD-01 public PR preview remains incomplete; no tunnel retry is implied. Journey owns completed history; Rules/Service Contracts own product behavior; AGENTS and the cloud guide own development workflow.
