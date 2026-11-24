"""Read-only TEST rollout inventory; retain selected metadata, never raw provider replies."""

import hashlib
import json
import os
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from deployment_profile import DEVELOPER, identities, load

ROOT = Path(__file__).resolve().parent
READS = {
    ("sts", "get-caller-identity"),
    ("lambda", "get-function"),
    ("lambda", "get-function-concurrency"),
    ("lambda", "get-alias"),
    ("cloudformation", "describe-stacks"),
    ("cloudformation", "get-template"),
    ("rds", "describe-db-instances"),
}
FLAGS = (
    "FITFINITY_AUTH_ENABLED",
    "FITFINITY_STAFF_INVITATIONS_ENABLED",
    "FITFINITY_STAFF_EMAIL_CORRECTIONS_ENABLED",
    "FITFINITY_MEDIA_ENABLED",
)


def require(value, message):
    if not value:
        raise RuntimeError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def aws(service, operation, *args, profile=DEVELOPER):
    region = identities(profile)["region"]
    require((service, operation) in READS, "Read operation is not allowed")
    require(not any(str(arg).startswith("--endpoint") for arg in args), "Endpoint override refused")
    result = subprocess.run(
        ["aws", service, operation, *args, "--region", region, "--output", "json"],
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "AWS_PAGER": "", "AWS_EC2_METADATA_DISABLED": "true"},
    )
    require(result.returncode == 0, f"Read failed: {service}/{operation}")
    return json.loads(result.stdout)


def configuration_summary(config):
    variables = config.get("Environment", {}).get("Variables", {})
    return {
        "environment_keys": sorted(variables),
        "feature_flags": {
            key: variables.get(key, "").lower()
            if variables.get(key, "").lower() in {"true", "false"}
            else "unset" if key not in variables else "invalid"
            for key in FLAGS
        },
    }


def observe(call=None, *, profile=DEVELOPER):
    target = identities(profile)
    account, region, function_name = target["account"], target["region"], target["runtime_function"]
    if call is None:

        def call(service, operation, *args):
            return aws(service, operation, *args, profile=profile)

    identity = call("sts", "get-caller-identity")
    require(
        identity.get("Account") == account
        and re.fullmatch(
            rf"arn:aws:sts::{account}:assumed-role/{re.escape(target['hosting_role'])}/[\w+=,.@-]+",
            identity.get("Arn", ""),
        ),
        "Wrong AWS account or observation role",
    )
    name = target["hosting_stack"]
    stacks = call("cloudformation", "describe-stacks", "--stack-name", name)["Stacks"]
    require(len(stacks) == 1 and stacks[0]["StackName"] == name, "Hosting stack differs")
    stack = stacks[0]
    require(stack["StackStatus"] in {"CREATE_COMPLETE", "UPDATE_COMPLETE"}, "Stack is not stable")
    template = call("cloudformation", "get-template", "--stack-name", stack["StackId"])[
        "TemplateBody"
    ]
    if isinstance(template, str):
        template = json.loads(template)
    function = call("lambda", "get-function", "--function-name", function_name)
    config = function["Configuration"]
    require(
        config["FunctionArn"] == f"arn:aws:lambda:{region}:{account}:function:" + function_name,
        "Runtime identity differs",
    )
    concurrency = call("lambda", "get-function-concurrency", "--function-name", function_name)
    alias = call(
        "lambda", "get-alias", "--function-name", function_name, "--name", target["runtime_alias"]
    )
    require(re.fullmatch(r"[1-9][0-9]*", alias["FunctionVersion"]), "Alias version differs")
    serving = call(
        "lambda",
        "get-function",
        "--function-name",
        function_name,
        "--qualifier",
        alias["FunctionVersion"],
    )
    database_id = target["database"]
    databases = call("rds", "describe-db-instances", "--db-instance-identifier", database_id)[
        "DBInstances"
    ]
    require(
        len(databases) == 1 and databases[0]["DBInstanceIdentifier"] == database_id,
        "Database identity differs",
    )
    db = databases[0]
    # Never retain environment values, stack parameters/template or Code.Location URLs.
    return {
        "observed_at": datetime.now(UTC).isoformat(),
        "profile_sha256": target["profile_sha256"],
        "account": account,
        "region": region,
        "deployment_decision": "HOLD",
        "stack": {
            "id": stack["StackId"],
            "status": stack["StackStatus"],
            "template_sha256": digest(template),
        },
        "runtime": {
            "arn": config["FunctionArn"],
            "revision_id": config["RevisionId"],
            "reserved_concurrency": concurrency.get("ReservedConcurrentExecutions"),
            "timeout_seconds": config.get("Timeout"),
            "state": config.get("State"),
            "update_status": config.get("LastUpdateStatus"),
            "latest_image": function["Code"].get("ResolvedImageUri"),
            "serving_image": serving["Code"].get("ResolvedImageUri"),
            "serving_configuration_sha256": digest(serving["Configuration"]),
            "configuration_sha256": digest(config),
            "latest_configuration": configuration_summary(config),
            "serving_configuration": configuration_summary(serving["Configuration"]),
            "alias_version": alias["FunctionVersion"],
            "alias_revision_id": alias["RevisionId"],
            "alias_has_weighted_routing": bool(
                alias.get("RoutingConfig", {}).get("AdditionalVersionWeights")
            ),
        },
        "database": {
            key: db.get(key)
            for key in (
                "DBInstanceIdentifier",
                "DBInstanceArn",
                "DbiResourceId",
                "DBInstanceStatus",
                "Engine",
                "EngineVersion",
                "BackupRetentionPeriod",
                "LatestRestorableTime",
                "StorageEncrypted",
                "PubliclyAccessible",
            )
        },
        "unverified": [
            "Database schema/data and current runtime grants (no SQL was executed)",
            "Snapshot/restore drill and actual recovery objectives",
            "Current image scan, feature IAM/media configuration and candidate rollout",
            "Frontend manifest binding and CloudFront propagation",
        ],
    }


def main():
    import argparse

    from hosting_frontend import source_check

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    profile = load(args.profile)
    require(os.getenv("GITHUB_REPOSITORY") == profile["github_repository"], "Repository differs")
    require(os.getenv("GITHUB_REF") == "refs/heads/main", "Observation requires reviewed main")
    require(os.getenv("GITHUB_EVENT_NAME") == "workflow_dispatch", "Manual dispatch required")
    require(not any(key.startswith("AWS_ENDPOINT_URL") for key in os.environ), "Endpoint override")
    source = source_check(ROOT.parents[1], os.getenv("GITHUB_SHA"))
    result = observe(profile=profile)
    result["source_sha"] = source["revision"]
    args.output.write_text(json.dumps(result, indent=2, default=str) + "\n")
    print("Read-only release observation retained; deployment HOLD")


if __name__ == "__main__":
    main()
