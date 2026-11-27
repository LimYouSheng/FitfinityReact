"""Run a reviewed probe lifecycle step from the protected manual Actions workflow."""

import argparse
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from deployment_profile import DEVELOPER, identities, load
from operator_checks import require
from operator_errors import OperatorFailure, decode_response, safe_reason
from operator_errors import failure_code as failure_code
from schema_probe_execution import execute

ALLOWED = {
    ("sts", "get-caller-identity"),
    ("iam", "get-role"),
    ("rds", "describe-db-instances"),
    ("ec2", "describe-subnets"),
    ("ec2", "describe-security-groups"),
    ("secretsmanager", "describe-secret"),
    ("ecr", "describe-image-scan-findings"),
    ("cloudformation", "create-stack"),
    ("cloudformation", "describe-stacks"),
    ("cloudformation", "get-template"),
    ("cloudformation", "get-template"),
    ("cloudformation", "describe-stack-resource"),
    ("cloudformation", "delete-stack"),
    ("lambda", "get-function"),
    ("lambda", "get-account-settings"),
    ("lambda", "get-function-concurrency"),
    ("lambda", "get-policy"),
    ("lambda", "list-function-url-configs"),
    ("lambda", "list-event-source-mappings"),
    ("lambda", "invoke"),
}


def aws(service, operation, parameters, *, profile=DEVELOPER, purpose="probe"):
    """Suppress raw provider replies/errors and never retry writes automatically."""
    require(purpose in {"probe", "upgrade"}, "Unknown private operator purpose")
    additional = (
        {("rds", "describe-db-snapshots"), ("lambda", "tag-resource")}
        if purpose == "upgrade"
        else set()
    )
    require((service, operation) in ALLOWED | additional, "AWS operation refused")
    read_timeout = 135 if purpose == "upgrade" and operation == "invoke" else 75
    require(
        not any(key.startswith("AWS_ENDPOINT_URL") for key in os.environ),
        "Endpoint override refused",
    )
    with tempfile.TemporaryDirectory(prefix="fitfinity-probe-") as directory:
        response = Path(directory) / "response.json"
        command = [
            "aws",
            service,
            operation,
            "--region",
            identities(profile)["region"],
            "--output",
            "json",
            "--no-cli-pager",
            "--cli-connect-timeout",
            "10",
            "--cli-read-timeout",
            str(read_timeout),
        ]
        if operation == "invoke":
            arguments = {
                "FunctionName": "--function-name",
                "InvocationType": "--invocation-type",
                "LogType": "--log-type",
                "Payload": "--payload",
            }
            require(set(parameters) <= arguments.keys(), "Unsupported invocation parameter")
            for key, value in parameters.items():
                command.extend([arguments[key], value])
            command.extend(["--cli-binary-format", "raw-in-base64-out", str(response)])
        else:
            command.extend(["--cli-input-json", json.dumps(parameters)])
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=read_timeout + 15,
                env={
                    **os.environ,
                    "AWS_PAGER": "",
                    "AWS_MAX_ATTEMPTS": "1",
                    "AWS_IGNORE_CONFIGURED_ENDPOINT_URLS": "true",
                    "AWS_CLI_AUTO_PROMPT": "off",
                },
            )
        except subprocess.TimeoutExpired:
            raise OperatorFailure(
                f"AWS {service}/{operation} failed; code=LocalProcessTimeout; "
                "exit_status=unavailable; outcome uncertain; "
                "inspect owned resource state before retry"
            ) from None
        if result.returncode:
            if (service, operation) == ("lambda", "get-policy") and re.search(
                r"\(ResourceNotFoundException\) when calling the GetPolicy operation", result.stderr
            ):
                return {"absent": True}
            raise OperatorFailure(
                f"AWS {service}/{operation} failed; code={failure_code(result.stderr)}; "
                f"exit_status={result.returncode}; inspect owned resource state before retry"
            )
        value = decode_response(result.stdout, service, operation)
        if operation == "invoke":
            require(response.stat().st_size <= 2 * 1024 * 1024, "Probe response too large")
            value["Payload"] = json.loads(response.read_text())
        return value


def main():
    """Preserve a sanitized receipt even when a lifecycle step fails."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode", choices=["create", "collect", "cleanup", "cleanup-check"], required=True
    )
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--template-sha256", required=True)
    parser.add_argument("--operation-id", required=True)
    parser.add_argument("--image-receipt", type=Path)
    parser.add_argument("--stack-id")
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    profile = load(args.profile)
    target = identities(profile)
    require(
        os.getenv("GITHUB_REPOSITORY") == profile["github_repository"]
        and os.getenv("GITHUB_REF") == "refs/heads/main"
        and os.getenv("GITHUB_EVENT_NAME") == "workflow_dispatch"
        and os.getenv("GITHUB_WORKFLOW_REF")
        == profile["github_repository"] + "/.github/workflows/aws-schema-probe.yml@refs/heads/main",
        "Protected manual main workflow required",
    )
    source = os.environ["GITHUB_SHA"]
    require(
        subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip() == source,
        "Checkout source differs",
    )
    review = json.loads(args.review.read_text())
    sql = Path(__file__).with_name("read-schema.sql").read_bytes()
    if args.mode.startswith("cleanup"):
        source = review["bindings"]["source_sha"]
        require(re.fullmatch(r"[0-9a-f]{40}", source), "Archived source differs")
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", source, os.environ["GITHUB_SHA"]], check=True
        )
        sql = subprocess.check_output(
            ["git", "show", source + ":backend/infrastructure/read-schema.sql"]
        )
    receipt = {
        "mode": args.mode,
        "profile_sha256": target["profile_sha256"],
        "operation_id": args.operation_id,
        "source_sha": source,
        "state": "not_started",
        "deployment_decision": "HOLD",
    }
    from operation_journal import Journal

    journal = Journal(args.receipt)

    def save(value):
        receipt.update(value)
        journal.save(receipt)

    try:
        receipt.update(
            execute(
                args.mode,
                review,
                args.template_sha256,
                source,
                sql,
                args.operation_id,
                json.loads(args.image_receipt.read_text()) if args.image_receipt else {},
                lambda service, operation, params: aws(service, operation, params, profile=profile),
                stack_id=args.stack_id,
                profile=profile,
                persist=save,
            )
        )
    except Exception as error:
        receipt["reason"] = safe_reason(error)
        receipt["state"] = "failed_or_uncertain"
        receipt["next"] = "Inspect owned stack; do not infer rollback or replay mutations"
        raise RuntimeError("Probe step failed: " + receipt["reason"]) from None
    finally:
        journal.save(receipt)
    print("Probe step receipt retained; staff deployment remains HOLD")


if __name__ == "__main__":
    main()
