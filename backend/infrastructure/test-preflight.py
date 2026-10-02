import datetime
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ACCOUNT = "418638389566"
PROFILE = "fitfinity-test"
REGION = "ap-southeast-1"
DIGEST = "sha256:63c6e6f20ffd3236e9d6582494270525ebdecc267e9bee8dc339bc6588a7eb2f"
ALLOWED = {
    ("sts", "get-caller-identity"),
    ("freetier", "get-account-plan-state"),
    ("lambda", "get-account-settings"),
    ("ec2", "describe-availability-zones"),
    ("ec2", "describe-vpcs"),
    ("ec2", "describe-instance-type-offerings"),
    ("rds", "describe-orderable-db-instance-options"),
    ("rds", "describe-db-instances"),
    ("cloudformation", "list-stacks"),
    ("cognito-idp", "list-user-pools"),
    ("ecr", "describe-image-scan-findings"),
}
COLOR = sys.stdout.isatty()


def note(message, code="36"):
    print(
        ("\033[" + code + "m" if COLOR else "") + message + ("\033[0m" if COLOR else ""), flush=True
    )


def aws(service, operation, *args, region=REGION):
    if (service, operation) not in ALLOWED:
        raise RuntimeError("Non-read-only operation refused")
    result = subprocess.run(
        [
            "aws",
            service,
            operation,
            *args,
            "--profile",
            PROFILE,
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
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(f"{service} {operation}: {result.stderr.strip()}")
    return json.loads(result.stdout)


def main():
    note("Fitfinity AWS infrastructure preflight — READ ONLY")
    print("No resources, secrets, repository files or account settings will be changed.")
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
    overrides = sorted(
        k
        for k, v in os.environ.items()
        if v and (k in forbidden or k.startswith("AWS_ENDPOINT_URL"))
    )
    if overrides:
        raise RuntimeError(
            "Remove credential/config/endpoint environment overrides: " + ", ".join(overrides)
        )
    os.environ["AWS_IGNORE_CONFIGURED_ENDPOINT_URLS"] = "true"
    os.environ["AWS_PAGER"] = ""
    os.environ["AWS_CLI_AUTO_PROMPT"] = "off"
    os.environ["AWS_MAX_ATTEMPTS"] = "2"
    identity = aws("sts", "get-caller-identity")
    if (
        identity.get("Account") != ACCOUNT
        or identity.get("Arn") != f"arn:aws:iam::{ACCOUNT}:user/fitfinity-deployer"
    ):
        raise RuntimeError("Expected account and fitfinity-deployer IAM identity were not verified")
    report = {
        "created_at_utc": datetime.datetime.now(datetime.UTC).isoformat(),
        "account": ACCOUNT,
        "region": REGION,
        "image_digest": DIGEST,
        "read_only": True,
        "checks": {},
    }
    checks = [
        (
            "account_plan",
            "freetier",
            "get-account-plan-state",
            [
                "--query",
                (
                    "{Plan:accountPlanType,Status:accountPlanStatus,Credits:accou"
                    "ntPlanRemainingCredits,Expires:accountPlanExpirationDate}"
                ),
            ],
            "us-east-1",
        ),
        ("lambda_limits", "lambda", "get-account-settings", [], REGION),
        (
            "availability_zones",
            "ec2",
            "describe-availability-zones",
            [
                "--query",
                (
                    "AvailabilityZones[?State==`available`].{Name:ZoneName,Id:Zon"
                    "eId,OptIn:OptInStatus}"
                ),
            ],
            REGION,
        ),
        (
            "postgres17_micro_options",
            "rds",
            "describe-orderable-db-instance-options",
            [
                "--engine",
                "postgres",
                "--db-instance-class",
                "db.t4g.micro",
                "--vpc",
                "--query",
                (
                    "OrderableDBInstanceOptions[?starts_with(EngineVersion, '17.'"
                    ") && StorageType=='gp3'].{Version:EngineVersion,MinGiB:MinSt"
                    "orageSize,MaxGiB:MaxStorageSize,Encryption:SupportsStorageEn"
                    "cryption,AZs:AvailabilityZones[].Name}"
                ),
            ],
            REGION,
        ),
        (
            "existing_databases",
            "rds",
            "describe-db-instances",
            [
                "--query",
                (
                    "DBInstances[].{Id:DBInstanceIdentifier,Engine:Engine,Version"
                    ":EngineVersion,Class:DBInstanceClass,Status:DBInstanceStatus"
                    ",Public:PubliclyAccessible}"
                ),
            ],
            REGION,
        ),
        (
            "vpcs",
            "ec2",
            "describe-vpcs",
            ["--query", "Vpcs[].{Id:VpcId,CIDR:CidrBlock,Default:IsDefault}"],
            REGION,
        ),
        (
            "small_arm_instance_offerings",
            "ec2",
            "describe-instance-type-offerings",
            [
                "--location-type",
                "availability-zone",
                "--filters",
                "Name=instance-type,Values=t4g.nano",
                "--query",
                "InstanceTypeOfferings[].{Type:InstanceType,AZ:Location}",
            ],
            REGION,
        ),
        (
            "fitfinity_stacks",
            "cloudformation",
            "list-stacks",
            [
                "--query",
                (
                    "StackSummaries[?contains(StackName, 'fitfinity') && StackSta"
                    "tus!='DELETE_COMPLETE'].{Name:StackName,Status:StackStatus}"
                ),
            ],
            REGION,
        ),
        (
            "staff_pool_inventory",
            "cognito-idp",
            "list-user-pools",
            [
                "--max-results",
                "60",
                "--query",
                "UserPools[?contains(Name, 'fitfinity')].{Id:Id,Name:Name}",
            ],
            REGION,
        ),
        (
            "image_scan",
            "ecr",
            "describe-image-scan-findings",
            [
                "--repository-name",
                "fitfinity-test-api",
                "--image-id",
                "imageDigest=" + DIGEST,
                "--query",
                (
                    "{Digest:imageId.imageDigest,Status:imageScanStatus.status,Co"
                    "mpleted:imageScanFindings.imageScanCompletedAt,Counts:imageS"
                    "canFindings.findingSeverityCounts}"
                ),
            ],
            REGION,
        ),
    ]
    for label, service, operation, args, region in checks:
        note("Reading " + label.replace("_", " ") + "…")
        report["checks"][label] = aws(service, operation, *args, region=region)
    scan = report["checks"]["image_scan"]
    if scan.get("Digest") != DIGEST:
        raise RuntimeError("Image scan digest mismatch")
    report["limitations"] = [
        (
            "Read permissions and regional offerings do not prove free-pl"
            "an eligibility or provisioning success."
        ),
        ("No price quote, deployment approval, security pass or secrets inspection is implied."),
        (
            "t4g.nano offerings are inventory only; no NAT instance or pa"
            "id egress option is selected."
        ),
        (
            "PostgreSQL version, outbound networking, secret injection an"
            "d migration execution need deployment review."
        ),
    ]
    if not report["checks"]["postgres17_micro_options"]:
        report["limitations"].append(
            "No PostgreSQL 17 db.t4g.micro gp3 options were returned; resolve before provisioning."
        )
    folder = Path.home() / "Downloads"
    folder.mkdir(exist_ok=True)
    fd, filename = tempfile.mkstemp(
        prefix="Fitfinity_AWS_Infrastructure_Preflight_", suffix=".json", dir=folder
    )
    with os.fdopen(fd, "w") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    note("READ-ONLY PREFLIGHT COLLECTED", "32")
    print("Report: " + filename)
    print(
        "Share this JSON report for infrastructure review. It contain"
        "s account/resource metadata, not secret values."
    )
    print(
        "No cloud writes were performed. This receipt is not an appli"
        "cation deployment or security pass."
    )


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        note("STOPPED: " + str(exc), "31")
        print("No cloud writes were performed.", file=sys.stderr)
        sys.exit(1)
