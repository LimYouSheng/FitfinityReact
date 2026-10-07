"""Read-only current-image evidence collection; canonical resource checks are unchanged."""

import json
import os
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import deploy
import private_runtime_binding as binding
from authentication_secrets import AuthenticationSecretOperator
from egress_execution import EgressOperator
from operator_context import OperatorContext

ROOT = Path(__file__).resolve().parent

REVISION = "2026-10-04-readonly-preflight-1"
MARKER = "Fitfinity_AWS_Runtime_Preflight_2026-10-04"
READS = frozenset(deploy.READS | {("ecr", "batch-get-image"), ("lambda", "get-account-settings")})
require = deploy.require


def note(message, color="36"):
    print(f"\033[{color}m{message}\033[0m", flush=True)


def now():
    return datetime.now(UTC)


def receipt_initial():
    return {
        "operator_revision": "2026-10-07-private-runtime-1",
        "checked_at": now().isoformat(),
        "account": deploy.CONFIG["account"],
        "region": deploy.CONFIG["region"],
        "image_digest": binding.DIGEST,
        "status": "started",
        "read_only": True,
        "cloud_writes": [],
        "calls": [],
        "steps": [],
        "aws_runtime_verified": False,
        "temporary_cleanup_complete": False,
        "application_deployed": False,
        "scan_policy_passed": False,
        "owner_created": False,
        "live_authentication_accepted": False,
    }


def evidence(report, checked_at):
    binding.check_approval(report["approval"], report["candidate_provenance"], checked_at)
    if report.get("current_scan_pages"):
        binding.acceptance(
            report["current_scan_pages"],
            binding.DIGEST,
            report["candidate_provenance"],
            report["approval"],
            checked_at,
        )
    return report["candidate"]


def safe_error(service, operation, result):
    error = result.stderr or ""
    match = re.search(r"An error occurred \(([A-Za-z0-9]+)\)", error)
    code = match[1] if match else ""
    low = error.lower()
    if code in {
        "ExpiredToken",
        "ExpiredTokenException",
        "InvalidClientTokenId",
        "UnrecognizedClientException",
    } or any(
        word in low
        for word in (
            "token has expired",
            "session has expired",
            "sso session",
            "refresh failed",
            "reauthenticate",
        )
    ):
        hint = "OIDC session expired; preserve state and resume through the manual workflow."
    elif result.returncode == 253:
        hint = "Temporary OIDC credentials unavailable; check runtime role setup."
    elif code in {"AccessDenied", "AccessDeniedException", "UnauthorizedOperation"}:
        hint = "Runtime permission denied; preserve receipt for review."
    elif result.returncode == 252:
        hint = "AWS CLI argument rejected. Preserve this receipt for compatibility review."
    elif code in {
        "ResourceNotFoundException",
        "ImageNotFoundException",
        "RepositoryNotFoundException",
    }:
        hint = "Expected resource is missing. Preserve this receipt; do not recreate it."
    else:
        hint = "AWS read failed. Check connectivity and preserve this receipt."
    return (
        f"{service} {operation} failed (exit {result.returncode}"
        + (f", {code}" if code else "")
        + "). "
        + hint
    )


def no_secret_fields(value):
    if isinstance(value, dict):
        require(
            not (
                {
                    "ClientSecret",
                    "SecretString",
                    "SecretBinary",
                    "AccessKeyId",
                    "SecretAccessKey",
                    "SessionToken",
                }
                & value.keys()
            ),
            "Unexpected secret field in provider output; output discarded",
        )
        for item in value.values():
            no_secret_fields(item)
    elif isinstance(value, list):
        for item in value:
            no_secret_fields(item)


class EvidenceAWS(deploy.ReadOnlyAWS):
    def __init__(self, report, runner=subprocess.run):
        super().__init__(True)
        self.report, self.runner = report, runner
        self.calls = report["calls"]

    def environment(self):
        binding.actions_environment()
        value = self("sts", "get-caller-identity")
        prefix = "arn:aws:sts::418638389566:assumed-role/fitfinity-test-github-runtime/"
        require(
            value.get("Account") == "418638389566"
            and value.get("Arn", "").startswith(prefix)
            and re.fullmatch(r"[A-Za-z0-9+=,.@_-]+", value["Arn"][len(prefix) :]),
            "Unexpected runtime identity",
        )
        return value["Arn"]

    def __call__(self, service, operation, *args, region=None, missing=False):
        require((service, operation) in READS, "Read-only collector refuses this operation")
        region = region or deploy.CONFIG["region"]
        require(
            region == deploy.CONFIG["region"] or (service == "freetier" and region == "us-east-1"),
            "Unexpected region",
        )
        forbidden = {
            "--debug",
            "--endpoint-url",
            "--no-verify-ssl",
            "--profile",
            "--region",
            "--output",
            "--cli-input-json",
            "--cli-input-yaml",
            "--max-items",
            "--starting-token",
        }
        require(not (set(args) & forbidden), "Unreviewed CLI override refused")
        if operation == "describe-user-pool-client":
            require(
                "--query" in args and args[args.index("--query") + 1] == deploy.client_projection(),
                "Secret-safe Cognito projection required",
            )
        if service == "ecr":
            require(
                "--repository-name" in args
                and args[args.index("--repository-name") + 1] == "fitfinity-test-api",
                "Wrong ECR repository",
            )
            flag = "--image-ids" if operation == "batch-get-image" else "--image-id"
            require(
                flag in args and args[args.index(flag) + 1] == "imageDigest=" + binding.DIGEST,
                "Wrong ECR digest",
            )
        call = {
            "service": service,
            "operation": operation,
            "region": region,
            "arguments": list(args),
            "status": "started",
        }
        self.calls.append(call)
        note(f"  READ {service} {operation}")
        command = [
            "aws",
            service,
            operation,
            *args,
            "--region",
            region,
            "--output",
            "json",
            "--no-cli-pager",
            "--no-cli-auto-prompt",
            "--cli-error-format",
            "legacy",
            "--cli-connect-timeout",
            "10",
            "--cli-read-timeout",
            "30",
        ]
        # CLI automatically retrieves complete collections. ECR is explicitly one page,
        # because the unchanged exception validator requires exactly four complete findings.
        if service == "ecr" and "--no-paginate" not in args:
            command.append("--no-paginate")
        env = {
            **os.environ,
            "AWS_PAGER": "",
            "AWS_CLI_AUTO_PROMPT": "off",
            "AWS_IGNORE_CONFIGURED_ENDPOINT_URLS": "true",
            "AWS_MAX_ATTEMPTS": "2",
        }
        try:
            result = self.runner(command, capture_output=True, text=True, timeout=90, env=env)
        except subprocess.TimeoutExpired:
            call["status"] = "timeout"
            raise RuntimeError(f"{service} {operation} timed out; no write was attempted") from None
        if result.returncode:
            call["status"] = "failed"
            if missing and operation == "describe-stacks" and "--stack-name" in args:
                name = args[args.index("--stack-name") + 1]
                if (
                    "(ValidationError)" in result.stderr
                    and f"Stack with id {name} does not exist" in result.stderr
                ):
                    call["status"] = "absent"
                    return None
            message = safe_error(service, operation, result)
            call["error"] = message
            raise RuntimeError(message)
        try:
            value = json.loads(result.stdout)
        except (ValueError, TypeError):
            call["status"] = "invalid-json"
            raise RuntimeError(
                f"{service} {operation} returned invalid JSON; output discarded"
            ) from None
        no_secret_fields(value)
        call.update(status="read", response=value)
        require(
            (service, operation) == ("ecr", "describe-image-scan-findings")
            or not any(value.get(k) for k in ("NextToken", "nextToken", "Marker", "NextMarker")),
            "Incomplete pagination; evidence retained, verification stopped",
        )
        return value


def github_main(report):
    binding.verify_main(report)


def image_review(report, aws, candidate, checked_at):
    binding.review_image(report, aws, checked_at)


def foundation_review(report, aws, auth):
    db = auth.db
    db.network()
    stack = db.one(
        aws("cloudformation", "describe-stacks", "--stack-name", db.FOUNDATION)["Stacks"],
        "Foundation missing",
    )
    require(
        db.stack_template(stack) == json.loads((ROOT / "test-foundation.json").read_text()),
        "Foundation template drift",
    )
    policy = json.loads(
        aws("cloudformation", "get-stack-policy", "--stack-name", db.FOUNDATION)["StackPolicyBody"]
    )
    require(
        any(
            p.get("Effect") == "Deny"
            and p.get("Principal") == "*"
            and "Condition" not in p
            and p.get("Resource") == "LogicalResourceId/Database"
            and set(p.get("Action", [])) >= {"Update:Replace", "Update:Delete"}
            for p in policy.get("Statement", [])
        ),
        "Database replacement/deletion protection differs",
    )
    report["foundation_metadata_verified"] = True


def egress_review(report, aws, context, db):
    egress = EgressOperator(context=context)
    stack = db.one(
        aws("cloudformation", "describe-stacks", "--stack-name", egress.FAILED_ARN)["Stacks"],
        "Egress missing",
    )
    require(
        stack["StackId"] == egress.FAILED_ARN
        and stack["StackStatus"] in {"CREATE_COMPLETE", "UPDATE_COMPLETE"}
        and db.stack_template(stack) == egress.TEMPLATE,
        "Egress template/state drift",
    )
    egress.verify(stack, check_host=False)
    report["egress_metadata_verified"] = True


def secrets_review(report, auth):
    auth.credentials_review()
    report["database_secret_metadata_verified"] = True
    stack = auth.before_secret()
    require(
        stack and stack["StackId"] == deploy.CONFIG["auth_stack"], "Authentication stack differs"
    )
    require(
        report.get("auth_secret_has_value") is True
        and report.get("auth_secret_arn") == deploy.CONFIG["auth_secret"]
        and report.get("auth_secret_version_id") == deploy.CONFIG["auth_version"],
        "Authentication secret version drift",
    )
    report["auth_secret_metadata_verified"] = True


def collect(report, aws, check_github=github_main):
    def step(name, action):
        row = {"name": name, "status": "running"}
        report["steps"].append(row)
        note("CHECK " + name)
        action()
        row["status"] = "passed"
        note("PASS " + name, "32")

    candidate = evidence(report, now())
    report["identity"] = aws.environment()
    capacity = aws("lambda", "get-account-settings")
    require(
        capacity.get("AccountLimit", {}).get("UnreservedConcurrentExecutions", 0) >= 102,
        "Insufficient unreserved capacity",
    )
    report["capacity"] = capacity
    step("unchanged GitHub main", lambda: check_github(report))
    step("AWS account and explicit profile", lambda: report.update(identity=aws.environment()))
    step(
        "exact current image and latest existing scan",
        lambda: image_review(report, aws, candidate, now()),
    )
    context = OperatorContext(report=report, aws_call=aws)
    auth = AuthenticationSecretOperator(context=context)
    step(
        "existing foundation, private network and RDS metadata",
        lambda: foundation_review(report, aws, auth),
    )
    step(
        "existing NAT configuration and routes",
        lambda: egress_review(report, aws, context, auth.db),
    )
    step("existing Cognito pool/client/MFA configuration", auth.cognito_review)
    step(
        "retained credential and authentication secret metadata",
        lambda: secrets_review(report, auth),
    )
    # No historical scan, initialization, host command or runtime invocation.
    evidence(report, now())
    binding.acceptance(
        report["current_scan_pages"],
        binding.DIGEST,
        report["candidate_provenance"],
        report["approval"],
        now(),
    )
    report.update(status="metadata_verified_runtime_pending", metadata_verified=True)
