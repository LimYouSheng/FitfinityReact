---
name: fitfinity-deployment
description: Establish Fitfinity deployment and configuration readiness from exact source, artifact, AWS account and runtime evidence. Use for developer-AWS setup, image publication, Lambda/frontend release, configuration drift, activation, failed deployment and rollback; preserve resource identity and distinguish source acceptance from real-provider/device acceptance.
---

# Deployment and configuration readiness

## Authority and owners

Read [AGENTS](../../../AGENTS.md), [North Star](../../../NORTH_STAR.md), [Progress](../../../PROGRESS.md), the [deployment runbook](../../../docs/runbook.md#6-deployments-and-rollback), [configuration guide](../../../docs/runbook.md#10-configuration) and [deployment rules](../../../docs/business-rules.md#deployment-migration-and-acceptance). Inspect actual workflows, infrastructure manifests, operator scripts and current receipts; historical checkpoints do not establish readiness.

This skill owns readiness investigation and evidence-based go/hold recommendations. The runbook owns commands/recovery, manifests own intended configuration and Progress owns current state. Apply the [testing](../fitfinity-testing/SKILL.md) and [documentation](../fitfinity-documentation/SKILL.md) skills for changes, [CI diagnosis](../fitfinity-ci-diagnosis/SKILL.md) for failed gates and [dependency review](../fitfinity-dependencies/SKILL.md) for runtime/package compatibility. Load applicable environment instructions before using its tools. No Cloudflare architecture or permissions are assumed.

Explicit user instructions take precedence. Reuse authorization already given for the same operation/scope; do not ask repeatedly. Existing source-merge authority does not authorize AWS mutations, image publication/scans, deployment, IAM/secrets changes, schedule activation, rollback or real customer/provider effects. Complete independent authorized preparation and make the exact action reviewable before requesting any missing authorization. Never print credentials, tokens or customer data. This is an instruction source, not an automatic deploy hook or standing monitor.

Adapted from the [SoccerBot deployment skill](https://github.com/soccerbotstudiosg/soccerbotstudioSG/blob/docs/dependency-review-skill/.agents/skills/soccerbot-deployment/SKILL.md), inspected2 November2026. Fitfinity’s actual AWS architecture, evidence owners and authority govern.

## 1. Identify the intended operation

State the target and outcome: read-only inspection, foundation preparation, ECR image publication, existing-image acceptance, Lambda/runtime rollout, frontend hosting release, configuration repair, activation or rollback. Distinguish GitHub Pages staff demo from the AWS API-connected site, and developer AWS from any customer production environment. A developer environment still has real costs and provider effects.

Verify repository, branch/head, PR/merge state, workflow/event and actor. Confirm AWS account, region, exact resource IDs/ARNs and resource ownership against the current reviewed configuration. A connector login, role name, display name or available token does not prove target identity or authorization. Check separate verification, image-publication and runtime/hosting role scopes in the executable workflows; never substitute broader credentials to bypass a denied operation. Preserve unknown edits, existing resources and explicitly protected runs.

Record deployment defaults and the intended activation state explicitly. A closed-by-default configuration can be correct: for example, Fitfinity’s image workflow requires `AWS_IMAGE_RELEASE_ENABLED == 'true'` as well as manual dispatch and source/account gates. An absent/false flag is not itself a defect or permission to enable it. Inspect actual configuration separately from the source default. When a test requires activation, prepare an exact scoped activation/reversion plan and obtain any missing authorization; do not turn production/provider effects on merely to pass readiness checks.

## 2. Trace source to the release artifact

- Bind repository/source SHA, successful verification run/attempt, expected job set, artifact identity/digest and release receipt. Full PR verification, fresh-main verification, image publication and deployment are different events. A skipped main-only publish on a PR is expected.
- Inspect the manual image workflow’s exact main source input, activation variable, protected environment, account/role restrictions and complete verification prerequisites. Keep verification/demo publishing separate from approval-gated image release. Do not approve an obsolete image just to clear concurrency.
- Preserve trusted source/artifact rules and keep PR/fork/Dependabot execution away from deployment credentials. Inspect image scan findings for the exact digest; a clean npm audit does not scan OS/Python packages or the deployed image. Never renew an exception from historical approval alone.
- For frontend release, retain the tested immutable artifact and its embedded public API configuration/base path. For Lambda, bind the exact reviewed image digest and current runtime configuration. Do not silently rebuild with different inputs or infer deployment from an image tag existing in ECR.
- Inspect outgoing/incoming schema compatibility, migration readiness, previous artifact availability and rollback constraints. A source rollback cannot undo data writes, migrations, invitations or other provider effects. Do not edit applied migrations or reset storage to recover a release.

## 3. Reconcile configuration at each store

Record expected/observed/gap information in the existing operational receipt, not a duplicate secret inventory. For secrets record names, scope and verification state only; presence does not establish validity or correct account/provider pairing.

| Surface | What to verify |
| --- | --- |
| Infrastructure and workflows | AWS account/region, resource identities/ownership, network and access boundaries, exact-source gates, GitHub environment protection and intended role selection. |
| GitHub Actions | Required variable/secret names and repository/environment scope, activation settings, OIDC trust and least-privilege role boundaries. A value in one store does not populate another. |
| Frontend artifact | Public API origin, base path and API/demo selection embedded at build time; actual artifact/source binding. Runtime secrets cannot repair a stale static build. |
| Lambda/API | Image digest, Lambda Web Adapter/readiness behavior, environment/secret references, database/schema readiness, VPC/security-group configuration and actual role permissions. Determine what the operation preserves or overwrites. |
| Cognito and identity | Exact pool/client/issuer, callback/logout origins, MFA and invitation/recovery configuration, correct staff identity mapping and provider authority. Synthetic signed tokens are not live Cognito acceptance. |
| RDS and storage | Database identity/engine/schema, encrypted connections/access, S3 bucket/prefix/KMS permissions, signed-URL origins and relevant retention/worker configuration. Distinguish logical expiry from physical deletion. |
| Cloud Containers/local setup | Checkout, runtime/lock/browser versions, isolated database/storage targets, proxy/CA trust and externally prepared image settings. Repository edits do not republish an external environment. |
| Monitoring and schedules | Implemented health checks and worker/event schedule state, alert recipients/thresholds, ingestion/redaction, retention and cost controls. Planned Grafana/OTel or unassigned alerts are not active controls. |

Use existing validators and names-only metadata first. If access is unavailable, record the precise unknown and minimum owner evidence needed; never request secret values in chat or interpret a masked placeholder as usable credentials. DNS, certificates, mail authentication, domain routing and provider delivery need separate evidence. Preserve unrelated records and mappings.

## 4. Inspect resources and operational behavior

Confirm current foundation ownership, subscriptions, migrations, resource state and operation receipts before authorized provisioning. Preserve RDS data, Cognito identities, S3 objects and existing network/role identities. Repeated execution must not create replacement resources or replay historical bootstrap/deletion operations. Test partial-failure recovery and wrong-account/resource rejection; a second successful call alone does not prove idempotency.

Review database capacity/connection behavior, Lambda cold/warm behavior, network egress, storage growth and cost where affected. Use actual authorized measurements, not local benchmark results as claimed AWS latency. Routine functional/load probes remain synthetic and isolated; production/customer load requires explicit scope.

Check worker/schedule activation, media deletion boundaries, backup/restore readiness and incident/rollback plans. Source code, configured cron or a dashboard flag does not prove execution, delivery or recovery. Monthly cleanup is not activated merely because it is documented. Proposed RPO/RTO, unassigned responders and unexecuted restore drills remain explicit gaps. Developer sites can remain reachable and incur idle costs; verify exposure and isolation rather than assuming production controls apply.

## 5. Diagnose deployment and verify acceptance

Read the first failing step and partial receipt before changing configuration or retrying. Classify eligibility rejection, build/artifact failure, permission/account mismatch, image/scan issue, migration/readiness failure, partial upload/rollout, routing/network issue or provider failure. A failed workflow may already have changed resources; inspect actual target state before retrying. A later successful request does not establish that the original cause was propagation.

After an authorized operation, verify actual revision/digest, configuration and health through permitted paths. Distinguish image published, runtime deployed, frontend published, API connected, provider verified and physical-device accepted. Network-policy denial is not proof the site is down; a deployment record does not prove public-route health. Use bounded checks, retain failures and do not bypass access controls.

Use the [Owner](../../../docs/uat/owner.md), [Admin](../../../docs/uat/admin.md) and [Trainer](../../../docs/uat/trainer.md) worksheets for designated developer-AWS identities and device acceptance. Require device model, exact OS version, exact browser version, deployed revision and Pass/Fail/Blocked/Not tested outcome in each physical acceptance record. Record results and perceived lag separately from blank masters. Upstream support, configured targets and verified coverage are separate claims; consult the [development coverage matrix](../../../docs/development.md#browser-testing-coverage). Emulation and two discrete tested versions do not establish real-device acceptance or a continuous supported range. Real login/MFA/recovery, invitations/email, sharing, storage cleanup, restart/restore, rollback and alert delivery are not accepted from configuration or synthetic CI alone. This skill grants no authority to send invitations/messages, change customer records or run recovery against real accounts.

## 6. Readiness receipt

Report target/operation and authorization; exact repository/source/run/artifact/digest; verified account/resource identities; configuration gaps without secrets; observed health/provider/device evidence; rollback constraints; and a **go** or **hold** recommendation with the concrete next step. Separate prepared, verified, published, deployed, activated and accepted states. Update Progress/Journey and affected operational owners under the documentation skill. Do not claim unconditional readiness with missing required evidence or create recursive status commits merely to restate green CI.
