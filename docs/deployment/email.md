# Transactional email setup

Local candidate, 28 November 2026: SES delivery is disabled by default. Source and synthetic tests are not proof that a sender is verified, the account has production access, a schedule is enabled, or a message reached an inbox. Initial developer sender: `sheng@app404.ai`, region `ap-southeast-1`. Client deployments supply their own sender and target bindings.

## Real AWS resources and SES sandbox

The setup scripts and deployment workflows must discover and validate the actual target account, region, SES identity, CloudFormation owners, runtime role/boundary, Cognito pool and signing-secret ARN. Reuse those resource bindings and prepare only missing configuration or reviewed changes. Do not substitute synthetic test identities, infer existence from a generated name, recreate installed resources, or treat an old operator receipt as current state. Offline fixtures remain test evidence only.

SES sandbox is a restriction on the real AWS account in a region, not a simulated deployment. Verified-recipient testing exercises the actual service. SES production access is required before sending to ordinary unverified trainer/client addresses; it does not create a separate application or replace existing SES identities.

Developer operator evidence, 28 November 2026: account `418638389566`, region `ap-southeast-1`, sending enabled, production access false, quota200 emails per24hours and1 per second. Both address/domain identities were initially absent; the operator successfully requested verification for `sheng@app404.ai`, then reported completion. A post-click `VerifiedForSendingStatus=true` response has not been pasted, so the next resource readback should include it. No application email, IAM change, database migration or scheduler activation is established by this sender-verification step.

## Events

| Trigger | Recipient | Message |
| --- | --- | --- |
| Trainer invitation | Trainer | Existing Cognito account setup invitation; provider owns temporary credentials. |
| Trainer deactivation | Trainer contact email | Account deactivation notice. |
| Client creation | Each client person | Welcome and assigned trainer, explicitly no app login. |
| Package purchase, including initial onboarding | Each client person | Purchased package, credits and inclusive validity dates. |
| Session acknowledgement | Each client person | Session/package update with current used and remaining credits and validity. |
| Explicit Email Report confirmation | Each client person | Bare text progress report from persisted measurements; no private trainer comments or video files. |

Existing Cognito password-recovery and login-email verification messages also inherit the configured pool sender. Authenticator-app MFA continues to use authenticator codes, not emailed codes.

Each person receives a separate message, including couples. Report preparation and Owner approval never send mail. The recipient/content preview is rechecked at submission. Repeated identical report content for the same actor returns the original receipt, including after a fresh login. Approval and report-email recovery remain separate operations.

## Configuration order

1. Verify the sender in SES in the deployment region. Address verification requires clicking the email sent to `sheng@app404.ai`; no DNS edit is required for that initial test. Domain verification for `app404.ai` requires the exact DKIM records returned by SES. Preserve existing MX and unrelated DNS records. A custom MAIL FROM domain is optional and requires its own records; do not add guessed SPF records.
2. Check whether SES remains in the sandbox. Sandbox delivery requires verified recipients (or SES mailbox simulator addresses). Request production access before sending to unverified trainers/clients. Configure account suppression for bounces and complaints; production acceptance needs actual delivery/feedback evidence.
3. Create a dedicated Secrets Manager signing secret in the target's secret namespace, `<secret_prefix>/email-dispatch`, containing a cryptographically random 32-byte key represented as 64 lowercase hex characters in `dispatch_key`. Do not paste its value in chat, GitHub variables, logs or templates. The application and scheduler receive only the exact ARN. Default AWS-managed encryption is the initial supported configuration; a customer KMS key requires separately reviewed grants.
4. Review runtime changes through the existing hosting feature/change-set path. Optional `email` bindings contain exactly `sender`, `identity_arn`, `dispatch_secret` and `configuration_set` (empty string when unused). `email_runtime.py` checks target/account/region/namespace, derives exact SES/secret grants, and places the same policy in the runtime role and its existing permissions-boundary owner. Preserve this binding during normal releases and rollback. Do not manually patch Lambda environment variables.
5. Review the existing Cognito stack's sender-only template change with `email_runtime.cognito_template`. It sets `EmailSendingAccount=DEVELOPER`, the verified SES identity and From address, preserving MFA, identities and `{username}`/`{####}` invitation placeholders. Inspect the actual existing pool owner before preparing its change set. Cognito's SES service-linked role is separate from the application's SES role.
6. Deploy schema `20261128_0054`, its runtime grants and compatible application source through the normal reviewed migration/release path. The two new tables are additive; populated email history prevents downgrade. Code rollback does not undo email effects.
7. Prepare the dedicated dispatcher stack from `email_scheduler.py`. It contains a Lambda worker, exact-role boundary, log group, disabled EventBridge schedule and invocation permission. Initially it processes at most one pending email per scheduled minute. It uses a purpose-bound, short-lived HMAC request to invoke the existing application alias; the application reads the durable queue and calls SES. No caller supplies recipients or message content. Provider-adapter invocation and private-network egress still require a deployed synthetic canary before schedule activation.
8. Run an authorized synthetic canary with verified test recipients, then enable the schedule only after queue, SES acceptance, inbox delivery and failure feedback are checked. Keep customer mail disabled until these checks pass. User-side exact CloudShell/change-set commands are pending source verification and target readback; this page is not an execution receipt.

## Initial sender check in CloudShell

These read-only commands establish the account and sender state before preparing any AWS changes:

```bash
aws sts get-caller-identity --query Account --output text --no-cli-pager
aws sesv2 get-account --region ap-southeast-1 \
  --query '{SendingEnabled:SendingEnabled,ProductionAccessEnabled:ProductionAccessEnabled,SendQuota:SendQuota}' \
  --output json --no-cli-pager
aws sesv2 get-email-identity --region ap-southeast-1 \
  --email-identity sheng@app404.ai \
  --query '{Verified:VerifiedForSendingStatus,Status:VerificationStatus}' \
  --output json --no-cli-pager
```

The expected developer account is `418638389566`. A missing address identity does not prove that its domain is unverified: also inspect `get-email-identity --email-identity app404.ai` before deciding what to create. If neither identity is verified, the initial address-only option is the following operator action; it sends a verification email and does not enable application sending:

```bash
aws sesv2 create-email-identity --region ap-southeast-1 \
  --email-identity sheng@app404.ai --no-cli-pager
```

Use that create command only for a missing address identity, then follow the verification link in its inbox and repeat the address readback. An existing pending identity should be handled through SES verification controls rather than deleting/recreating it. Do not post verification links or credentials in chat. The remaining role, secret, Cognito and disabled-scheduler changes must be prepared against their actual stack owners using the configuration order above; these sender commands are not a deployment installer.

## Failure and recovery

Business changes and email intents commit together. External SES calls happen afterwards under a database lease. SES acceptance is recorded as `accepted`, not `delivered`; the UI says queued, not sent. A definitive throttling rejection can retry with bounded backoff, at most five attempts. Transport uncertainty, server errors and interrupted leases become `unknown` and are held: SES SendEmail has no idempotency key, so automatically resending could duplicate delivery. Definitive rejection becomes `failed`. Preserve provider IDs and original event/receipt identities when investigating; never clear the queue or blindly requeue unknown mail.

Record live setup and canary evidence in [Journey](../journey.md), resource state in [Infrastructure](infrastructure.md), and the next required action in [Progress](../../PROGRESS.md). The parked CloudShell master catalog remains preserved; automated master-script integration is not yet complete.
