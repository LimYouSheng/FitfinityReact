"""Execute one reviewed private probe operation; never migrate or deploy the staff API."""

import hashlib
import json
import re
import time
from datetime import UTC, datetime

from operator_checks import require
from release_image import ACCOUNT, REGION, URI, scan_policy
from schema_probe_iam import NAME
from schema_probe_plan import prepare_review

ROLE = f"arn:aws:sts::{ACCOUNT}:assumed-role/fitfinity-test-github-schema-probe/"


def compact(value):
    """Serialize protocol payloads without optional whitespace."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def validate_review(review, expected_hash, source_sha, sql, *, now, cleanup=False):
    """Recompute the approved template before any AWS operation."""
    binding = review["bindings"]
    checked = prepare_review(
        binding,
        source_sha,
        sql,
        now=binding["expires_at"] - 1 if cleanup else now,
    )
    require(review == checked, "Probe review changed; regenerate and review")
    require(
        re.fullmatch(r"[0-9a-f]{64}", expected_hash or "")
        and checked["template_sha256"] == expected_hash,
        "Reviewed template digest differs",
    )
    return binding


def validate_image(receipt, binding, call, now):
    """Require a matching publication receipt and fresh live scan without starting one."""
    require(
        receipt.get("account") == ACCOUNT
        and receipt.get("region") == REGION
        and receipt.get("revision") == binding["source_sha"]
        and receipt.get("image_digest") == binding["image_digest"]
        and receipt.get("image_uri") == URI + "@" + binding["image_digest"]
        and all(
            receipt.get(key) is True
            for key in ("candidate_ready", "image_published", "scan_policy_passed")
        )
        and receipt.get("source_files", {}).get("backend/infrastructure/read-schema.sql")
        == binding["sql_sha256"],
        "Image publication receipt differs",
    )
    pages, tokens = [], set()
    arguments = {
        "repositoryName": "fitfinity-test-api",
        "imageId": {"imageDigest": binding["image_digest"]},
    }
    while True:
        page = call("ecr", "describe-image-scan-findings", arguments)
        require(
            page.get("imageScanStatus", {}).get("status") == "COMPLETE", "Image scan is incomplete"
        )
        pages.append(page)
        token = page.get("nextToken")
        if not token:
            break
        require(token not in tokens and len(pages) < 100, "Invalid image scan pagination")
        tokens.add(token)
        arguments = {**arguments, "nextToken": token}
    scan_policy(pages, binding["image_digest"], datetime.fromtimestamp(now, UTC))


def preflight(binding, call):
    """Verify current private resource metadata without retrieving credentials."""
    limits = call("lambda", "get-account-settings", {})
    require(
        limits.get("AccountLimit", {}).get("UnreservedConcurrentExecutions", 0) >= 101,
        "Account concurrency cannot reserve one probe execution while retaining AWS headroom",
    )
    databases = call("rds", "describe-db-instances", {"DBInstanceIdentifier": "fitfinity-test-db"})[
        "DBInstances"
    ]
    require(len(databases) == 1, "Database identity differs")
    db = databases[0]
    require(
        db.get("DBInstanceArn") == f"arn:aws:rds:{REGION}:{ACCOUNT}:db:fitfinity-test-db"
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
            and row.get("OwnerId") == ACCOUNT
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
        len(groups) == 1 and groups[0].get("VpcId") == vpc and groups[0].get("OwnerId") == ACCOUNT,
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


def owned_stack(call, tags, template_hash, stack_id=None):
    """Refuse foreign stacks before invocation or deletion."""
    rows = call("cloudformation", "describe-stacks", {"StackName": stack_id or NAME})["Stacks"]
    require(len(rows) == 1, "Probe stack identity differs")
    stack = rows[0]
    require(
        re.fullmatch(
            rf"arn:aws:cloudformation:{REGION}:{ACCOUNT}:stack/{NAME}/[\w-]+",
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
):
    """Perform one lifecycle step without automatic mutation retries or implicit cleanup."""
    now = time.time() if now is None else now
    require(mode in {"create", "collect", "cleanup", "cleanup-check"}, "Unknown probe mode")
    require(re.fullmatch(r"[0-9a-f]{32}", operation_id or ""), "Exact operation ID required")
    binding = validate_review(
        review, expected_hash, source_sha, sql, now=now, cleanup=mode.startswith("cleanup")
    )
    identity = call("sts", "get-caller-identity", {})
    require(
        identity.get("Account") == ACCOUNT and identity.get("Arn", "").startswith(ROLE),
        "Wrong probe account or role",
    )
    tags = {
        "FitfinityOperation": operation_id,
        "FitfinitySource": source_sha,
        "FitfinityTemplate": expected_hash,
    }
    if mode == "create":
        preflight(binding, call)
        validate_image(image_receipt, binding, call, now)
        result = call(
            "cloudformation",
            "create-stack",
            {
                "StackName": NAME,
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
    stack = owned_stack(call, tags, expected_hash, stack_id)
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
    validate_image(image_receipt, binding, call, now)
    function = call("lambda", "get-function", {"FunctionName": NAME})
    config = function["Configuration"]
    expected = review["template"]["Resources"]["Probe"]["Properties"]
    require(
        function["Code"].get("ResolvedImageUri") == URI + "@" + binding["image_digest"]
        and config.get("FunctionArn") == f"arn:aws:lambda:{REGION}:{ACCOUNT}:function:{NAME}"
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
    concurrency = call("lambda", "get-function-concurrency", {"FunctionName": NAME})
    require(concurrency.get("ReservedConcurrentExecutions") == 1, "Probe concurrency differs")
    role = call(
        "cloudformation",
        "describe-stack-resource",
        {"StackName": stack["StackId"], "LogicalResourceId": "ProbeRole"},
    )["StackResourceDetail"]
    require(
        role.get("ResourceType") == "AWS::IAM::Role"
        and config.get("Role")
        == f"arn:aws:iam::{ACCOUNT}:role/" + role.get("PhysicalResourceId", ""),
        "Probe execution role differs",
    )
    live_role = call("iam", "get-role", {"RoleName": role["PhysicalResourceId"]})["Role"]
    role_properties = review["template"]["Resources"]["ProbeRole"]["Properties"]
    require(
        live_role.get("Arn") == config["Role"]
        and live_role.get("PermissionsBoundary", {}).get("PermissionsBoundaryArn")
        == role_properties["PermissionsBoundary"]
        and live_role.get("AssumeRolePolicyDocument")
        == role_properties["AssumeRolePolicyDocument"],
        "Live runtime role boundary or trust differs",
    )
    urls = call("lambda", "list-function-url-configs", {"FunctionName": NAME})
    require(
        urls.get("FunctionUrlConfigs") == [] and not urls.get("NextMarker"),
        "Public function URL refused",
    )
    require(
        call("lambda", "get-policy", {"FunctionName": NAME}) == {"absent": True},
        "Probe resource policy must be absent",
    )
    events = call("lambda", "list-event-source-mappings", {"FunctionName": NAME})
    require(
        events.get("EventSourceMappings") == [] and not events.get("NextMarker"),
        "Probe event source refused",
    )
    result = call(
        "lambda",
        "invoke",
        {
            "FunctionName": NAME,
            "InvocationType": "RequestResponse",
            "LogType": "None",
            "Payload": compact(review["invoke_payload"]),
        },
    )
    require(
        result.get("StatusCode") == 200 and not result.get("FunctionError"),
        "Probe invocation failed",
    )
    envelope = result["Payload"]
    require(
        envelope.get("statusCode") == 200 and envelope.get("isBase64Encoded", False) is False,
        "Probe HTTP response failed",
    )
    payload = json.loads(envelope["body"])
    require(
        payload.get("source_sha") == source_sha
        and payload.get("sql_sha256") == binding["sql_sha256"],
        "Probe result binding differs",
    )
    catalog = payload.get("catalog", {})
    require(
        catalog.get("database") == binding["db_name"]
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
