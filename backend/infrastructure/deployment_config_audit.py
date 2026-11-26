"""Collect non-secret deployment role/configuration evidence without changing AWS."""

import argparse
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

READS = {
    ("sts", "get-caller-identity"),
    ("iam", "get-role"),
    ("iam", "list-role-policies"),
    ("iam", "get-role-policy"),
    ("iam", "list-attached-role-policies"),
    ("iam", "get-policy"),
    ("iam", "get-policy-version"),
    ("cloudformation", "describe-stacks"),
    ("cloudformation", "list-stack-resources"),
    ("cloudformation", "describe-stack-resources"),
    ("lambda", "get-function-configuration"),
    ("lambda", "get-function-concurrency"),
}


def collect(profile, read):
    """Read exact target roles and redact runtime values before retaining observations."""
    account, region, prefix = (profile[key] for key in ("account", "region", "resource_prefix"))
    if read("sts", "get-caller-identity", {}).get("Account") != account:
        raise RuntimeError("Wrong AWS account")
    report = {
        "account": account,
        "region": region,
        "resource_prefix": prefix,
        "observed_at": datetime.now(UTC).isoformat(),
        "roles": {},
        "aws_changes": False,
    }
    for suffix in (
        "github-image",
        "github-schema-probe",
        "github-schema-upgrade",
        "github-maintenance",
        "github-hosting",
        "hosting-cloudformation",
        "hosting-api",
    ):
        name = prefix + "-" + suffix
        value = read("iam", "get-role", {"RoleName": name})
        role = value.get("Role")
        if not role:
            report["roles"][name] = value
            continue
        item = {
            key: role.get(key) for key in ("Arn", "AssumeRolePolicyDocument", "PermissionsBoundary")
        }
        policies = read("iam", "list-role-policies", {"RoleName": name})
        item["inline_inventory"] = policies
        item["inline_policies"] = {
            policy: read("iam", "get-role-policy", {"RoleName": name, "PolicyName": policy}).get(
                "PolicyDocument"
            )
            for policy in policies.get("PolicyNames", [])
        }
        attached = read("iam", "list-attached-role-policies", {"RoleName": name})
        item["attached_inventory"] = attached
        arns = [row["PolicyArn"] for row in attached.get("AttachedPolicies", [])]
        boundary = (role.get("PermissionsBoundary") or {}).get("PermissionsBoundaryArn")
        if boundary:
            arns.append(boundary)
        item["managed_policies"] = {}
        for arn in sorted(set(arns)):
            policy = read("iam", "get-policy", {"PolicyArn": arn})
            version = policy.get("Policy", {}).get("DefaultVersionId")
            item["managed_policies"][arn] = (
                read("iam", "get-policy-version", {"PolicyArn": arn, "VersionId": version})
                if version
                else policy
            )
        item["stack_owner"] = read(
            "cloudformation", "describe-stack-resources", {"PhysicalResourceId": name}
        )
        report["roles"][name] = item
    stack = prefix + "-login"
    metadata = read("cloudformation", "describe-stacks", {"StackName": stack})
    report["hosting_stack"] = [
        {
            key: row.get(key)
            for key in ("StackId", "StackName", "StackStatus", "RoleARN", "ParentId", "RootId")
        }
        for row in metadata.get("Stacks", [])
    ] or metadata
    report["hosting_resources"] = read(
        "cloudformation", "list-stack-resources", {"StackName": stack}
    )
    runtime = read("lambda", "get-function-configuration", {"FunctionName": prefix + "-staff-api"})
    report["runtime"] = {
        key: runtime.get(key)
        for key in ("FunctionArn", "Role", "RevisionId", "State", "LastUpdateStatus", "VpcConfig")
    }
    values = runtime.get("Environment", {}).get("Variables", {})
    report["runtime"]["environment_names"] = sorted(values)
    report["runtime"]["feature_flags"] = {
        key: values.get(key, "unset")
        if values.get(key, "unset") in ("true", "false", "unset")
        else "invalid"
        for key in (
            "FITFINITY_AUTH_ENABLED",
            "FITFINITY_MEDIA_ENABLED",
            "FITFINITY_STAFF_INVITATIONS_ENABLED",
            "FITFINITY_STAFF_EMAIL_CORRECTIONS_ENABLED",
        )
    }
    report["concurrency"] = read(
        "lambda", "get-function-concurrency", {"FunctionName": prefix + "-staff-api"}
    )
    report["unverified"] = [
        "GitHub environment variables/protections",
        "Secret values and validity",
        "Effective SCP/session policy restrictions",
        "Live provider and physical-device acceptance",
    ]
    return report


def main():
    """Write a private metadata report; never log provider error bodies or secret values."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    profile = json.loads(args.profile.read_text())

    def read(service, operation, values):
        if (service, operation) not in READS:
            raise RuntimeError("Only enumerated read operations are allowed")
        result = subprocess.run(
            [
                "aws",
                service,
                operation,
                "--region",
                profile["region"],
                "--cli-input-json",
                json.dumps(values),
                "--output",
                "json",
                "--no-cli-pager",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode:
            match = re.search(r"An error occurred \(([A-Za-z0-9]+)\)", result.stderr)
            return {"unverified": True, "code": match[1] if match else "ReadFailed"}
        return json.loads(result.stdout)

    report = collect(profile, read)
    with args.output.open("x") as stream:
        args.output.chmod(0o600)
        json.dump(report, stream, indent=2)
    print("Read-only configuration report saved:", args.output)


if __name__ == "__main__":
    main()
