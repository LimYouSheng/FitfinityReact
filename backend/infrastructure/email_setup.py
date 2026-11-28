"""Read actual CloudShell resource owners and prepare disabled email setup artifacts."""

import argparse
import json
import os
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import boto3
import email_runtime
from botocore.exceptions import ClientError
from deployment_profile import fingerprint, identities, load
from email_deployment import hosting_values
from email_scheduler import template as scheduler
from operator_checks import require
from release_features import prepare as features
from release_observation import digest


def coordinator_read(candidate, target):
    """Add only the read needed to bind the external boundary in coordinator reviews."""
    candidate = deepcopy(candidate)
    root = f"arn:aws:cloudformation:{target['region']}:{target['account']}:stack/"
    old = root + target["hosting_stack"] + "/*"
    new = root + target["resource_prefix"] + "-github-hosting/*"
    resources = candidate["Resources"]
    policies = resources["CoordinatorRole"]["Properties"]["Policies"]
    require(len(policies) == 1, "Unexpected coordinator policy owners")
    for document in (
        policies[0]["PolicyDocument"],
        resources["CoordinatorBoundary"]["Properties"]["PolicyDocument"],
    ):
        rows = [s for s in document["Statement"] if s.get("Action") == "cloudformation:GetTemplate"]
        require(len(rows) == 1, "Expected one coordinator template-read statement")
        require(rows[0]["Resource"] in (old, [old], [old, new]), "Coordinator read scope differs")
        rows[0]["Resource"] = [old, new]
    return candidate


def documents(profile, email, hosting, boundary, coordinator, alias_arn):
    """Preserve current identities and emit only email changes with the worker disabled."""
    target = identities(profile)
    email_runtime.checked(target, email)
    values = hosting_values(hosting, profile, email)
    proposed = features(
        hosting,
        values,
        profile=profile,
        boundary_template=boundary,
        boundary_template_sha256=digest(boundary) if boundary is not None else None,
    )
    worker = scheduler(
        target["account"],
        target["region"],
        target["resource_prefix"],
        alias_arn,
        email["dispatch_secret"],
        target["secret_prefix"],
    )
    return {
        "hosting-preview": proposed["candidate_template"],
        "boundary": proposed["boundary_candidate_template"],
        "boundary_logical_id": proposed["boundary_resource"],
        "coordinator": coordinator_read(coordinator, target) if boundary is not None else None,
        "worker": worker,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--email", required=True, help="JSON file containing four public bindings")
    parser.add_argument(
        "--release-config", required=True, help="Current release configuration JSON"
    )
    parser.add_argument("--output", required=True, help="New private review directory")
    args = parser.parse_args()
    require(
        not any(k.startswith("AWS_ENDPOINT_URL") for k in os.environ), "Endpoint override refused"
    )
    profile = load(args.profile)
    target = identities(profile)
    email = email_runtime.checked(target, json.loads(Path(args.email).read_text()))
    config = json.loads(Path(args.release_config).read_text())
    require(
        config.get("profile_sha256") == fingerprint(profile), "Release configuration target differs"
    )
    root = Path(args.output)
    require(not root.exists(), "Use a new review directory; preserve previous evidence")
    session = boto3.Session(region_name=target["region"])
    require(
        session.client("sts").get_caller_identity()["Account"] == target["account"],
        "Wrong AWS account",
    )
    ses = session.client("sesv2")
    identity = ses.get_email_identity(EmailIdentity=email["identity_arn"].split(":identity/", 1)[1])
    require(identity.get("VerifiedForSendingStatus") is True, "SES sender identity is not verified")
    secret = session.client("secretsmanager").describe_secret(SecretId=email["dispatch_secret"])
    require(
        secret["ARN"] == email["dispatch_secret"] and not secret.get("DeletedDate"),
        "Secret identity differs",
    )
    require(
        not secret.get("KmsKeyId") or secret["KmsKeyId"] == "alias/aws/secretsmanager",
        "Custom KMS requires reviewed access",
    )
    require(
        any("AWSCURRENT" in stages for stages in secret.get("VersionIdsToStages", {}).values()),
        "Secret has no current version",
    )
    cf = session.client("cloudformation")

    def read(name):
        stack = cf.describe_stacks(StackName=name)["Stacks"][0]
        require(
            stack["StackStatus"]
            in {"CREATE_COMPLETE", "UPDATE_COMPLETE", "UPDATE_ROLLBACK_COMPLETE"},
            "Stack is not stable",
        )
        value = cf.get_template(StackName=stack["StackId"], TemplateStage="Original")[
            "TemplateBody"
        ]
        value = json.loads(value) if isinstance(value, str) else value
        require(isinstance(value, dict), "Expected JSON template")
        return stack, value

    hosting_stack, hosting = read(target["hosting_stack"])
    role = session.client("iam").get_role(RoleName=target["resource_prefix"] + "-hosting-api")[
        "Role"
    ]
    expected_boundary = (
        f"arn:aws:iam::{target['account']}:policy/{target['resource_prefix']}-hosting-api-boundary"
    )
    require(
        role.get("PermissionsBoundary", {}).get("PermissionsBoundaryArn") == expected_boundary,
        "Live runtime boundary differs",
    )
    for logical, physical in (
        ("ApiFunction", target["runtime_function"]),
        ("ApiRole", role["RoleName"]),
    ):
        actual = cf.describe_stack_resource(
            StackName=hosting_stack["StackId"], LogicalResourceId=logical
        )["StackResourceDetail"]
        require(actual["PhysicalResourceId"] == physical, "Hosting resource owner differs")
    alias = cf.describe_stack_resource(
        StackName=hosting_stack["StackId"], LogicalResourceId="ApiAlias"
    )["StackResourceDetail"]["PhysicalResourceId"]
    live_alias = session.client("lambda").get_alias(
        FunctionName=target["runtime_function"], Name=alias.rsplit(":", 1)[-1]
    )
    require(live_alias["AliasArn"] == alias, "Live application alias differs")
    owner_stack = boundary = journal_stack = journal = None
    if isinstance(hosting["Resources"]["ApiRole"]["Properties"]["PermissionsBoundary"], str):
        owner_stack, boundary = read(target["resource_prefix"] + "-github-hosting")
        journal_stack, journal = read(target["resource_prefix"] + "-deployment-journal")
    result = documents(profile, email, hosting, boundary, journal, alias)
    config["email"] = email
    config.pop("email_boundary", None)
    if owner_stack:
        logical = result["boundary_logical_id"]
        actual = cf.describe_stack_resource(
            StackName=owner_stack["StackId"], LogicalResourceId=logical
        )["StackResourceDetail"]
        require(
            actual["PhysicalResourceId"] == expected_boundary, "External boundary owner differs"
        )
        entities = session.client("iam").list_entities_for_policy(
            PolicyArn=expected_boundary, PolicyUsageFilter="PermissionsBoundary"
        )
        require(
            not entities.get("IsTruncated")
            and not entities.get("PolicyUsers")
            and not entities.get("PolicyGroups")
            and [r["RoleName"] for r in entities.get("PolicyRoles", [])] == [role["RoleName"]],
            "Boundary has unexpected consumers",
        )
        config["email_boundary"] = {
            "stack_arn": owner_stack["StackId"],
            "logical_id": logical,
            "template_sha256": digest(result["boundary"]),
        }
    worker_exists = False
    try:
        _, installed_worker = read(target["resource_prefix"] + "-email-dispatch")
    except ClientError as exc:
        require(
            exc.response["Error"]["Code"] == "ValidationError"
            and "does not exist" in exc.response["Error"]["Message"],
            "Cannot establish worker stack existence",
        )
    else:
        require(
            installed_worker == result["worker"],
            "Existing worker differs; inspect before changing it",
        )
        worker_exists = True
    root.mkdir(mode=0o700)

    def save(name, value):
        path = root / (name + ".json")
        path.write_text(json.dumps(value, indent=2) + "\n")
        path.chmod(0o600)

    for name in ("hosting-preview", "boundary", "coordinator", "worker"):
        if result[name] is not None:
            save(name, result[name])
    for name, stack, original in (
        ("boundary", owner_stack, boundary),
        ("coordinator", journal_stack, journal),
    ):
        if stack is not None and result[name] != original:
            body = json.dumps(result[name])
            require(len(body.encode()) <= 51200, "Template needs reviewed S3 upload")
            save(
                name + "-change-set",
                {
                    "StackName": stack["StackId"],
                    "ChangeSetName": "email-" + uuid4().hex,
                    "ChangeSetType": "UPDATE",
                    "TemplateBody": body,
                    "Capabilities": ["CAPABILITY_NAMED_IAM"],
                    "Parameters": [
                        {"ParameterKey": p["ParameterKey"], "UsePreviousValue": True}
                        for p in stack.get("Parameters", [])
                    ],
                },
            )
    if not worker_exists:
        save(
            "worker-change-set",
            {
                "StackName": target["resource_prefix"] + "-email-dispatch",
                "ChangeSetName": "email-worker-" + uuid4().hex,
                "ChangeSetType": "CREATE",
                "TemplateBody": json.dumps(result["worker"]),
                "Capabilities": ["CAPABILITY_NAMED_IAM"],
            },
        )
    save("release-config", config)
    save(
        "review",
        {
            "profile_sha256": fingerprint(profile),
            "hosting_stack": hosting_stack["StackId"],
            "hosting_original_sha256": digest(hosting),
            "boundary_stack": owner_stack["StackId"] if owner_stack else None,
            "boundary_original_sha256": digest(boundary) if boundary else None,
            "coordinator_stack": journal_stack["StackId"] if journal_stack else None,
            "coordinator_original_sha256": digest(journal) if journal else None,
            "worker_stack": target["resource_prefix"] + "-email-dispatch",
            "candidate_sha256": {
                name: digest(result[name])
                for name in ("boundary", "coordinator", "worker")
                if result[name] is not None
            },
            "production_access": ses.get_account().get("ProductionAccessEnabled", False),
            "cognito_changed": False,
            "schedule_enabled": False,
        },
    )
    print(f"Review directory: {root}")
    print("PREPARED ONLY. Read-only AWS calls; no secret values read and no change sets executed.")
    print(
        "Review boundary/coordinator/worker templates. "
        "Hosting preview is for reviewed release only."
    )


if __name__ == "__main__":
    main()
