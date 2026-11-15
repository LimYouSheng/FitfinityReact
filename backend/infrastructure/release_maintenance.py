"""Pause one reviewed staff runtime and prepare an owned pre-upgrade snapshot."""

import re
import time

from deployment_profile import identities
from operator_checks import require


def validate_review(review, profile, now):
    """Reject incomplete, foreign or expired maintenance metadata."""
    target = identities(profile)
    require(
        set(review)
        == {
            "profile_sha256",
            "source_sha",
            "operation_id",
            "expires_at",
            "function_revision",
            "database_resource_id",
            "previous_concurrency",
        }
        and review["profile_sha256"] == target["profile_sha256"]
        and re.fullmatch(r"[a-f0-9]{40}", review["source_sha"])
        and re.fullmatch(r"[a-f0-9]{32}", review["operation_id"])
        and re.fullmatch(r"[A-Za-z0-9-]{1,128}", review["function_revision"])
        and re.fullmatch(r"db-[A-Za-z0-9]{1,64}", review["database_resource_id"])
        and type(review["expires_at"]) is int
        and 0 < review["expires_at"] - now <= 3600
        and type(review["previous_concurrency"]) is int
        and review["previous_concurrency"] > 0,
        "Exact unexpired maintenance review required",
    )
    return target


def inspect(review, call, profile, now):
    """Recheck exact cloud identities and reject stale maintenance authority."""
    target = validate_review(review, profile, now)
    account, region = target["account"], target["region"]
    identity = call("sts", "get-caller-identity", {})
    require(
        identity.get("Account") == account
        and re.fullmatch(
            rf"arn:aws:sts::{account}:assumed-role/{re.escape(target['maintenance_role'])}/[\w+=,.@-]+",
            identity.get("Arn", ""),
        ),
        "Wrong maintenance account or role",
    )
    function = call("lambda", "get-function", {"FunctionName": target["runtime_function"]})
    config = function.get("Configuration", {})
    require(
        config.get("FunctionArn")
        == f"arn:aws:lambda:{region}:{account}:function:" + target["runtime_function"]
        and config.get("RevisionId") == review["function_revision"]
        and config.get("LastUpdateStatus") == "Successful"
        and type(config.get("Timeout")) is int
        and 1 <= config["Timeout"] <= 900
        and isinstance(function.get("Tags"), dict)
        and not function.get("TagsError"),
        "Staff runtime configuration or tag observation differs",
    )
    rows = call("rds", "describe-db-instances", {"DBInstanceIdentifier": target["database"]})[
        "DBInstances"
    ]
    require(
        len(rows) == 1
        and rows[0].get("DBInstanceArn")
        == f"arn:aws:rds:{region}:{account}:db:{target['database']}"
        and rows[0].get("DbiResourceId") == review["database_resource_id"]
        and rows[0].get("DBInstanceStatus") == "available"
        and rows[0].get("Engine") == "postgres"
        and rows[0].get("StorageEncrypted") is True
        and rows[0].get("PubliclyAccessible") is False,
        "Private database identity or readiness differs",
    )
    concurrency = call(
        "lambda", "get-function-concurrency", {"FunctionName": target["runtime_function"]}
    ).get("ReservedConcurrentExecutions")
    require(type(concurrency) is int, "Explicit staff concurrency required")
    return target, function, concurrency


def execute(mode, review, call, persist, *, profile, prior=None, now=None):
    """Persist intent before each write; inspect uncertain outcomes without replay."""
    require(
        mode in {"pause", "inspect", "snapshot", "snapshot-check"}, "Unknown maintenance operation"
    )
    require(callable(persist), "Durable maintenance receipt writer required")
    now = time.time() if now is None else now
    target, function, concurrency = inspect(
        review,
        call,
        profile,
        review["expires_at"] - 1 if mode in {"inspect", "snapshot-check"} else now,
    )
    operation = review["operation_id"]
    ownership = operation + ":" + review["source_sha"] + ":" + target["profile_sha256"]
    snapshot_name = target["resource_prefix"] + "-release-" + operation
    snapshot_arn = f"arn:aws:rds:{target['region']}:{target['account']}:snapshot:{snapshot_name}"
    snapshot_marker = function["Tags"].get("FitfinitySnapshot")
    marker = function["Tags"].get("FitfinityMaintenance")
    identity = {key: review[key] for key in ("profile_sha256", "source_sha", "operation_id")}
    receipt = {
        "identity": identity,
        "state": "checked",
        "previous_concurrency": review["previous_concurrency"],
    }
    if prior is not None:
        require(
            prior.get("identity") == identity
            and prior.get("previous_concurrency") == review["previous_concurrency"],
            "Prior maintenance identity differs",
        )
    if mode == "pause":
        require(
            prior is None and marker is None and concurrency == review["previous_concurrency"],
            "Inspect existing maintenance; do not replay pause",
        )
        receipt["state"] = "pause_submitted"
        persist(dict(receipt))
        call(
            "lambda",
            "tag-resource",
            {
                "Resource": function["Configuration"]["FunctionArn"],
                "Tags": {"FitfinityMaintenance": ownership},
            },
        )
        call(
            "lambda",
            "put-function-concurrency",
            {"FunctionName": target["runtime_function"], "ReservedConcurrentExecutions": 0},
        )
    else:
        require(prior is not None and marker == ownership, "Owned maintenance marker required")
        if mode == "inspect":
            receipt["state"] = "paused" if concurrency == 0 else "pause_not_observed"
            if concurrency == 0:
                receipt["drained_after"] = prior.get(
                    "drained_after", now + function["Configuration"]["Timeout"]
                )
            if prior.get("snapshot_arn"):
                receipt["snapshot_arn"] = prior["snapshot_arn"]
            if prior.get("snapshot_requested") or snapshot_marker == ownership:
                receipt["snapshot_requested"] = True
                receipt["snapshot_arn"] = snapshot_arn
        else:
            require(concurrency == 0, "Staff invocation must remain disabled")
            name, arn = snapshot_name, snapshot_arn
            receipt["snapshot_arn"] = arn
            receipt["snapshot_requested"] = True
            if mode == "snapshot":
                require(
                    prior.get("state") == "paused"
                    and not prior.get("snapshot_requested")
                    and snapshot_marker is None,
                    "Inspect the original snapshot request; do not replay",
                )
                require(
                    type(prior.get("drained_after")) in (int, float)
                    and now >= prior["drained_after"],
                    "Wait for the runtime's maximum in-flight invocation lifetime",
                )
                receipt["state"] = "snapshot_submitted"
                persist(dict(receipt))
                call(
                    "lambda",
                    "tag-resource",
                    {
                        "Resource": function["Configuration"]["FunctionArn"],
                        "Tags": {"FitfinitySnapshot": ownership},
                    },
                )
                call(
                    "rds",
                    "create-db-snapshot",
                    {
                        "DBInstanceIdentifier": target["database"],
                        "DBSnapshotIdentifier": name,
                        "Tags": [
                            {"Key": key, "Value": value}
                            for key, value in {
                                "Application": "Fitfinity",
                                "FitfinityOperation": operation,
                                "FitfinityProfile": target["profile_sha256"],
                                "FitfinitySource": review["source_sha"],
                            }.items()
                        ],
                    },
                )
            else:
                require(
                    prior.get("snapshot_requested") is True and prior.get("snapshot_arn") == arn,
                    "Original snapshot intent required",
                )
                rows = call("rds", "describe-db-snapshots", {"DBSnapshotIdentifier": arn})[
                    "DBSnapshots"
                ]
                require(
                    len(rows) == 1
                    and rows[0].get("DBSnapshotArn") == arn
                    and rows[0].get("DbiResourceId") == review["database_resource_id"]
                    and rows[0].get("DBInstanceIdentifier") == target["database"]
                    and rows[0].get("SnapshotType") == "manual"
                    and rows[0].get("Encrypted") is True,
                    "Snapshot identity or encryption differs",
                )
                tags = call("rds", "list-tags-for-resource", {"ResourceName": arn})["TagList"]
                observed = {row["Key"]: row["Value"] for row in tags}
                require(
                    observed.get("FitfinityOperation") == operation
                    and observed.get("FitfinityProfile") == target["profile_sha256"]
                    and observed.get("FitfinitySource") == review["source_sha"],
                    "Snapshot ownership differs",
                )
                receipt["state"] = (
                    "snapshot_ready" if rows[0].get("Status") == "available" else "snapshot_pending"
                )
    persist(dict(receipt))
    return receipt
