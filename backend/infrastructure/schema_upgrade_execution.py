"""Execute reviewed private upgrades with owned-resource and uncertain-outcome receipts."""

import json
import re
import time
from datetime import datetime

from deployment_profile import identities
from operator_checks import require
from release_maintenance import check_snapshot_tags, verified_snapshot
from release_pause import require_recorded_pause
from schema_probe_execution import compact, inspect_function, owned_stack, preflight
from schema_upgrade_plan import prepare, validate_image


def readiness(binding, evidence, call, *, profile, now):
    """Require fresh catalog/backup evidence and currently disabled staff invocation."""
    target = identities(profile)
    account, region = target["account"], target["region"]
    require(isinstance(evidence, dict), "Upgrade readiness evidence required")
    catalog = evidence.get("catalog", {})
    require(
        catalog.get("database") == binding["db_name"]
        and catalog.get("database_user") == "fitfinity_migrator"
        and catalog.get("transaction_read_only") == "on"
        and catalog.get("alembic_revisions") == [binding["from_revision"]],
        "Fresh private catalog identity/revision required",
    )
    observed = datetime.fromisoformat(catalog.get("observed_at", ""))
    require(
        observed.tzinfo is not None and 0 <= now - observed.timestamp() <= 3600,
        "Catalog evidence expired or future dated",
    )
    snapshot = evidence.get("snapshot_arn", "")
    maintenance = evidence.get("maintenance")
    ownership = verified_snapshot(maintenance, snapshot, target, binding["source_sha"])
    rows = call("rds", "describe-db-snapshots", {"DBSnapshotIdentifier": snapshot})["DBSnapshots"]
    require(len(rows) == 1, "Snapshot identity differs")
    backup = rows[0]
    check_snapshot_tags(backup.get("TagList"), ownership["tags"])
    instances = call("rds", "describe-db-instances", {"DBInstanceIdentifier": target["database"]})[
        "DBInstances"
    ]
    database_arn = f"arn:aws:rds:{region}:{account}:db:{target['database']}"
    require(
        len(instances) == 1
        and instances[0].get("DBInstanceArn") == database_arn
        and isinstance(instances[0].get("DbiResourceId"), str)
        and bool(instances[0]["DbiResourceId"]),
        "Database resource identity required",
    )
    require(
        backup.get("DBSnapshotArn") == snapshot
        and backup.get("DBSnapshotIdentifier") == ownership["name"]
        and not backup.get("SourceDBSnapshotIdentifier")
        and backup.get("DBInstanceIdentifier") == target["database"]
        and backup.get("DbiResourceId") == instances[0]["DbiResourceId"]
        and backup.get("Status") == "available"
        and backup.get("SnapshotType") == "manual"
        and backup.get("Encrypted") is True
        and backup.get("Engine") == "postgres",
        "A completed encrypted target PostgreSQL snapshot is required",
    )
    created = datetime.fromisoformat(backup.get("SnapshotCreateTime", ""))
    require(
        created.tzinfo is not None
        and max(observed.timestamp(), maintenance["drained_after"]) <= created.timestamp() <= now,
        "Backup must follow both the current catalog observation and the maintenance drain",
    )
    function = call("lambda", "get-function", {"FunctionName": target["runtime_function"]})
    config = function.get("Configuration", {})
    tags = function.get("Tags")
    require(
        config.get("FunctionArn")
        == f"arn:aws:lambda:{region}:{account}:function:{target['runtime_function']}"
        and config.get("LastUpdateStatus") == "Successful",
        "Staff runtime identity/update state differs",
    )
    require(
        isinstance(tags, dict)
        and not function.get("TagsError")
        and tags.get("FitfinityMaintenance") == ownership["marker"]
        and tags.get("FitfinitySnapshot") == ownership["marker"],
        "Snapshot must belong to the active drained maintenance operation",
    )
    concurrency = call(
        "lambda", "get-function-concurrency", {"FunctionName": target["runtime_function"]}
    )
    require(
        type(concurrency.get("ReservedConcurrentExecutions")) is int
        and concurrency["ReservedConcurrentExecutions"] == 0,
        "Staff invocation must remain disabled during the upgrade",
    )
    require_recorded_pause(call, profile)


def execute(
    mode,
    review,
    expected_hash,
    source_sha,
    image_receipt,
    call,
    persist,
    *,
    profile,
    evidence=None,
    prior=None,
    stack_id=None,
    now=None,
    migrations=None,
):
    """Perform one explicit step; persist write intent before any mutation, never retry it."""
    require(
        mode in {"create", "inspect", "invoke", "cleanup", "cleanup-check"}, "Unknown upgrade mode"
    )
    require(callable(persist), "Durable receipt writer required")
    now = time.time() if now is None else now
    binding = review["binding"]
    checked = prepare(
        binding,
        profile=profile,
        source_sha=source_sha,
        migrations=migrations,
        now=binding["expires_at"] - 1 if mode in {"inspect", "cleanup", "cleanup-check"} else now,
    )
    require(
        review == checked and expected_hash == checked["template_sha256"], "Upgrade review differs"
    )
    target = identities(profile)
    account, name = target["account"], target["upgrade_name"]
    identity = call("sts", "get-caller-identity", {})
    require(
        identity.get("Account") == account
        and re.fullmatch(
            rf"arn:aws:sts::{account}:assumed-role/{re.escape(target['upgrade_operator_role'])}/[\w+=,.@-]+",
            identity.get("Arn", ""),
        ),
        "Wrong upgrade account or role",
    )
    tags = {
        "FitfinityOperation": binding["operation_id"],
        "FitfinitySource": source_sha,
        "FitfinityTemplate": expected_hash,
        "FitfinityProfile": target["profile_sha256"],
    }
    receipt = {"identity": tags, "stack_id": stack_id, "state": "checked"}
    if prior is not None:
        require(prior.get("identity") == tags, "Prior operation identity differs")
        require(
            stack_id == prior.get("stack_id")
            or (
                mode == "inspect"
                and prior.get("state") == "create_submitted"
                and prior.get("stack_id") is None
            ),
            "Prior stack receipt differs",
        )
    if mode == "create":
        require(prior is None and stack_id is None, "Inspect an earlier create; do not replay")
        preflight(binding, call, profile=profile)
        validate_image(review, image_receipt, call, profile=profile, source_sha=source_sha, now=now)
        receipt["state"] = "create_submitted"
        persist(dict(receipt))
        result = call(
            "cloudformation",
            "create-stack",
            {
                "StackName": name,
                "TemplateBody": compact(review["template"]),
                "Capabilities": ["CAPABILITY_NAMED_IAM"],
                "OnFailure": "DO_NOTHING",
                "ClientRequestToken": binding["operation_id"],
                "Tags": [{"Key": key, "Value": value} for key, value in tags.items()],
            },
        )
        receipt["stack_id"] = result["StackId"]
    else:
        require(stack_id is not None, "Exact retained stack ARN required")
        stack = owned_stack(call, tags, expected_hash, stack_id, profile=profile, purpose="upgrade")
        status = stack["StackStatus"]
        if mode == "cleanup-check":
            receipt.update(
                state="cleanup_verified" if status == "DELETE_COMPLETE" else "cleanup_pending"
            )
        elif mode == "cleanup":
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
            receipt["state"] = "cleanup_submitted"
            persist(dict(receipt))
            call(
                "cloudformation",
                "delete-stack",
                {"StackName": stack_id, "ClientRequestToken": binding["operation_id"] + "-cleanup"},
            )
        else:
            require(status == "CREATE_COMPLETE", "Upgrade worker is not ready")
            live = inspect_function(
                review, binding, stack, call, profile=profile, purpose="upgrade"
            )
            if mode == "inspect":
                require(prior is not None, "Retained operation receipt required for inspection")
                receipt.update(state="worker_verified", database_outcome="not_observed")
                if live.get("Tags", {}).get("FitfinityInvocation"):
                    receipt["invocation"] = "invoke_submitted"
                # Preserve uncertain invocation evidence across metadata-only inspection.
                if prior and (
                    prior.get("invocation")
                    or prior.get("state") in {"invoke_submitted", "upgraded", "already_at_target"}
                ):
                    receipt["invocation"] = prior.get("invocation", prior["state"])
            else:
                require(
                    prior is not None
                    and prior.get("state") in {"create_submitted", "worker_verified"}
                    and not prior.get("invocation"),
                    "Inspect database after any previous invocation; do not replay",
                )
                validate_image(
                    review,
                    image_receipt,
                    call,
                    profile=profile,
                    source_sha=source_sha,
                    now=now,
                    migrations=migrations,
                )
                preflight(binding, call, profile=profile, reserve_capacity=False)
                readiness(binding, evidence, call, profile=profile, now=now)
                require(
                    not live.get("Tags", {}).get("FitfinityInvocation"),
                    "Worker invocation already marked; inspect database before recovery",
                )
                receipt["state"] = "invoke_submitted"
                persist(dict(receipt))
                call(
                    "lambda",
                    "tag-resource",
                    {
                        "Resource": live["Configuration"]["FunctionArn"],
                        "Tags": {"FitfinityInvocation": binding["operation_id"]},
                    },
                )
                result = call(
                    "lambda",
                    "invoke",
                    {
                        "FunctionName": name,
                        "InvocationType": "RequestResponse",
                        "LogType": "None",
                        "Payload": json.dumps(review["invoke_payload"], separators=(",", ":")),
                    },
                )
                require(
                    result.get("StatusCode") == 200 and not result.get("FunctionError"),
                    "Upgrade outcome uncertain; inspect database",
                )
                # Generic events return the worker's JSON object directly through the adapter.
                payload = result.get("Payload")
                require(
                    payload
                    in [
                        {
                            "operation_id": binding["operation_id"],
                            "source_sha": source_sha,
                            "from_revision": binding["from_revision"],
                            "schema": binding["to_revision"],
                            "outcome": outcome,
                        }
                        for outcome in ("upgraded", "already_at_target")
                    ],
                    "Upgrade response binding differs; inspect database",
                )
                receipt.update(state=payload["outcome"], result=payload)
    persist(dict(receipt))
    return receipt
