"""Collect remaining read-only developer probe prerequisites without secret values."""

import json
import os
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

ACCOUNT = "418638389566"
REGION = "ap-southeast-1"
INSTANCE = "i-0fc0373d803ed17ec"
DATABASE_GROUP = "sg-02e32d9cff9e4e8b6"


def read(service, operation, *args):
    """Run a bounded metadata read and suppress raw error details."""
    allowed = {
        ("sts", "get-caller-identity"),
        ("ec2", "describe-instances"),
        ("ec2", "describe-instance-status"),
        ("ec2", "describe-security-groups"),
        ("lambda", "get-function-configuration"),
        ("iam", "get-open-id-connect-provider"),
    }
    if (service, operation) not in allowed:
        raise RuntimeError("Read operation refused")
    result = subprocess.run(
        [
            "aws",
            service,
            operation,
            *args,
            "--region",
            REGION,
            "--output",
            "json",
            "--no-cli-pager",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        env={
            **os.environ,
            "AWS_PAGER": "",
            "AWS_CLI_AUTO_PROMPT": "off",
            "AWS_IGNORE_CONFIGURED_ENDPOINT_URLS": "true",
            "AWS_MAX_ATTEMPTS": "1",
        },
    )
    if result.returncode:
        match = re.search(r"An error occurred \(([^)]+)\)", result.stderr)
        return {"read_error": match.group(1) if match else "AWS_READ_FAILED"}
    return json.loads(result.stdout)


def selected(row, fields):
    """Project only the documented metadata fields."""
    return {key: row.get(key) for key in fields}


def collect(call=read):
    """Collect the egress health, DB inbound rule, Lambda reason and OIDC identity."""
    if call("sts", "get-caller-identity").get("Account") != ACCOUNT:
        raise RuntimeError("Wrong AWS account; no further reads performed")
    result = {"account": ACCOUNT, "region": REGION, "observed_at": datetime.now(UTC).isoformat()}
    instances = call("ec2", "describe-instances", "--instance-ids", INSTANCE)
    result["egress_instance"] = (
        instances
        if "read_error" in instances
        else [
            selected(
                row,
                [
                    "InstanceId",
                    "State",
                    "VpcId",
                    "SubnetId",
                    "PublicIpAddress",
                    "SourceDestCheck",
                    "SecurityGroups",
                ],
            )
            for reservation in instances.get("Reservations", [])
            for row in reservation.get("Instances", [])
        ]
    )
    result["egress_status_checks"] = call(
        "ec2", "describe-instance-status", "--instance-ids", INSTANCE, "--include-all-instances"
    )
    groups = call("ec2", "describe-security-groups", "--group-ids", DATABASE_GROUP)
    result["database_security_group"] = (
        groups
        if "read_error" in groups
        else [
            selected(row, ["GroupId", "OwnerId", "VpcId", "IpPermissions"])
            for row in groups.get("SecurityGroups", [])
        ]
    )
    runtime = call(
        "lambda", "get-function-configuration", "--function-name", "fitfinity-test-staff-api"
    )
    result["runtime_state"] = (
        runtime
        if "read_error" in runtime
        else selected(
            runtime,
            [
                "FunctionArn",
                "State",
                "StateReason",
                "StateReasonCode",
                "LastUpdateStatus",
                "LastUpdateStatusReasonCode",
            ],
        )
    )
    provider = call(
        "iam",
        "get-open-id-connect-provider",
        "--open-id-connect-provider-arn",
        f"arn:aws:iam::{ACCOUNT}:oidc-provider/token.actions.githubusercontent.com",
    )
    result["github_oidc"] = (
        provider if "read_error" in provider else selected(provider, ["Url", "ClientIDList"])
    )
    return result


if __name__ == "__main__":
    report = collect()
    path = Path("fitfinity-network-followup.json")
    with path.open("x") as output:
        json.dump(report, output, indent=2)
    print(json.dumps(report, indent=2))
    print(f"Saved: {path.resolve()}. Read-only; no resources changed.")
