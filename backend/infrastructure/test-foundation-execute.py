import datetime
import json
import os
import subprocess
import sys
import tempfile
import time
from decimal import Decimal
from pathlib import Path

TEMPLATE = json.loads((Path(__file__).resolve().parent / "test-foundation.json").read_text())
RECOVERY_HASH = "fc3671d622fce133ea5a2cec81d400e48de906269b2d61747aa61200b65bb5c1"
ACCOUNT = "418638389566"
REGION = "ap-southeast-1"
PROFILE = "fitfinity-test"
STACK = "fitfinity-test-foundation"
CHANGE = (
    "arn:aws:cloudformation:ap-southeast-1:418638389566:changeSet"
    "/foundation-67d405fd41489323c1ef/ea14ec3e-f149-418f-b279-5cf"
    "9a0f31428"
)
HASH = "67d405fd41489323c1efb89785f475e696f6149d429fa9a67318c35d55af07e4"
ALLOWED = {
    ("sts", "get-caller-identity"),
    ("pricing", "get-products"),
    ("freetier", "get-account-plan-state"),
    ("cloudformation", "describe-stacks"),
    ("cloudformation", "describe-change-set"),
    ("cloudformation", "get-template"),
    ("cloudformation", "execute-change-set"),
    ("cloudformation", "describe-stack-events"),
    ("cloudformation", "update-termination-protection"),
    ("cloudformation", "set-stack-policy"),
    ("cloudformation", "update-stack"),
    ("cloudformation", "list-stack-resources"),
    ("rds", "describe-db-instances"),
    ("rds", "describe-db-parameters"),
}
WRITE_ATTEMPTED = False


def note(s):
    print(s, flush=True)


def aws(service, operation, *args, region=REGION):
    if (service, operation) not in ALLOWED:
        raise RuntimeError("Operation refused")
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
    )
    if result.returncode:
        raise RuntimeError(service + " " + operation + ": " + result.stderr.strip())
    return json.loads(result.stdout) if result.stdout.strip() else {}


def stack_info():
    s = aws("cloudformation", "describe-stacks", "--stack-name", STACK)["Stacks"][0]
    if not s["StackId"].startswith(f"arn:aws:cloudformation:{REGION}:{ACCOUNT}:stack/{STACK}/"):
        raise RuntimeError("Stack identity mismatch")
    return s


def check_template(change=False):
    args = ["--stack-name", STACK, "--template-stage", "Original"]
    if change:
        args += ["--change-set-name", CHANGE]
    body = aws("cloudformation", "get-template", *args)["TemplateBody"]
    if isinstance(body, str):
        body = json.loads(body)
    if body != TEMPLATE:
        raise RuntimeError("Live template no longer matches the reviewed template")


def prices():
    base = {
        "location": "Asia Pacific (Singapore)",
        "databaseEngine": "PostgreSQL",
        "deploymentOption": "Single-AZ",
    }

    def get(extra, unit, storage=False):
        filters = [
            {"Type": "TERM_MATCH", "Field": k, "Value": v} for k, v in {**base, **extra}.items()
        ]
        response = aws(
            "pricing",
            "get-products",
            "--service-code",
            "AmazonRDS",
            "--filters",
            json.dumps(filters),
            region="us-east-1",
        )
        rates = []
        for raw in response.get("PriceList", []):
            item = json.loads(raw) if isinstance(raw, str) else raw
            attrs = item["product"]["attributes"]
            if storage and not (
                attrs.get("volumeType") == "General Purpose-GP3"
                or attrs.get("volumeApiName") == "gp3"
            ):
                continue
            for term in item.get("terms", {}).get("OnDemand", {}).values():
                for dim in term.get("priceDimensions", {}).values():
                    if (
                        dim.get("unit") == unit
                        and dim.get("beginRange") == "0"
                        and dim.get("endRange") == "Inf"
                    ):
                        rate = Decimal(dim["pricePerUnit"]["USD"])
                        if rate > 0:
                            rates.append(
                                {
                                    "sku": item["product"]["sku"],
                                    "usd": str(rate),
                                    "unit": unit,
                                    "description": dim["description"],
                                    "effective": term.get("effectiveDate"),
                                }
                            )
        if len(rates) != 1:
            raise RuntimeError(
                "Current " + unit + " price was not uniquely identified; no deployment will proceed"
            )
        return rates[0]

    compute = get({"instanceType": "db.t4g.micro", "productFamily": "Database Instance"}, "Hrs")
    storage = get({"productFamily": "Database Storage"}, "GB-Mo", storage=True)
    monthly = Decimal(compute["usd"]) * 730 + Decimal(storage["usd"]) * 20 + Decimal("0.40")
    capped = Decimal(compute["usd"]) * 730 + Decimal(storage["usd"]) * 30 + Decimal("0.40")
    quote = {
        "compute": compute,
        "gp3_storage": storage,
        "managed_secret_monthly_usd_assumption": "0.40",
        "base_monthly_usd_730_hours": str(monthly),
        "base_monthly_usd_at_30_gib": str(capped),
        "excludes": (
            "Taxes, exchange rates, CPU credit overages, excess backups/s"
            "napshots, secret API calls, transfer and other app resources"
            ". Not a total spend cap."
        ),
        "secret_price_source": "https://aws.amazon.com/secrets-manager/pricing/",
    }
    note(
        "Current Singapore compute: US$"
        + compute["usd"]
        + "/hour; gp3: US$"
        + storage["usd"]
        + "/GiB-month."
    )
    note(
        f"Foundation base estimate: US${monthly:.2f}/month at 730 hours and 20 GiB, "
        "including a US$0.40 managed-secret allowance."
    )
    note(f"At the 30 GiB storage ceiling: US${capped:.2f}/month, before the same exclusions.")
    note(quote["excludes"])
    return quote


def confirm():
    # Separate handles support macOS terminals, which are not seekable streams.
    with open("/dev/tty", "w") as terminal:
        terminal.write(
            "To provision this foundation and accept the displayed running costs, type "
            + ACCOUNT
            + ": "
        )
        terminal.flush()
    with open("/dev/tty") as terminal:
        value = terminal.readline().strip()
    if value != ACCOUNT:
        raise RuntimeError("Confirmation did not match; no provisioning request sent")


def save(report):
    folder = Path.home() / "Downloads"
    folder.mkdir(exist_ok=True)
    fd, name = tempfile.mkstemp(
        prefix="Fitfinity_AWS_Foundation_Execution_", suffix=".json", dir=folder
    )
    with os.fdopen(fd, "w") as f:
        json.dump(report, f, indent=2)
        f.write("\n")
    note("Receipt: " + name)
    return name


def main():
    global WRITE_ATTEMPTED
    note("Fitfinity AWS — recover the failed Free-plan test foundation (1-day backups)")
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
        raise RuntimeError("Remove AWS credential/config/endpoint environment overrides")
    os.environ.update(
        AWS_PAGER="",
        AWS_CLI_AUTO_PROMPT="off",
        AWS_IGNORE_CONFIGURED_ENDPOINT_URLS="true",
        AWS_MAX_ATTEMPTS="2",
    )
    who = aws("sts", "get-caller-identity")
    if (
        who.get("Account") != ACCOUNT
        or who.get("Arn") != f"arn:aws:iam::{ACCOUNT}:user/fitfinity-deployer"
    ):
        raise RuntimeError("Expected test IAM identity was not verified")
    s = stack_info()
    quote = None
    tags = {t["Key"]: t["Value"] for t in s.get("Tags", [])}
    if (
        tags.get("TemplateSHA256") != HASH
        or tags.get("ManagedBy") != "fitfinity-foundation-planner"
        or tags.get("Application") != "Fitfinity"
        or tags.get("Environment") != "test"
    ):
        raise RuntimeError("Existing stack ownership mismatch")
    if s["StackStatus"] == "CREATE_FAILED":
        original = json.loads(json.dumps(TEMPLATE))
        original["Resources"]["Database"]["Properties"]["BackupRetentionPeriod"] = 14
        live = aws(
            "cloudformation", "get-template", "--stack-name", STACK, "--template-stage", "Original"
        )["TemplateBody"]
        if isinstance(live, str):
            live = json.loads(live)
        if live != original:
            raise RuntimeError(
                "Failed stack template differs from the original reviewed foundation"
            )
        resources = aws("cloudformation", "list-stack-resources", "--stack-name", STACK)[
            "StackResourceSummaries"
        ]
        if len(resources) != 20 or {x["LogicalResourceId"] for x in resources} != set(
            TEMPLATE["Resources"]
        ):
            raise RuntimeError("Unexpected preserved resource inventory")
        for resource in resources:
            name = resource["LogicalResourceId"]
            if resource["ResourceType"] != TEMPLATE["Resources"][name]["Type"]:
                raise RuntimeError("Unexpected resource type")
            if name == "Database":
                reason = resource.get("ResourceStatusReason", "").lower()
                if (
                    resource["ResourceStatus"] != "CREATE_FAILED"
                    or "backup retention period" not in reason
                    or "free tier" not in reason
                ):
                    raise RuntimeError(
                        "Database failure does not match the reviewed Free-plan retention rejection"
                    )
            elif resource["ResourceStatus"] != "CREATE_COMPLETE":
                raise RuntimeError("Another resource needs review: " + name)
        databases = aws(
            "rds",
            "describe-db-instances",
            "--query",
            ("DBInstances[?DBInstanceIdentifier=='fitfinity-test-db'].DBInstanceIdentifier"),
        )
        if databases:
            raise RuntimeError(
                "A database already exists; refusing to reduce any existing backup history"
            )
        plan = aws("freetier", "get-account-plan-state", region="us-east-1")
        if plan.get("accountPlanStatus") != "ACTIVE" or plan.get("accountPlanType") != "FREE":
            raise RuntimeError("This specific recovery expects the ACTIVE FREE test account")
        quote = prices()
        note(
            "Only template change: test database BackupRetentionPeriod 14"
            " -> 1 day. Automated backups stay enabled."
        )
        note(
            "Production target remains 14 days. No account upgrade, netwo"
            "rk rebuild or database deletion is requested."
        )
        note(
            "The Free-plan error does not state its maximum; this retry m"
            "ust still be accepted by AWS."
        )
        confirm()
        if stack_info()["StackStatus"] != "CREATE_FAILED":
            raise RuntimeError("Stack state changed during review")
        with tempfile.TemporaryDirectory(prefix="fitfinity-foundation-recovery-") as td:
            source = Path(td) / "template.json"
            source.write_text(json.dumps(TEMPLATE))
            WRITE_ATTEMPTED = True
            aws(
                "cloudformation",
                "update-stack",
                "--stack-name",
                s["StackId"],
                "--template-body",
                "file://" + str(source),
                "--disable-rollback",
                "--client-request-token",
                "fitfinity-retention-one-day-" + RECOVERY_HASH[:20],
            )
    elif s["StackStatus"] in {"UPDATE_IN_PROGRESS", "UPDATE_COMPLETE", "CREATE_COMPLETE"}:
        check_template()
        note("Resuming verification of the exact recovered foundation; no new update request.")
    else:
        raise RuntimeError("Stack requires review: " + s["StackStatus"])
    deadline = time.monotonic() + 2700
    while True:
        s = stack_info()
        status = s["StackStatus"]
        note("CloudFormation: " + status)
        if status in {"CREATE_COMPLETE", "UPDATE_COMPLETE"}:
            break
        if status not in {
            "CREATE_IN_PROGRESS",
            "UPDATE_IN_PROGRESS",
            "UPDATE_COMPLETE_CLEANUP_IN_PROGRESS",
        }:
            events = aws(
                "cloudformation",
                "describe-stack-events",
                "--stack-name",
                STACK,
                "--query",
                (
                    "StackEvents[?contains(ResourceStatus, 'FAILED')].{Resource:L"
                    "ogicalResourceId,Status:ResourceStatus,Reason:ResourceStatus"
                    "Reason}"
                ),
            )
            save(
                {"stack": STACK, "status": status, "failures": events, "foundation_verified": False}
            )
            raise RuntimeError(
                "Foundation creation needs review; preserved resources may incur costs"
            )
        if time.monotonic() >= deadline:
            raise RuntimeError(
                "Still creating. Rerun this script to resume verification; AW"
                "S continues in the background"
            )
        time.sleep(15)
    check_template()
    outputs = {v["OutputKey"]: v["OutputValue"] for v in s.get("Outputs", [])}
    dbs = aws("rds", "describe-db-instances", "--db-instance-identifier", "fitfinity-test-db")[
        "DBInstances"
    ]
    if len(dbs) != 1:
        raise RuntimeError("Expected one database")
    db = dbs[0]
    expected = {
        "Engine": "postgres",
        "DBInstanceClass": "db.t4g.micro",
        "PubliclyAccessible": False,
        "StorageEncrypted": True,
        "DeletionProtection": True,
        "MultiAZ": False,
        "BackupRetentionPeriod": 1,
        "StorageType": "gp3",
        "MaxAllocatedStorage": 30,
    }
    if (
        any(db.get(k) != v for k, v in expected.items())
        or db.get("DBInstanceStatus") != "available"
        or db.get("EngineVersion") != "17.11"
    ):
        raise RuntimeError("Created database settings differ from the reviewed configuration")
    if db.get("AllocatedStorage") != 20:
        raise RuntimeError("Unexpected initial database storage")
    if db["DBSubnetGroup"]["VpcId"] != outputs["Vpc"]:
        raise RuntimeError("Database VPC mismatch")
    if {x["VpcSecurityGroupId"] for x in db.get("VpcSecurityGroups", [])} != {
        outputs["DatabaseSecurityGroup"]
    }:
        raise RuntimeError("Database security-group mismatch")
    secret = db.get("MasterUserSecret", {})
    if (
        secret.get("SecretStatus") != "active"
        or secret.get("SecretArn") != outputs["AdminSecretArn"]
    ):
        raise RuntimeError("Managed administrator secret is not active/matching")
    group = db["DBParameterGroups"][0]
    params = aws(
        "rds",
        "describe-db-parameters",
        "--db-parameter-group-name",
        group["DBParameterGroupName"],
        "--query",
        ("Parameters[?ParameterName=='rds.force_ssl'].{Name:ParameterName,Value:ParameterValue}"),
    )
    if (
        params != [{"Name": "rds.force_ssl", "Value": "1"}]
        or group.get("ParameterApplyStatus") != "in-sync"
    ):
        raise RuntimeError("Database TLS parameter is not confirmed active")
    WRITE_ATTEMPTED = True
    aws(
        "cloudformation",
        "update-termination-protection",
        "--stack-name",
        STACK,
        "--enable-termination-protection",
    )
    policy = {
        "Statement": [
            {"Effect": "Allow", "Principal": "*", "Action": "Update:*", "Resource": "*"},
            {
                "Effect": "Deny",
                "Principal": "*",
                "Action": ["Update:Replace", "Update:Delete"],
                "Resource": "LogicalResourceId/Database",
            },
        ]
    }
    aws(
        "cloudformation",
        "set-stack-policy",
        "--stack-name",
        STACK,
        "--stack-policy-body",
        json.dumps(policy),
    )
    report = {
        "created_at_utc": datetime.datetime.now(datetime.UTC).isoformat(),
        "account": ACCOUNT,
        "region": REGION,
        "stack": STACK,
        "stack_id": s["StackId"],
        "original_change_set_id": CHANGE,
        "template_sha256": RECOVERY_HASH,
        "test_backup_retention_days": 1,
        "production_backup_retention_target_days": 14,
        "foundation_verified": True,
        "app_deployed": False,
        "outputs": outputs,
        "pricing_at_execution": quote,
        "database_checks": expected,
        "tls_forced": True,
        "termination_protection_enabled": True,
        "database_replace_delete_denied_by_stack_policy": True,
        "remaining": [
            "Application/Cognito/secrets integration",
            "Outbound networking",
            "Restricted migration/bootstrap",
            "Frontend/API deployment",
            "Physical device checks",
        ],
    }
    save(report)
    note(
        "FOUNDATION VERIFIED — private database and network provisioned; application NOT deployed."
    )
    note("Keep this receipt. No password or secret value was retrieved or printed.")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
        note("STOPPED: " + str(exc))
        note(
            ("Resources may be running or still provisioning. Nothing is automatically deleted.")
            if WRITE_ATTEMPTED
            else (
                "This run has not attempted a cloud write; any previously sta"
                "rted deployment may still be running."
            )
        )
        sys.exit(1)
