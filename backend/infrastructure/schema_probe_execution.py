"""Execute one reviewed private probe operation; never migrate or deploy the staff API."""

import hashlib
import json
import re
import time

from deployment_profile import DEVELOPER, identities
from operator_checks import require
from release_image_validation import validate_image as validate_published_image
from schema_probe_plan import prepare_review


def compact(value):
    """Serialize protocol payloads without optional whitespace."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def validate_review(
    review, expected_hash, source_sha, sql, *, now, cleanup=False, profile=DEVELOPER
):
    """Recompute the approved template before any AWS operation."""
    binding = review["bindings"]
    checked = prepare_review(
        binding,
        source_sha,
        sql,
        now=binding["expires_at"] - 1 if cleanup else now,
        profile=profile,
    )
    require(review == checked, "Probe review changed; regenerate and review")
    require(
        re.fullmatch(r"[0-9a-f]{64}", expected_hash or "")
        and checked["template_sha256"] == expected_hash,
        "Reviewed template digest differs",
    )
    return binding


def validate_image(receipt, binding, call, now, *, profile=DEVELOPER):
    """Require the probe SQL in the exact published image and a fresh complete scan."""
    validate_published_image(
        receipt,
        binding,
        call,
        now,
        profile=profile,
        required_files={"backend/infrastructure/read-schema.sql": binding["sql_sha256"]},
    )


def preflight(binding, call, *, profile=DEVELOPER, reserve_capacity=True):
    """Verify current private resource metadata without retrieving credentials."""
    target = identities(profile)
    account, region = target["account"], target["region"]
    if reserve_capacity:
        limits = call("lambda", "get-account-settings", {})
        require(
            limits.get("AccountLimit", {}).get("UnreservedConcurrentExecutions", 0) >= 101,
            "Account concurrency cannot reserve one probe execution while retaining AWS headroom",
        )
    databases = call("rds", "describe-db-instances", {"DBInstanceIdentifier": target["database"]})[
        "DBInstances"
    ]
    require(len(databases) == 1, "Database identity differs")
    db = databases[0]
    require(
        db.get("DBInstanceArn") == f"arn:aws:rds:{region}:{account}:db:{target['database']}"
        and db.get("DBInstanceStatus") == "available"
        and db.get("Endpoint", {}).get("Address") == binding["db_host"]
        and db.get("DBName") == binding["db_name"]
        and db.get("StorageEncrypted") is True
        and db.get("PubliclyAccessible") is False,
        "Database metadata differs",
    )
    vpc = db["DBSubnetGroup"]["VpcId"]
    subnets = call("ec2", "describe-subnets", {"SubnetIds": binding["subnet_ids"]})["Subnets"]
    require(
        len(subnets) == 2
        and {row["SubnetId"] for row in subnets} == set(binding["subnet_ids"])
        and all(
            row.get("VpcId") == vpc
            and row.get("OwnerId") == account
            and row.get("State") == "available"
            and row.get("MapPublicIpOnLaunch") is False
            for row in subnets
        ),
        "Private subnet bindings differ",
    )
    groups = call("ec2", "describe-security-groups", {"GroupIds": [binding["security_group_id"]]})[
        "SecurityGroups"
    ]
    require(
        len(groups) == 1 and groups[0].get("VpcId") == vpc and groups[0].get("OwnerId") == account,
        "Probe security group differs",
    )
    secret = call(
        "secretsmanager", "describe-secret", {"SecretId": binding["migration_secret_arn"]}
    )
    require(
        secret.get("ARN") == binding["migration_secret_arn"]
        and not secret.get("DeletedDate")
        and secret.get("KmsKeyId") in (None, "alias/aws/secretsmanager"),
        "Secret identity or KMS grant needs review",
    )


def owned_stack(call, tags, template_hash, stack_id=None, *, profile=DEVELOPER, purpose="probe"):
    """Refuse foreign stacks before invocation or deletion."""
    target = identities(profile)
    require(purpose in {"probe", "upgrade"}, "Unknown private worker purpose")
    account, region = target["account"], target["region"]
    name = target["probe_name" if purpose == "probe" else "upgrade_name"]
    rows = call("cloudformation", "describe-stacks", {"StackName": stack_id or name})["Stacks"]
    require(len(rows) == 1, "Probe stack identity differs")
    stack = rows[0]
    require(
        re.fullmatch(
            rf"arn:aws:cloudformation:{region}:{account}:stack/{name}/[\w-]+",
            stack.get("StackId", ""),
        ),
        "Probe stack ARN differs",
    )
    require(stack_id is None or stack["StackId"] == stack_id, "Stack receipt differs")
    actual = {row["Key"]: row["Value"] for row in stack.get("Tags", [])}
    require(
        all(actual.get(key) == value for key, value in tags.items()),
        "Probe stack belongs to another operation",
    )
    template = call(
        "cloudformation",
        "get-template",
        {"StackName": stack["StackId"], "TemplateStage": "Original"},
    )["TemplateBody"]
    if isinstance(template, str):
        template = json.loads(template)
    require(
        hashlib.sha256(compact(template).encode()).hexdigest() == template_hash,
        "Live probe template differs",
    )
    return stack


def inspect_function(review, binding, stack, call, *, profile, purpose="probe"):
    """Require exact private worker configuration and absence of public/event triggers."""
    require(purpose in {"probe", "upgrade"}, "Unknown private worker purpose")
    target = identities(profile)
    account, region = target["account"], target["region"]
    name = target["probe_name" if purpose == "probe" else "upgrade_name"]
    uri = target["registry"] + "/" + target["image_repository"]
    function = call("lambda", "get-function", {"FunctionName": name})
    if purpose == "upgrade":
        require(
            isinstance(function.get("Tags"), dict) and not function.get("TagsError"),
            "Upgrade invocation marker cannot be inspected",
        )
    config = function["Configuration"]
    resource_id = "Probe" if purpose == "probe" else "Upgrade"
    expected = review["template"]["Resources"][resource_id]["Properties"]
    require(
        function["Code"].get("ResolvedImageUri") == uri + "@" + binding["image_digest"]
        and config.get("FunctionArn") == f"arn:aws:lambda:{region}:{account}:function:{name}"
        and config.get("State") == "Active"
        and config.get("LastUpdateStatus") == "Successful"
        and config.get("MemorySize") == expected["MemorySize"]
        and config.get("Timeout") == expected["Timeout"]
        and config.get("Architectures") == expected["Architectures"]
        and config.get("ImageConfigResponse", {}).get("ImageConfig") == expected["ImageConfig"]
        and config.get("Environment", {}).get("Variables") == expected["Environment"]["Variables"]
        and set(config.get("VpcConfig", {}).get("SubnetIds", []))
        == set(expected["VpcConfig"]["SubnetIds"])
        and set(config.get("VpcConfig", {}).get("SecurityGroupIds", []))
        == set(expected["VpcConfig"]["SecurityGroupIds"]),
        "Live probe configuration differs",
    )
    concurrency = call("lambda", "get-function-concurrency", {"FunctionName": name})
    require(concurrency.get("ReservedConcurrentExecutions") == 1, "Probe concurrency differs")
    role = call(
        "cloudformation",
        "describe-stack-resource",
        {"StackName": stack["StackId"], "LogicalResourceId": resource_id + "Role"},
    )["StackResourceDetail"]
    require(
        role.get("ResourceType") == "AWS::IAM::Role"
        and config.get("Role")
        == f"arn:aws:iam::{account}:role/" + role.get("PhysicalResourceId", ""),
        "Probe execution role differs",
    )
    live_role = call("iam", "get-role", {"RoleName": role["PhysicalResourceId"]})["Role"]
    role_properties = review["template"]["Resources"][resource_id + "Role"]["Properties"]
    require(
        live_role.get("Arn") == config["Role"]
        and live_role.get("PermissionsBoundary", {}).get("PermissionsBoundaryArn")
        == role_properties["PermissionsBoundary"]
        and live_role.get("AssumeRolePolicyDocument")
        == role_properties["AssumeRolePolicyDocument"],
        "Live runtime role boundary or trust differs",
    )
    urls = call("lambda", "list-function-url-configs", {"FunctionName": name})
    require(
        urls.get("FunctionUrlConfigs") == [] and not urls.get("NextMarker"),
        "Public function URL refused",
    )
    require(
        call("lambda", "get-policy", {"FunctionName": name}) == {"absent": True},
        "Probe resource policy must be absent",
    )
    events = call("lambda", "list-event-source-mappings", {"FunctionName": name})
    require(
        events.get("EventSourceMappings") == [] and not events.get("NextMarker"),
        "Probe event source refused",
    )

    return function


def execute(
    mode,
    review,
    expected_hash,
    source_sha,
    sql,
    operation_id,
    image_receipt,
    call,
    *,
    now=None,
    stack_id=None,
    profile=DEVELOPER,
):
    """Perform one lifecycle step without automatic mutation retries or implicit cleanup."""
    target = identities(profile)
    account, name = target["account"], target["probe_name"]
    role_prefix = f"arn:aws:sts::{account}:assumed-role/{target['operator_role']}/"
    now = time.time() if now is None else now
    require(mode in {"create", "collect", "cleanup", "cleanup-check"}, "Unknown probe mode")
    require(re.fullmatch(r"[0-9a-f]{32}", operation_id or ""), "Exact operation ID required")
    binding = validate_review(
        review,
        expected_hash,
        source_sha,
        sql,
        now=now,
        cleanup=mode.startswith("cleanup"),
        profile=profile,
    )
    identity = call("sts", "get-caller-identity", {})
    require(
        identity.get("Account") == account and identity.get("Arn", "").startswith(role_prefix),
        "Wrong probe account or role",
    )
    tags = {
        "FitfinityOperation": operation_id,
        "FitfinitySource": source_sha,
        "FitfinityTemplate": expected_hash,
        "FitfinityProfile": target["profile_sha256"],
    }
    if mode == "create":
        preflight(binding, call, profile=profile)
        validate_image(image_receipt, binding, call, now, profile=profile)
        result = call(
            "cloudformation",
            "create-stack",
            {
                "StackName": name,
                "TemplateBody": compact(review["template"]),
                "Capabilities": ["CAPABILITY_NAMED_IAM"],
                "OnFailure": "DO_NOTHING",
                "ClientRequestToken": operation_id,
                "Tags": [{"Key": key, "Value": value} for key, value in tags.items()],
            },
        )
        return {"state": "create_submitted", "stack_id": result["StackId"], "next": "collect"}
    require(
        mode != "cleanup-check" or stack_id, "Cleanup verification requires the retained stack ARN"
    )
    stack = owned_stack(call, tags, expected_hash, stack_id, profile=profile)
    status = stack["StackStatus"]
    if mode == "cleanup-check":
        return {
            "state": "cleanup_verified" if status == "DELETE_COMPLETE" else "cleanup_pending",
            "stack_status": status,
        }
    if mode == "cleanup":
        require(
            status
            in {
                "CREATE_COMPLETE",
                "CREATE_FAILED",
                "ROLLBACK_COMPLETE",
                "ROLLBACK_FAILED",
                "DELETE_FAILED",
            },
            "Stack is not ready for cleanup",
        )
        call(
            "cloudformation",
            "delete-stack",
            {"StackName": stack["StackId"], "ClientRequestToken": operation_id + "-cleanup"},
        )
        return {"state": "cleanup_submitted", "stack_id": stack["StackId"], "next": "cleanup-check"}
    require(status == "CREATE_COMPLETE", "Probe not ready; inspect stack before collecting")
    validate_image(image_receipt, binding, call, now, profile=profile)
    inspect_function(review, binding, stack, call, profile=profile)
    result = call(
        "lambda",
        "invoke",
        {
            "FunctionName": name,
            "InvocationType": "RequestResponse",
            "LogType": "None",
            "Payload": compact(review["invoke_payload"]),
        },
    )
    require(
        result.get("StatusCode") == 200 and not result.get("FunctionError"),
        "Probe invocation failed",
    )
    # Lambda Web Adapter returns the JSON response body directly for a generic event.
    payload = result.get("Payload")
    require(
        isinstance(payload, dict)
        and set(payload) == {"source_sha", "sql_sha256", "catalog"}
        and payload.get("source_sha") == source_sha
        and payload.get("sql_sha256") == binding["sql_sha256"],
        "Probe result binding differs",
    )
    catalog = payload["catalog"]
    require(
        isinstance(catalog, dict)
        and catalog.get("database") == binding["db_name"]
        and catalog.get("database_user") == "fitfinity_migrator"
        and catalog.get("transaction_read_only") == "on",
        "Probe catalog identity differs",
    )
    return {
        "state": "observed",
        "stack_id": stack["StackId"],
        "receipt": payload,
        "next": "cleanup",
    }
