# Transactional email setup

Local candidate, 28 November 2026: SES delivery is disabled by default. Source and synthetic tests are not proof that a sender is verified, the account has production access, a schedule is enabled, or a message reached an inbox. Initial developer sender: `sheng@app404.ai`, region `ap-southeast-1`. Client deployments supply their own sender and target bindings.

## Real AWS resources and SES sandbox

The setup scripts and deployment workflows must discover and validate the actual target account, region, SES identity, CloudFormation owners, runtime role/boundary, Cognito pool and signing-secret ARN. Reuse those resource bindings and prepare only missing configuration or reviewed changes. Do not substitute synthetic test identities, infer existence from a generated name, recreate installed resources, or treat an old operator receipt as current state. Offline fixtures remain test evidence only.

SES sandbox is a restriction on the real AWS account in a region, not a simulated deployment. Verified-recipient testing exercises the actual service. SES production access is required before sending to ordinary unverified trainer/client addresses; it does not create a separate application or replace existing SES identities.

Developer operator evidence, 28 November 2026: account `418638389566`, region `ap-southeast-1`, sending enabled, production access false, quota200 emails per24hours and1 per second. Both address/domain identities were initially absent; the operator successfully requested verification for `sheng@app404.ai`, then reported completion. The subsequent operator readback confirms `sender_verified=true`, production access false and runtime email disabled. No application email, IAM change, database migration or scheduler activation is established by this sender-verification step.

Actual bindings from that readback:

| Resource | Observed binding / owner |
| --- | --- |
| Runtime and role | `fitfinity-test-staff-api` and `fitfinity-test-hosting-api`; `fitfinity-test-login` owns `ApiFunction` and `ApiRole`. Runtime Active/Successful. |
| Runtime boundary | `arn:aws:iam::418638389566:policy/fitfinity-test-hosting-api-boundary`; `fitfinity-test-github-hosting` owns `ApiBoundary`. |
| Cognito pool | `ap-southeast-1_La0Y3MXCj`; `fitfinity-test-cognito` owns `StaffPool`, currently `COGNITO_DEFAULT`. |
| Dispatch secret | Operator supplied `arn:aws:secretsmanager:ap-southeast-1:418638389566:secret:fitfinity/test/email-dispatch-Vh1QVX` after the create-secret step. Value was not shared. |

Keep Cognito on `COGNITO_DEFAULT`, as explicitly selected by the user. This email setup does not change the pool, invitation credentials, password recovery or login-email verification. SES production access is needed for unrestricted application transactional email, not for the unchanged Cognito sender. The secret ARN alone does not establish runtime grants, valid key contents, an installed worker or delivery acceptance.

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
5. Prepare the actual external boundary, coordinator read grant and disabled worker with the CloudShell command below. Install the reviewed prerequisite change sets before using the generated release configuration. The coordinator receives only GetTemplate access to the existing hosting-access stack; it receives no IAM write authority. Cognito is unchanged.
6. Deploy schema `20261128_0054`, its runtime grants and compatible application source through the normal reviewed migration/release path. The new tables are additive; populated email history prevents downgrade. Code rollback does not undo email effects. The release applies the runtime role/environment change through its frozen `feature_values`, preserving existing feature flags and resource ownership.
7. The dedicated worker template keeps its EventBridge schedule disabled. It processes at most one pending email per scheduled minute after activation, using a short-lived HMAC request to the actual application alias. No caller supplies recipients or content. Provider-adapter invocation and private-network egress need a deployed canary.
8. Run an authorized synthetic canary **from** `sheng@app404.ai` **to** a verified test recipient. Sender and recipient may be the same address. Check queue outcome, SES acceptance, inbox delivery and failure feedback before enabling the schedule. Application queue capture and worker delivery are separate: deployment with email bindings enables intent capture; the disabled schedule prevents automatic dispatch.

## Prepare the existing account in CloudShell

Use the reviewed checkout containing `email_setup.py`. Save the **current** GitHub repository variables `FITFINITY_RELEASE_CONFIG_JSON` and `FITFINITY_DEPLOYMENT_TARGETS_JSON` as `release-config-current.json` and `deployment-targets.json` in a private directory. These contain public bindings only, never secret values. The current configured profile can differ from the historical checked-in developer profile, so the command selects the target from those saved variables and verifies its fingerprint.

From the repository root, set `EMAIL_INPUT_DIR` to that private directory, then run:

```bash
export EMAIL_INPUT_DIR="$HOME/fitfinity-email-inputs"
mkdir -p "$EMAIL_INPUT_DIR"
chmod 700 "$EMAIL_INPUT_DIR"
# Save the two current GitHub variable JSON values here before continuing.
python3 - <<'PYPROFILE'
import json
import os
import sys
from pathlib import Path
sys.path.insert(0, "backend/infrastructure")
from deployment_profile import configured_target, fingerprint
root = Path(os.environ["EMAIL_INPUT_DIR"])
config = json.loads((root / "release-config-current.json").read_text())
profile = configured_target(config["target"], (root / "deployment-targets.json").read_text())
if fingerprint(profile) != config["profile_sha256"]:
    raise SystemExit("Current GitHub target and release profile differ; preserve both for review")
(root / "target-profile.json").write_text(json.dumps(profile, indent=2) + "\n")
PYPROFILE
cat > "$EMAIL_INPUT_DIR/email.json" <<'JSON'
{
  "sender": "sheng@app404.ai",
  "identity_arn": "arn:aws:ses:ap-southeast-1:418638389566:identity/sheng@app404.ai",
  "dispatch_secret": "arn:aws:secretsmanager:ap-southeast-1:418638389566:secret:fitfinity/test/email-dispatch-Vh1QVX",
  "configuration_set": ""
}
JSON
bash docs/deployment/master-script/prepare-review.sh email \
  "$EMAIL_INPUT_DIR/target-profile.json" "$EMAIL_INPUT_DIR/email.json" \
  "$EMAIL_INPUT_DIR/release-config-current.json" "$EMAIL_INPUT_DIR/review"
```

The helper requires Python with boto3 (available in AWS CloudShell). Use a new review directory on subsequent preparations. It performs read-only AWS calls, reads no secret values, creates no change sets and sends no email. It verifies actual account, SES identity, secret metadata/current version, stack owners, alias and boundary consumers. An existing worker must exactly match the disabled candidate; a differing worker stops for inspection.

Outputs:

- `review.json`: actual owners, original/candidate hashes and observed production-access state.
- `boundary-change-set.json` and `coordinator-change-set.json`: UPDATE requests only when those templates differ; preserve current stack parameters.
- `worker-change-set.json`: CREATE request only when the dispatcher stack is absent, with schedule disabled.
- `hosting-preview.json`: review aid only; apply through normal rollout, never directly as a separate update.
- `release-config.json`: complete replacement for the existing GitHub variable, preserving target/profile/probe and adding `email` plus the external `email_boundary` owner/candidate hash.

After inspecting the generated requests, create each present change set (this prepares AWS review objects; it does not execute them):

```bash
python3 - <<'PYCHANGES'
import json
import os
import subprocess
from pathlib import Path
root = Path(os.environ["EMAIL_INPUT_DIR"]) / "review"
profile = json.loads((root.parent / "target-profile.json").read_text())
for name in ("boundary", "coordinator", "worker"):
    path = root / (name + "-change-set.json")
    if not path.exists():
        continue
    request = json.loads(path.read_text())
    base = ["aws", "cloudformation", "--region", profile["region"], "--no-cli-pager"]
    subprocess.run(base + ["create-change-set", "--cli-input-json", "file://" + str(path)], check=True)
    subprocess.run(base + ["wait", "change-set-create-complete", "--stack-name", request["StackName"], "--change-set-name", request["ChangeSetName"]], check=True)
    subprocess.run(base + ["describe-change-set", "--stack-name", request["StackName"], "--change-set-name", request["ChangeSetName"], "--query", "{Status:Status,ExecutionStatus:ExecutionStatus,Changes:Changes}", "--output", "json"], check=True)
print("PREPARED ONLY. No change sets executed. Retain and review these results.")
PYCHANGES
```

Expected changes: only the existing runtime boundary policy, coordinator role/boundary GetTemplate scope, and the new disabled dispatcher resources. Execute the separately reviewed change sets using their exact returned IDs and verify completion before updating GitHub. After an interrupted command inspect the named change set rather than blindly rerunning creation.

## GitHub JSON update

Replace the existing repository variable **`FITFINITY_RELEASE_CONFIG_JSON`** with the complete contents of generated `review/release-config.json` **after** the prerequisite IAM/worker installation is verified. No new email-specific GitHub secret or separate sender variable is needed. Never put the dispatch signing key in GitHub.

The coordinator freezes email values and the external boundary owner/hash into the rollout review. The manual upload/create/deploy path checks those same values against the configured intent before AWS authentication; construct its review using the same generated email bindings and actual hosting template. Recovery/resumption retain the original review rather than adopting a later variable edit. Removing `email` from the configuration preserves installed email settings; it is not a disable switch. A stale boundary hash stops the release and requires a fresh preparation against actual state. Keep existing workflow enablement choices unchanged; this setup does not enable orchestration or scheduled delivery.

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

Use that create command only for a missing address identity, then follow the verification link in its inbox and repeat the address readback. An existing pending identity should be handled through SES verification controls rather than deleting/recreating it. Do not post verification links or credentials in chat. The remaining role, secret and disabled-scheduler changes must be prepared against their actual stack owners using the configuration order above; these sender commands are not a deployment installer.

## Failure and recovery

Business changes and email intents commit together. External SES calls happen afterwards under a database lease. SES acceptance is recorded as `accepted`, not `delivered`; the UI says queued, not sent. A definitive throttling rejection can retry with bounded backoff, at most five attempts. Transport uncertainty, server errors and interrupted leases become `unknown` and are held: SES SendEmail has no idempotency key, so automatically resending could duplicate delivery. Definitive rejection becomes `failed`. Preserve provider IDs and original event/receipt identities when investigating; never clear the queue or blindly requeue unknown mail.

Record live setup and canary evidence in [Journey](../journey.md), resource state in [Infrastructure](infrastructure.md), and the next required action in [Progress](../../PROGRESS.md). The parked CloudShell master catalog remains preserved; the email phase is integrated as read-only preparation; full fresh-account installation and live email acceptance remain separate work.
