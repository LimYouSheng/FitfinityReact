"""Repository entry point for test infrastructure, read-only audit and current image candidates.

Bootstrap/recovery are explicit operations. They are never a release algorithm.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from authentication_secrets import AuthenticationSecretOperator
from egress_execution import EgressOperator
from operator_context import OperatorContext

ROOT = Path(__file__).resolve().parent
CONFIG = json.loads((ROOT / "deployment-test.json").read_text())
READS = {
    ("sts", "get-caller-identity"),
    ("freetier", "get-account-plan-state"),
    ("cloudformation", "describe-stacks"),
    ("cloudformation", "get-template"),
    ("cloudformation", "list-stack-resources"),
    ("cloudformation", "get-stack-policy"),
    ("rds", "describe-db-instances"),
    ("rds", "describe-db-parameters"),
    ("ec2", "describe-security-groups"),
    ("ec2", "describe-subnets"),
    ("ec2", "describe-route-tables"),
    ("ec2", "describe-instances"),
    ("ec2", "describe-volumes"),
    ("ec2", "describe-network-interfaces"),
    ("ec2", "describe-instance-credit-specifications"),
    ("secretsmanager", "describe-secret"),
    ("secretsmanager", "get-resource-policy"),
    ("cognito-idp", "describe-user-pool"),
    ("cognito-idp", "describe-user-pool-client"),
    ("cognito-idp", "get-user-pool-mfa-config"),
    ("ecr", "describe-image-scan-findings"),
}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def client_projection():
    template = json.loads((ROOT / "test-cognito-accepted.json").read_text())
    keys = sorted(
        set(template["Resources"]["StaffClient"]["Properties"]) - {"GenerateSecret"}
        | {
            "ClientId",
            "AllowedOAuthFlowsUserPoolClient",
            "CallbackURLs",
            "LogoutURLs",
            "SupportedIdentityProviders",
        }
    )
    return (
        "UserPoolClient.{"
        + ",".join(k + ":" + k for k in keys)
        + ',HasClientSecret:ClientSecret != `null` && ClientSecret != `""`}'
    )


class ReadOnlyAWS:
    def __init__(self, actions=False):
        self.actions = actions
        self.calls = []

    def environment(self):
        blocked = {
            "AWS_CONFIG_FILE",
            "AWS_SHARED_CREDENTIALS_FILE",
            "AWS_CA_BUNDLE",
            "AWS_WEB_IDENTITY_TOKEN_FILE",
            "AWS_ROLE_ARN",
            "AWS_SECURITY_TOKEN",
        }
        if not self.actions:
            blocked |= {"AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"}
        require(
            not any(
                value and (key in blocked or key.startswith("AWS_ENDPOINT_URL"))
                for key, value in os.environ.items()
            ),
            "AWS credential/config/endpoint override refused",
        )
        if self.actions:
            require(
                os.getenv("GITHUB_ACTIONS") == "true"
                and os.getenv("GITHUB_REPOSITORY") == CONFIG["repository"]
                and os.getenv("GITHUB_REF") == "refs/heads/main",
                "Unexpected Actions repository or branch",
            )
            require(
                all(
                    os.getenv(key)
                    for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN")
                ),
                "Actions requires temporary OIDC credentials",
            )
        identity = self("sts", "get-caller-identity")
        require(identity.get("Account") == CONFIG["account"], "AWS account differs")
        if self.actions:
            expected = (
                f"arn:aws:sts::{CONFIG['account']}:assumed-role/fitfinity-test-github-verify/"
            )
            require(
                identity.get("Arn", "").startswith(expected)
                and re.fullmatch(r"[A-Za-z0-9+=,.@_-]+", identity["Arn"][len(expected) :]),
                "Unexpected Actions verification role",
            )
        else:
            require(
                identity.get("Arn") == f"arn:aws:iam::{CONFIG['account']}:user/fitfinity-deployer",
                "Expected fitfinity-deployer identity",
            )
        return identity["Arn"]

    def __call__(self, service, operation, *args, region=None, missing=False):
        require((service, operation) in READS, "Live audit refuses mutations and secret values")
        region = region or CONFIG["region"]
        require(
            region == CONFIG["region"] or (service == "freetier" and region == "us-east-1"),
            "Unexpected AWS region",
        )
        if operation == "describe-user-pool-client":
            require(
                "--query" in args and args[args.index("--query") + 1] == client_projection(),
                "Secret-safe Cognito projection required",
            )
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
            "--cli-connect-timeout",
            "10",
            "--cli-read-timeout",
            "30",
        ]
        if not self.actions:
            command.extend(["--profile", CONFIG["profile"]])
        self.calls.append({"service": service, "operation": operation})
        env = {
            **os.environ,
            "AWS_PAGER": "",
            "AWS_CLI_AUTO_PROMPT": "off",
            "AWS_IGNORE_CONFIGURED_ENDPOINT_URLS": "true",
            "AWS_MAX_ATTEMPTS": "2",
        }
        result = subprocess.run(command, capture_output=True, text=True, timeout=120, env=env)
        if result.returncode:
            # An absent exact stack is the only missing result used by the live audit.
            if missing and operation == "describe-stacks" and "--stack-name" in args:
                name = args[args.index("--stack-name") + 1]
                if (
                    "(ValidationError)" in result.stderr
                    and f"Stack with id {name} does not exist" in result.stderr
                ):
                    return None
            raise RuntimeError(f"{service} {operation} failed; provider response suppressed")
        return json.loads(result.stdout) if result.stdout.strip() else {}


def verify(report, aws):
    report["identity"] = aws.environment()
    plan = aws("freetier", "get-account-plan-state", region="us-east-1")
    require(
        plan.get("accountPlanType") == "FREE" and plan.get("accountPlanStatus") == "ACTIVE",
        "Accepted AWS account plan differs",
    )
    context = OperatorContext(report=report, aws_call=aws)
    auth = AuthenticationSecretOperator(context=context)
    db = auth.db
    db.network()
    row = db.one(
        aws("cloudformation", "describe-stacks", "--stack-name", db.FOUNDATION)["Stacks"],
        "Foundation missing",
    )
    require(
        db.stack_template(row) == json.loads((ROOT / "test-foundation.json").read_text()),
        "Foundation template drift",
    )
    policy = json.loads(
        aws("cloudformation", "get-stack-policy", "--stack-name", db.FOUNDATION)["StackPolicyBody"]
    )
    require(
        any(
            item.get("Effect") == "Deny"
            and item.get("Principal") == "*"
            and "Condition" not in item
            and item.get("Resource") == "LogicalResourceId/Database"
            and set(item.get("Action", [])) >= {"Update:Replace", "Update:Delete"}
            for item in policy.get("Statement", [])
        ),
        "Database replacement/deletion protection differs",
    )
    report["foundation_metadata_verified"] = True
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
    auth.cognito_review()
    auth.credentials_review()
    report["database_secret_metadata_verified"] = True
    row = auth.before_secret()
    require(row and row["StackId"] == CONFIG["auth_stack"], "Authentication stack differs")
    require(
        report.get("auth_secret_has_value") is True
        and report.get("auth_secret_arn") == CONFIG["auth_secret"]
        and report.get("auth_secret_version_id") == CONFIG["auth_version"],
        "Authentication version drift",
    )
    report["auth_secret_metadata_verified"] = True
    db.scan()
    # Native proof is historical, not reasserted by this metadata-only audit.
    report["metadata_verified"] = True


def status():
    return {
        "environment": CONFIG["environment"],
        "accepted_at": CONFIG["accepted_at"],
        "source": "recorded native/GitHub acceptance; not a live AWS query",
        "stages": CONFIG["stages"],
        "automatic_release_ready": False,
        "image_candidate_command": "image-candidate --actions --receipt <new-path>",
        "image_candidate_live_accepted": False,
        "release_blockers": CONFIG["release_blockers"],
    }


def run_stage(kind, name):
    stage = CONFIG["stages"].get(name)
    require(
        stage and stage["kind"] == kind, "Choose a stage from deploy.py status with its exact kind"
    )
    if stage["accepted"] and kind == "bootstrap":
        print(f"{name}: already accepted. No setup replay. Use verify for current AWS metadata.")
        return
    path = ROOT / stage["script"]
    require(path.is_file() and path.parent == ROOT, "Canonical operator missing")
    subprocess.run([sys.executable, str(path), *stage.get("arguments", [])], check=True)


def save_receipt(path, report):
    path = Path(path)
    # Exclusive creation avoids overwriting an earlier receipt or following its symlink.
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")


def main(argv=None):
    arguments = sys.argv[1:] if argv is None else argv
    if arguments[:1] == ["private-runtime"]:
        from private_runtime import main as private_main

        raise SystemExit(private_main(arguments[1:]))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=[
            "status",
            "verify",
            "deploy",
            "bootstrap",
            "review",
            "probe",
            "release",
            "recovery",
            "image-candidate",
            "image-accept",
        ],
    )
    parser.add_argument("stage", nargs="?")
    parser.add_argument("--actions", action="store_true")
    parser.add_argument("--receipt")
    parser.add_argument("--digest")
    parser.add_argument("--build-run", type=int)
    parser.add_argument("--build-attempt", type=int)
    parser.add_argument("--artifact-id", type=int)
    parser.add_argument("--approval-id")
    args = parser.parse_args(argv)
    require(
        not args.stage or args.command in {"bootstrap", "review", "probe", "release", "recovery"},
        "Unexpected stage",
    )
    require(
        not args.actions or args.command in {"verify", "image-candidate", "image-accept"},
        "Actions supports metadata verification or the separate image candidate job",
    )
    if args.command == "status":
        print(json.dumps(status(), indent=2))
    elif args.command == "deploy":
        raise RuntimeError(
            "Full release is not ready:\n- " + "\n- ".join(CONFIG["release_blockers"])
        )
    elif args.command == "image-accept":
        require(
            args.actions and args.receipt, "Image acceptance requires Actions and a new receipt"
        )
        from image_acceptance import accept_existing

        accept_existing(
            args.receipt,
            args.digest,
            args.build_run,
            args.build_attempt,
            args.artifact_id,
            args.approval_id,
        )
    elif args.command == "image-candidate":
        require(args.actions and args.receipt, "Image candidates require Actions and a new receipt")
        from release_image import create_candidate

        create_candidate(args.receipt)
    elif args.command == "verify":
        aws = ReadOnlyAWS(args.actions)
        report = {
            "checked_at": datetime.now(UTC).isoformat(),
            "account": CONFIG["account"],
            "region": CONFIG["region"],
            "read_only": True,
            "metadata_verified": False,
            "runtime_smoke_executed": False,
            "database_sql_executed": False,
            "app_deployed": False,
            "cloud_writes": [],
            "calls": aws.calls,
        }
        try:
            verify(report, aws)
            print("PASS — existing AWS metadata verified. App/runtime deployment remains pending.")
        except Exception as error:
            report["error"] = (
                str(error) if isinstance(error, RuntimeError) else type(error).__name__
            )
            raise
        finally:
            if args.receipt:
                save_receipt(args.receipt, report)
    else:
        run_stage(args.command, args.stage)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(
            f"\033[31mSTOPPED: "
            f"{error if isinstance(error, RuntimeError) else type(error).__name__}\033[0m",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
