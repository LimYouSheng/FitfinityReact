import datetime
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

TEMPLATE_TEXT = (Path(__file__).resolve().parent / "test-foundation.json").read_text()
TEMPLATE_HASH = hashlib.sha256(TEMPLATE_TEXT.encode()).hexdigest()
ACCOUNT = "418638389566"
REGION = "ap-southeast-1"
PROFILE = "fitfinity-test"
STACK = "fitfinity-test-foundation"
CHANGE = "foundation-" + TEMPLATE_HASH[:20]
TAGS = [
    {"Key": "Application", "Value": "Fitfinity"},
    {"Key": "Environment", "Value": "test"},
    {"Key": "ManagedBy", "Value": "fitfinity-foundation-planner"},
    {"Key": "TemplateSHA256", "Value": TEMPLATE_HASH},
]
ALLOWED = {
    ("sts", "get-caller-identity"),
    ("ec2", "describe-vpcs"),
    ("rds", "describe-orderable-db-instance-options"),
    ("rds", "describe-db-instances"),
    ("cloudformation", "validate-template"),
    ("cloudformation", "describe-stacks"),
    ("cloudformation", "describe-change-set"),
    ("cloudformation", "create-change-set"),
    ("cloudformation", "get-template"),
}


def note(message):
    print(message, flush=True)


def aws(service, operation, *args, missing_ok=False):
    if (service, operation) not in ALLOWED:
        raise RuntimeError("Unsupported operation refused: " + service + " " + operation)
    result = subprocess.run(
        [
            "aws",
            service,
            operation,
            *args,
            "--profile",
            PROFILE,
            "--region",
            REGION,
            "--output",
            "json",
            "--no-cli-pager",
            "--no-cli-auto-prompt",
            "--cli-connect-timeout",
            "10",
            "--cli-read-timeout",
            "30",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode:
        error = result.stderr.strip()
        if (
            missing_ok
            and ("ValidationError" in error or "ChangeSetNotFound" in error)
            and "does not exist" in error
        ):
            return None
        raise RuntimeError(service + " " + operation + ": " + error)
    return json.loads(result.stdout) if result.stdout.strip() else {}


def main():
    note("Fitfinity AWS foundation — CREATE PLAN ONLY")
    note("Creates a CloudFormation change set and possibly a REVIEW_IN_PROGRESS stack placeholder.")
    note(
        "Does not execute it: no database, VPC, compute, secrets or p"
        "aid runtime resources are provisioned."
    )
    forbidden = {
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AWS_SECURITY_TOKEN",
        "AWS_ROLE_ARN",
        "AWS_WEB_IDENTITY_TOKEN_FILE",
        "AWS_CONFIG_FILE",
        "AWS_SHARED_CREDENTIALS_FILE",
    }
    if any(
        v and (k in forbidden or k.startswith("AWS_ENDPOINT_URL")) for k, v in os.environ.items()
    ):
        raise RuntimeError(
            "Remove AWS credential/config/endpoint environment overrides before continuing"
        )
    os.environ.update(
        AWS_PAGER="",
        AWS_CLI_AUTO_PROMPT="off",
        AWS_IGNORE_CONFIGURED_ENDPOINT_URLS="true",
        AWS_MAX_ATTEMPTS="2",
    )
    identity = aws("sts", "get-caller-identity")
    if (
        identity.get("Account") != ACCOUNT
        or identity.get("Arn") != f"arn:aws:iam::{ACCOUNT}:user/fitfinity-deployer"
    ):
        raise RuntimeError(
            "Expected test account and fitfinity-deployer identity were not verified"
        )
    template = json.loads(TEMPLATE_TEXT)
    existing = aws("cloudformation", "describe-stacks", "--stack-name", STACK, missing_ok=True)
    if existing:
        stack = existing["Stacks"][0]
        if stack["StackStatus"] != "REVIEW_IN_PROGRESS":
            raise RuntimeError(
                "A non-preview foundation stack already exists; review it before any further action"
            )
        actual = {x["Key"]: x["Value"] for x in stack.get("Tags", [])}
        # A CREATE change set can leave a placeholder whose tags are not yet applied.
        # Ownership is established below by the exact named change set and template.
        if actual and any(actual.get(x["Key"]) != x["Value"] for x in TAGS):
            raise RuntimeError("Foundation placeholder tags do not match this planner")
    old = aws(
        "cloudformation",
        "describe-change-set",
        "--stack-name",
        STACK,
        "--change-set-name",
        CHANGE,
        missing_ok=True,
    )
    if existing and old is None:
        raise RuntimeError("Unrecognized foundation placeholder; no changes were made")
    if not old:
        vpcs = aws("ec2", "describe-vpcs")["Vpcs"]
        import ipaddress

        proposed = ipaddress.ip_network("10.84.0.0/16")
        for vpc in vpcs:
            for block in vpc.get("CidrBlockAssociationSet", [{"CidrBlock": vpc["CidrBlock"]}]):
                if block.get("CidrBlockState", {}).get("State") in {"disassociated", "failed"}:
                    continue
                if proposed.overlaps(ipaddress.ip_network(block["CidrBlock"])):
                    raise RuntimeError(
                        "Proposed VPC range overlaps an existing VPC; review addressing first"
                    )
        databases = aws("rds", "describe-db-instances")["DBInstances"]
        if any(db["DBInstanceIdentifier"] == "fitfinity-test-db" for db in databases):
            raise RuntimeError("Database name already exists outside this initial plan")
        options = aws(
            "rds",
            "describe-orderable-db-instance-options",
            "--engine",
            "postgres",
            "--engine-version",
            "17.11",
            "--db-instance-class",
            "db.t4g.micro",
            "--vpc",
        )["OrderableDBInstanceOptions"]
        if not any(
            x.get("StorageType") == "gp3"
            and x.get("SupportsStorageEncryption")
            and x.get("MinStorageSize", 999) <= 20
            and x.get("MaxStorageSize", 0) >= 30
            and {"ap-southeast-1a", "ap-southeast-1b"}.issubset(
                {z["Name"] for z in x.get("AvailabilityZones", [])}
            )
            for x in options
        ):
            raise RuntimeError(
                "The reviewed PostgreSQL 17.11 encrypted gp3 configuration is unavailable"
            )
        with tempfile.TemporaryDirectory(prefix="fitfinity-foundation-") as td:
            source = Path(td) / "template.json"
            source.write_text(TEMPLATE_TEXT)
            aws("cloudformation", "validate-template", "--template-body", "file://" + str(source))
            note("Submitting the 20-resource foundation preview to AWS…")
            aws(
                "cloudformation",
                "create-change-set",
                "--stack-name",
                STACK,
                "--change-set-name",
                CHANGE,
                "--change-set-type",
                "CREATE",
                "--template-body",
                "file://" + str(source),
                "--description",
                (
                    "Fitfinity isolated test foundation preview; no execution aut"
                    "horized by this planner"
                ),
                "--client-token",
                CHANGE,
                "--tags",
                json.dumps(TAGS),
            )
    else:
        note("Reusing the existing exact foundation preview.")
    deadline = time.monotonic() + 180
    while True:
        plan = aws(
            "cloudformation",
            "describe-change-set",
            "--stack-name",
            STACK,
            "--change-set-name",
            CHANGE,
        )
        if plan["Status"] == "CREATE_COMPLETE":
            break
        if plan["Status"] not in {"CREATE_PENDING", "CREATE_IN_PROGRESS"}:
            raise RuntimeError(
                "Change set is not ready: " + plan["Status"] + " " + plan.get("StatusReason", "")
            )
        if time.monotonic() >= deadline:
            raise RuntimeError(
                "Preview still processing. Rerun this same script to read its"
                " status; it will not execute it"
            )
        note("AWS is preparing the preview…")
        time.sleep(5)
    if plan.get("ExecutionStatus") != "AVAILABLE":
        raise RuntimeError(
            "Change set has already been executed or is unavailable; review its status"
        )
    returned = aws(
        "cloudformation",
        "get-template",
        "--stack-name",
        STACK,
        "--change-set-name",
        CHANGE,
        "--template-stage",
        "Original",
    )["TemplateBody"]
    if isinstance(returned, str):
        returned = json.loads(returned)
    if returned != template:
        raise RuntimeError("AWS preview template differs from the embedded reviewed template")
    changes = [x["ResourceChange"] for x in plan.get("Changes", [])]
    if len(changes) != len(template["Resources"]) or {
        x["LogicalResourceId"] for x in changes
    } != set(template["Resources"]):
        raise RuntimeError("Unexpected preview resource set")
    if any(
        x["Action"] != "Add"
        or x["ResourceType"] != template["Resources"][x["LogicalResourceId"]]["Type"]
        for x in changes
    ):
        raise RuntimeError("Unexpected change action or resource type")
    report = {
        "created_at_utc": datetime.datetime.now(datetime.UTC).isoformat(),
        "account": ACCOUNT,
        "region": REGION,
        "stack": STACK,
        "change_set_name": CHANGE,
        "change_set_id": plan["ChangeSetId"],
        "template_sha256": TEMPLATE_HASH,
        "executed": False,
        "template": template,
        "changes": changes,
        "future_execution_costs": (
            "Database compute, 20 GiB gp3 (autoscaling ceiling 30 GiB), m"
            "anaged secret, and applicable backup/IO/transfer charges con"
            "sume credits or incur costs. Obtain current cost review befo"
            "re execution."
        ),
        "limitations": [
            (
                "No application, internet egress, Cognito, migration or first"
                "-owner bootstrap is deployed."
            ),
            (
                "Change-set creation is not proof of service entitlement, ava"
                "ilable capacity, successful provisioning or app health."
            ),
            (
                "Single-AZ database uses two subnet AZs for RDS subnet requir"
                "ements; it is not Multi-AZ failover."
            ),
            (
                "Deletion protection and snapshot policies require deliberate"
                " reviewed cleanup; stopping testing does not stop charges."
            ),
        ],
    }
    folder = Path.home() / "Downloads"
    folder.mkdir(exist_ok=True)
    fd, name = tempfile.mkstemp(prefix="Fitfinity_AWS_Foundation_Plan_", suffix=".json", dir=folder)
    with os.fdopen(fd, "w") as f:
        json.dump(report, f, indent=2)
        f.write("\n")
    note("FOUNDATION PLAN VERIFIED — NOT EXECUTED")
    note("Preview: " + plan["ChangeSetId"])
    note("Report: " + name)
    note(
        "Share this report for review. No paid foundation resources w"
        "ere provisioned by this script."
    )


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, OSError, KeyError, subprocess.TimeoutExpired) as exc:
        note("STOPPED: " + str(exc))
        note(
            "This script never executes change sets or deletes resources."
            " A preview/stack placeholder may remain."
        )
        sys.exit(1)
